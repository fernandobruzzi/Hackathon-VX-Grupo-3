"""Reserva e persistência de turnos.

Um turno passa por duas transações curtas, e o Agent é chamado entre elas, sem lock aberto:

1. Reserva: confere dono, versão esperada e turno ativo, e grava `active_turn_id`.
2. Conclusão: só aplica o retorno se o turno reservado ainda for o ativo; grava as duas mensagens,
   mescla o contexto e incrementa a versão.

Se o Agent falhar, a reserva é liberada sem mudar a versão, e nada da mensagem fica gravado.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.pdm_loader import DEFAULT_PDM_VERSION
from vx_materials_api.db.models import ChatMessage, ChatSession
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.chat import AgentRunResponse, ChatMessageRequest, ChatTurnResponse, MaterialCard
from vx_materials_api.security.identity import Identity

NCM_VERSION = "ncm-demo-v1"
# Reserva sem conclusão por mais que isso é tratada como abandonada (queda da API no meio do turno).
ABANDONED_TURN_AFTER = timedelta(seconds=60)
# Chaves que o Agent pode gravar no contexto da sessão. O resto do retorno é descartado.
CONTEXT_KEYS = frozenset(
    {
        "candidate_class_ids",
        "confirmed_attributes",
        "item_name",
        "missing_attributes",
        "pdm_class_id",
        "planner",
        "validation_status",
    }
)


def turn_status(card: MaterialCard) -> str:
    """Status do turno, derivado pela API da ficha, nunca informado pelo Agent.

    Pronto para envio exige ficha válida e duplicidade verificada sem item igual. Se a verificação
    falhou, o pedido continua aguardando, mesmo com a ficha completa.
    """
    if card.existing is not None:
        return "EXISTING"
    if card.validation_status == "OUT_OF_SCOPE":
        return "OUT_OF_SCOPE"
    if card.validation_status == "VALID" and card.duplicate_check_status == "NO_MATCH":
        return "READY_TO_SUBMIT"
    return "NEEDS_INPUT"


@dataclass(frozen=True)
class Reservation:
    session_id: uuid.UUID
    turn_id: uuid.UUID
    session_version: int
    agent_payload: dict[str, Any]


def _conflict(code: str, message: str) -> ApiProblem:
    return ApiProblem(409, code, message)


def _locked_session(db: Session, identity: Identity, session_id: uuid.UUID) -> ChatSession:
    session = db.scalar(
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.tenant_id == identity.tenant_id)
        .with_for_update()
    )
    # Conversa de outra pessoa responde como inexistente.
    if session is None or session.owner_user_id != identity.user_id:
        raise ApiProblem(404, "NOT_FOUND", "Conversa não encontrada.")
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


def reserve_turn(db: Session, identity: Identity, request: ChatMessageRequest) -> Reservation:
    turn_id = uuid.uuid4()
    if request.session_id is None:
        if request.expected_session_version != 0:
            raise _conflict("VERSION_CONFLICT", "Uma conversa nova começa na versão 0.")
        session = ChatSession(
            tenant_id=identity.tenant_id,
            owner_user_id=identity.user_id,
            context={},
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
        # `updated_at` muda junto (onupdate) e marca o horário da reserva.
        session.active_turn_id = turn_id

    context = session.context or {}
    payload = {
        "turn_id": str(turn_id),
        "session_id": str(session.id),
        "session_version": session.version,
        "message": request.message,
        "context": {
            "pdm_version": session.pdm_version or DEFAULT_PDM_VERSION,
            "ncm_version": session.ncm_version or NCM_VERSION,
            "center_code": request.center_code,
            "history": _history(db, session.id),
            "confirmed_attributes": context.get("confirmed_attributes", {}),
        },
    }
    reservation = Reservation(session.id, turn_id, session.version, payload)
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
) -> ChatTurnResponse:
    session = _locked_session(db, identity, reservation.session_id)
    if session.active_turn_id != reservation.turn_id or session.version != reservation.session_version:
        raise _conflict("TURN_SUPERSEDED", "O turno foi substituído por outro.")

    last = db.scalar(select(func.max(ChatMessage.sequence)).where(ChatMessage.session_id == session.id)) or 0
    tool_calls = [call.model_dump(mode="json") for call in result.tool_calls]
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
    patch = {key: value for key, value in result.context_patch.items() if key in CONTEXT_KEYS}
    status = turn_status(result.material_card)
    # O envio só é liberado quando a API concorda que o pedido está pronto.
    material_card = result.material_card.model_copy(update={"can_submit": status == "READY_TO_SUBMIT"})
    card = material_card.model_dump(mode="json")
    session.context = {**(session.context or {}), **patch, "material_card": card}
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
        tool_calls=result.tool_calls,
        material_card=material_card,
    )
