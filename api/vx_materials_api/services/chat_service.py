"""Reserva e persistência de turnos.

Um turno passa por duas transações curtas, e o Agent é chamado entre elas, sem lock aberto:

1. Reserva: confere dono, versão esperada e turno ativo, e grava `active_turn_id`.
2. Conclusão: só aplica o retorno se o turno reservado ainda for o ativo; grava as duas mensagens,
   mescla o contexto e incrementa a versão.

Se o Agent falhar, a reserva é liberada sem mudar a versão, e nada da mensagem fica gravado.
A invalidação de uma prova de catálogo antiga permanece gravada para a próxima tentativa.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from domain.identity import identity_signature
from domain.pdm_loader import DEFAULT_PDM_VERSION
from pipelines.sanitize import _catalog
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.extraction import get_extraction_repository
from vx_materials_api.db.models import ChatMessage, ChatSession, Dataset, MaterialMaster, OperationRequest
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.chat import AgentRunResponse, ChatMessageRequest, ChatTurnResponse, MaterialCard
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.rbac import has_permission, require_conversation_owner, require_resource_scope

NCM_VERSION = "ncm-demo-v1"
# Reserva sem conclusão por mais que isso é tratada como abandonada (queda da API no meio do turno).
ABANDONED_TURN_AFTER = timedelta(seconds=60)
# Chaves que o Agent pode gravar no contexto da sessão. O resto do retorno é descartado.
CONTEXT_KEYS = frozenset(
    {
        "candidate_class_ids",
        "dismissed_material_codes",
        "offered_material_codes",
        "confirmed_attributes",
        "item_name",
        "missing_attributes",
        "pdm_class_id",
        "planner",
        "validation_status",
    }
)


SEARCH_TOOL = "search_similar_materials"
# Verificação de duplicidade aceita pela API. Só a API grava: o Agent não escreve nesta chave.
DUPLICATE_CHECK = "duplicate_check"
_NOT_RUN = object()


def cache_rules(catalog) -> str:
    embedder = get_embedding_repository()
    return index_version(
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
        embedder.signature if embedder else None,
    )


def _catalog_proof(db, tenant_id, rules_version):
    # Contagem e soma avançam em cada publicação/alteração; a API nunca reduz revisões nem apaga materiais.
    count, revisions = db.execute(
        select(func.count(), func.coalesce(func.sum(MaterialMaster.version), 0)).where(
            MaterialMaster.tenant_id == tenant_id
        )
    ).one()
    dataset = db.scalar(
        select(Dataset.id)
        .where(Dataset.tenant_id == tenant_id)
        .order_by(Dataset.imported_at.desc(), Dataset.id.desc())
        .limit(1)
    )
    return {
        "materials": count,
        "revisions": int(revisions),
        "rules": rules_version,
        "inventory_dataset": str(dataset) if dataset else None,
    }


def _clear_duplicate_check(context):
    historical = list(
        dict.fromkeys([*context.get("stale_offered_material_codes", []), *context.get("offered_material_codes", [])])
    )
    cleaned = {
        **context,
        DUPLICATE_CHECK: None,
        "offered_material_codes": [],
        "dismissed_material_codes": [],
        "stale_offered_material_codes": historical,
    }
    if context.get("material_card"):
        cleaned["material_card"] = {
            **context["material_card"],
            "can_submit": False,
            "duplicate_check_status": "PENDING",
            "existing": None,
            "similar_candidates": [],
        }
    return cleaned


def card_signature(card: MaterialCard) -> str:
    """Classe, nome efetivo e atributos; o Agent calcula igual antes de reaproveitar a busca."""
    return identity_signature(card.pdm_class_id, card.pdm_class_name, card.attributes)


def _search_candidates(result: AgentRunResponse) -> list[dict[str, Any]] | None | object:
    """Candidatos da busca deste turno; None se ela falhou; `_NOT_RUN` se o turno não buscou."""
    for call in reversed(result.tool_calls):
        if call.name == SEARCH_TOOL:
            return call.result.get("candidates", []) if call.status == "SUCCEEDED" else None
    return _NOT_RUN


def effective_candidates(
    result: AgentRunResponse, saved: dict[str, Any] | None
) -> tuple[list[dict[str, Any]] | None, bool]:
    """Candidatos que valem para o turno e se vieram da verificação salva.

    Sem busca neste turno, a verificação salva só vale se a ficha for a mesma que a gerou. Caso
    contrário, o turno conta como sem verificação e o pedido não fica pronto.
    """
    search = _search_candidates(result)
    if search is not _NOT_RUN:
        return search, False
    named = result.context_patch.get("item_name")
    if named is not None and named != result.material_card.pdm_class_name:
        return None, False
    if saved and saved.get("signature") == card_signature(result.material_card):
        return saved.get("candidates", []), True
    return None, False


def validate_action(context: dict[str, Any], request: ChatMessageRequest) -> None:
    """Códigos históricos permitem recuperar o turno, mas não são reenviados como ofertas válidas."""
    action = request.action
    if action is None:
        return
    offered = [*context.get("offered_material_codes", []), *context.get("stale_offered_material_codes", [])]
    if action.type == "PICK_CANDIDATE" and action.material_code not in offered:
        raise ApiProblem(422, "INVALID_ACTION", "Esse código não foi oferecido nesta conversa.")
    if action.type == "DISMISS_CANDIDATES" and not offered:
        raise ApiProblem(422, "INVALID_ACTION", "Não há itens parecidos para descartar nesta conversa.")


def _agent_duplicate_check(saved: dict[str, Any] | None) -> dict[str, Any] | None:
    if not saved:
        return None
    keys = ("signature", "status", "existing", "similar_candidates")
    return {key: saved[key] for key in keys if saved.get(key) is not None}


def _code_to_use(candidate: dict[str, Any]) -> str | None:
    if candidate.get("status") == "ATIVO":
        return candidate.get("material_code")
    if candidate.get("status") == "BLOQUEADO":
        return candidate.get("active_code_target")
    return None


def validated_candidate_codes(
    context: dict[str, Any], patch: dict[str, Any], search: list[dict[str, Any]] | None
) -> tuple[list[str], list[str]]:
    """Códigos oferecidos e descartados que a sessão aceita, sem confiar só no retorno do Agent.

    Um descarte só vale para códigos oferecidos num turno anterior desta sessão. Um código oferecido
    precisa ter vindo da busca deste turno.
    """
    offered_before = context.get("offered_material_codes", [])
    dismissed = list(context.get("dismissed_material_codes", []))
    for code in patch.get("dismissed_material_codes", []):
        if code in offered_before and code not in dismissed:
            dismissed.append(code)
    shown = {candidate.get("material_code") for candidate in search or []}
    offered = [code for code in patch.get("offered_material_codes", []) if code in shown]
    return offered, dismissed


def turn_status(
    card: MaterialCard,
    search: list[dict[str, Any]] | None,
    dismissed: list[str],
    offered_before: list[str],
    saved_existing_code: str | None = None,
) -> str:
    """Status do turno, derivado pela API da ficha e da busca deste turno, nunca informado pelo Agent.

    Pronto para envio exige ficha válida, busca executada, nenhum item com a mesma identidade e todos
    os itens parecidos descartados pelo solicitante. Se a busca falhou, o pedido continua aguardando.
    """
    verified = {_code_to_use(c) for c in search or [] if c.get("identity_verified") and _code_to_use(c)}
    if card.existing is not None:
        chosen = {_code_to_use(c) for c in search or [] if c.get("material_code") in offered_before}
        accepted = (verified | chosen | {saved_existing_code}) - {None}
        return "EXISTING" if card.existing.material_code in accepted else "NEEDS_INPUT"
    if card.validation_status == "OUT_OF_SCOPE":
        return "OUT_OF_SCOPE"
    if search is None or verified:
        return "NEEDS_INPUT"
    similar = [c for c in search if _code_to_use(c) and c.get("material_code") not in dismissed]
    if card.validation_status == "VALID" and card.duplicate_check_status == "NO_MATCH" and not similar:
        return "READY_TO_SUBMIT"
    return "NEEDS_INPUT"


@dataclass(frozen=True)
class Reservation:
    session_id: uuid.UUID
    turn_id: uuid.UUID
    session_version: int
    agent_payload: dict[str, Any]
    catalog_proof: dict[str, Any]


def can_see_diagnostics(identity: Identity) -> bool:
    """Chamadas MCP são diagnóstico técnico: só a role Dev/TI as recebe, nunca os perfis de negócio."""
    return has_permission(identity, "chat:diagnostics")


def _conflict(code: str, message: str) -> ApiProblem:
    return ApiProblem(409, code, message)


def _exposed_centers(value) -> set[str]:
    """Centros persistidos, inclusive estoque de turnos anteriores que pode aparecer no texto."""
    if isinstance(value, list):
        return set().union(*(_exposed_centers(item) for item in value))
    if not isinstance(value, dict):
        return set()
    centers = set(value.get("history_center_codes", []))
    if value.get("center_code"):
        centers.add(value["center_code"])
    return centers.union(*(_exposed_centers(item) for item in value.values()))


def _session_centers(db: Session, session: ChatSession) -> set[str] | None:
    context = session.context or {}
    centers = _exposed_centers(context)
    if "history_center_codes" in context:
        return centers
    # Antes do acumulador, o Agent já gravava estoque no texto determinístico de item existente.
    # Só esse trecho do ASSISTANT é interpretado; mensagens do usuário e prosa livre não são escopo.
    messages = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session.id, ChatMessage.author_type == "ASSISTANT")
    )
    for message in messages:
        centers |= _exposed_centers(message.tool_calls)
        section = "Estoque nos seus centros:"
        marker = f" {section} "
        if not message.content.startswith("Esse item já existe: use o código ") or section not in message.content:
            continue
        if message.content.count(section) != 1 or marker not in message.content or not message.content.endswith("."):
            return None
        stock = message.content.rsplit(marker, 1)[1][:-1]
        for row in stock.split(", "):
            match = re.fullmatch(r".+ no centro ([^,.\s]+)", row)
            if match is None or row.count(" no centro ") != 1:
                return None
            centers.add(match[1])
    return centers


def _require_history_scope(db: Session, identity: Identity, session: ChatSession) -> set[str]:
    centers = _session_centers(db, session)
    if centers is None:
        raise ApiProblem(404, "NOT_FOUND", "Conversa não encontrada no seu escopo.")
    require_resource_scope(identity, session.tenant_id, centers)
    return centers


def _locked_session(db: Session, identity: Identity, session_id: uuid.UUID) -> ChatSession:
    session = db.scalar(
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.tenant_id == identity.tenant_id)
        .with_for_update()
    )
    # Conversa de outra pessoa responde como inexistente.
    require_conversation_owner(identity, session)
    return session


def _history(db: Session, session_id: uuid.UUID) -> list[dict[str, Any]]:
    messages = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.sequence)
    )
    return [
        {
            "id": str(message.id),
            "author": "user" if message.author_type == "USER" else "assistant",
            "content": message.content,
            "created_at": message.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
        for message in messages
    ]


def reserve_turn(db: Session, identity: Identity, request: ChatMessageRequest, *, rules_version=None) -> Reservation:
    turn_id = uuid.uuid4()
    if request.session_id is None:
        if request.expected_session_version != 0:
            raise _conflict("VERSION_CONFLICT", "Uma conversa nova começa na versão 0.")
        session = ChatSession(
            tenant_id=identity.tenant_id,
            owner_user_id=identity.user_id,
            context={"center_code": request.center_code},
            pdm_version=DEFAULT_PDM_VERSION,
            ncm_version=NCM_VERSION,
            status="ACTIVE",
            version=0,
            active_turn_id=turn_id,
        )
        db.add(session)
        db.flush()
    else:
        session = _locked_session(db, identity, request.session_id)
        _require_history_scope(db, identity, session)
        if session.registration_order_id is not None:
            raise _conflict("CHAT_ALREADY_SUBMITTED", "Esta conversa já gerou um pedido. Inicie uma nova conversa.")
        abandoned = session.updated_at < datetime.now(UTC) - ABANDONED_TURN_AFTER
        if session.active_turn_id is not None and not abandoned:
            raise _conflict("TURN_IN_PROGRESS", "Já existe um turno em processamento nesta conversa.")
        if session.version != request.expected_session_version:
            raise _conflict("VERSION_CONFLICT", "A conversa mudou desde a última resposta.")
        duplicate = db.scalar(
            select(ChatMessage.id).where(
                ChatMessage.session_id == session.id, ChatMessage.client_message_id == request.client_message_id
            )
        )
        if duplicate is not None:
            raise _conflict("DUPLICATE_MESSAGE", "Esta mensagem já foi processada.")
        validate_action(session.context or {}, request)
        # `updated_at` muda junto (onupdate) e marca o horário da reserva.
        session.active_turn_id = turn_id

    if request.session_id is None:
        validate_action({}, request)
    context = session.context or {}
    rules_version = rules_version() if callable(rules_version) else rules_version
    rules_version = rules_version or cache_rules(_catalog(None))
    proof = _catalog_proof(db, identity.tenant_id, rules_version)
    saved = context.get(DUPLICATE_CHECK)
    if saved and saved.get("catalog_proof") != proof:
        context = _clear_duplicate_check(context)
        session.context = context
    payload = {
        "turn_id": str(turn_id),
        "session_id": str(session.id),
        "session_version": session.version,
        "message": request.message,
        "action": request.action.model_dump() if request.action else None,
        "context": {
            "pdm_version": session.pdm_version or DEFAULT_PDM_VERSION,
            "ncm_version": session.ncm_version or NCM_VERSION,
            "center_code": request.center_code,
            "history": _history(db, session.id),
            "confirmed_attributes": context.get("confirmed_attributes", {}),
            "pdm_class_id": (context.get("material_card") or {}).get("pdm_class_id"),
            "item_name": (context.get("material_card") or {}).get("pdm_class_name"),
            "offered_material_codes": context.get("offered_material_codes", []),
            "dismissed_material_codes": context.get("dismissed_material_codes", []),
            "duplicate_check": _agent_duplicate_check(context.get(DUPLICATE_CHECK)),
        },
    }
    reservation = Reservation(session.id, turn_id, session.version, payload, proof)
    db.commit()
    return reservation


def release_turn(db: Session, reservation: Reservation) -> None:
    session = db.get(ChatSession, reservation.session_id, with_for_update=True)
    if session is not None and session.active_turn_id == reservation.turn_id:
        session.active_turn_id = None
    db.commit()


def complete_turn(
    db: Session,
    identity: Identity,
    request: ChatMessageRequest,
    reservation: Reservation,
    result: AgentRunResponse,
    request_id: str,
    *,
    rules_version=None,
) -> ChatTurnResponse:
    # Mesma ordem dos escritores: a conclusão só confirma prova e mensagens num catálogo estável.
    # Os locks são curtos e vêm antes do lock da conversa, como no envio de pedidos.
    for seed in (0, 1):
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, :seed))"),
            {"tenant": str(identity.tenant_id), "seed": seed},
        )
    session = _locked_session(db, identity, reservation.session_id)
    history_centers = _require_history_scope(db, identity, session)
    if session.active_turn_id != reservation.turn_id or session.version != reservation.session_version:
        raise _conflict("TURN_SUPERSEDED", "O turno foi substituído por outro.")
    rules_version = rules_version() if callable(rules_version) else rules_version
    rules_version = rules_version or cache_rules(_catalog(None))
    if _catalog_proof(db, identity.tenant_id, rules_version) != reservation.catalog_proof:
        session.context = _clear_duplicate_check(session.context or {})
        session.active_turn_id = None
        db.commit()
        raise _conflict("CATALOG_CHANGED", "O catálogo mudou durante a verificação. Envie a mensagem novamente.")

    last = db.scalar(select(func.max(ChatMessage.sequence)).where(ChatMessage.session_id == session.id)) or 0
    tool_calls = [call.model_dump(mode="json") for call in result.tool_calls]
    # O texto novo usa nomes de centros; só o histórico anterior passa pelo leitor legado.
    # A autorização usa os códigos estruturados, inclusive se a ficha for reduzida depois.
    centers = (
        history_centers | _exposed_centers(result.material_card.model_dump(mode="json")) | _exposed_centers(tool_calls)
    )
    require_resource_scope(identity, session.tenant_id, centers)
    db.add_all(
        [
            ChatMessage(
                session_id=session.id,
                client_message_id=request.client_message_id,
                sequence=last + 1,
                author_type="USER",
                actor_user_id=identity.user_id,
                content=request.message,
                turn_id=reservation.turn_id,
            ),
            ChatMessage(
                session_id=session.id,
                sequence=last + 2,
                author_type="ASSISTANT",
                content=result.assistant_message,
                tool_calls=tool_calls,
                turn_id=reservation.turn_id,
            ),
        ]
    )
    context = session.context or {}
    patch = {key: value for key, value in result.context_patch.items() if key in CONTEXT_KEYS}
    saved = context.get(DUPLICATE_CHECK)
    if saved and saved.get("catalog_proof") != reservation.catalog_proof:
        saved = None
    search, reused = effective_candidates(result, saved)
    offered, dismissed = validated_candidate_codes(context, patch, search)
    patch |= {"offered_material_codes": offered, "dismissed_material_codes": dismissed}
    saved_existing = ((saved or {}).get("existing") or {}).get("material_code") if reused else None
    status = turn_status(
        result.material_card, search, dismissed, context.get("offered_material_codes", []), saved_existing
    )
    # O envio só é liberado quando a API concorda que o pedido está pronto.
    material_card = result.material_card.model_copy(update={"can_submit": status == "READY_TO_SUBMIT"})
    if search is None:
        material_card = material_card.model_copy(
            update={"duplicate_check_status": "PENDING", "existing": None, "similar_candidates": []}
        )
    card = material_card.model_dump(mode="json")
    if search is not None:
        patch["stale_offered_material_codes"] = []
        patch[DUPLICATE_CHECK] = {
            "signature": card_signature(material_card),
            "catalog_proof": reservation.catalog_proof,
            "candidates": search,
            "status": material_card.duplicate_check_status,
            "existing": card.get("existing") if status == "EXISTING" else None,
            "similar_candidates": card["similar_candidates"],
        }
    session.context = {
        **context,
        **patch,
        "material_card": card,
        "center_code": request.center_code,
        "history_center_codes": sorted(centers | {request.center_code}),
    }
    session.version += 1
    session.active_turn_id = None
    db.commit()

    return ChatTurnResponse(
        request_id=request_id,
        session_id=session.id,
        session_version=session.version,
        # Validar no chat não cria pedido nem material: o envio é uma ação explícita, fora deste turno.
        order_id=None,
        status=status,
        assistant_message=result.assistant_message,
        # A API sempre persiste as chamadas; a resposta só as expõe a quem tem diagnóstico.
        tool_calls=result.tool_calls if can_see_diagnostics(identity) else [],
        material_card=material_card,
    )


def list_sessions(db: Session, identity: Identity, *, limit: int, offset: int) -> dict:
    title = (
        select(ChatMessage.content)
        .where(ChatMessage.session_id == ChatSession.id, ChatMessage.author_type == "USER")
        .order_by(ChatMessage.sequence)
        .limit(1)
        .scalar_subquery()
    )
    rows = db.execute(
        select(ChatSession, title)
        .where(ChatSession.tenant_id == identity.tenant_id, ChatSession.owner_user_id == identity.user_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id)
    )
    items = []
    visible = 0
    for session, title_text in rows:
        centers = _session_centers(db, session)
        if centers is None or centers - identity.center_codes:
            continue
        if visible < offset:
            visible += 1
            continue
        if len(items) == limit:
            return {"items": items, "next_cursor": str(offset + limit)}
        items.append(
            {
                "id": session.id,
                "title": (title_text or "Conversa sem mensagens")[:120],
                "updated_at": session.updated_at.isoformat(),
            }
        )
    return {"items": items, "next_cursor": None}


def read_session(db: Session, identity: Identity, session_id: uuid.UUID) -> dict:
    # Uma leitura usa o mesmo filtro de dono/tenant e snapshot do turno, sem chamar o Agent.
    session = _locked_session(db, identity, session_id)
    _require_history_scope(db, identity, session)
    context = session.context or {}
    messages = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.sequence)
    ).all()
    submission = (
        db.scalar(
            select(OperationRequest)
            .where(
                OperationRequest.user_id == identity.user_id,
                OperationRequest.operation == "chat.submit",
                OperationRequest.resource_id == str(session.registration_order_id),
            )
            .limit(1)
        )
        if session.registration_order_id
        else None
    )
    calls = []
    turn = 0
    diagnostics = can_see_diagnostics(identity)
    for message in messages:
        if message.author_type == "ASSISTANT":
            turn += 1
            if diagnostics:
                calls.extend({"turn": turn, "call": call} for call in message.tool_calls or [])
    return {
        "session_id": session.id,
        "session_version": session.version,
        "processing": session.active_turn_id is not None
        and session.updated_at >= datetime.now(UTC) - ABANDONED_TURN_AFTER,
        "center_code": context.get("center_code"),
        "messages": _history(db, session.id),
        "calls": calls,
        "material_card": context.get("material_card"),
        "order_id": session.registration_order_id,
        "submission": submission.response["body"] if submission else None,
    }
