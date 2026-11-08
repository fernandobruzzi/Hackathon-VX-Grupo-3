"""Confirmação da necessidade a partir da ficha salva, sem publicar ou movimentar estoque."""

from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select, text

from vx_materials_api.db.models import ChatMessage, MaterialMaster, RegistrationOrder
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.chat import ChatMaterialRequestResponse, MaterialCard
from vx_materials_api.schemas.material_requests import CreateMaterialRequest
from vx_materials_api.security.rbac import require_center, require_permission
from vx_materials_api.services import chat_order_service, chat_service, material_request_service, order_service


def _response(db, caller, session, row):
    return ChatMaterialRequestResponse(
        session_id=session.id,
        session_version=session.version,
        material_request=material_request_service.detail(db, row, caller),
    )


def submit_request(db, caller, catalog, session_id, payload, key, request_id):
    require_permission(caller, "requests:create")
    # Mesma ordem da conclusão dos turnos e dos escritores de catálogo.
    for seed in (0, 1):
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, :seed))"),
            {"tenant": str(caller.tenant_id), "seed": seed},
        )
    session = chat_service._locked_session(db, caller, session_id)
    chat_service._require_history_scope(db, caller, session)
    context = session.context or {}
    require_center(caller, context.get("center_code"))
    previous, digest = order_service._idempotent(
        db, caller, "chat.request-material", key, {"session_id": str(session_id), **payload.model_dump(mode="json")}
    )
    if previous:
        return ChatMaterialRequestResponse.model_validate(previous.response["body"])
    existing_request = chat_service.material_request_for(db, session_id)
    if existing_request:
        if (
            payload.expected_session_version != session.version - 1
            or Decimal(payload.quantity) != existing_request.quantity
            or payload.unit != existing_request.unit
        ):
            raise ApiProblem(409, "CHAT_ALREADY_SUBMITTED", "Esta conversa já gerou uma solicitação com outros dados.")
        response = _response(db, caller, session, existing_request)
        order_service._remember(
            db, caller, "chat.request-material", key, digest, existing_request.id, response.model_dump(mode="json")
        )
        db.commit()
        return response
    if session.registration_order_id is not None:
        raise ApiProblem(409, "CHAT_ALREADY_SUBMITTED", "Esta conversa já gerou um pedido de cadastro.")
    if session.active_turn_id is not None:
        raise ApiProblem(409, "TURN_IN_PROGRESS", "Aguarde a resposta do chat antes de confirmar.")
    if session.version != payload.expected_session_version:
        raise ApiProblem(409, "VERSION_CONFLICT", "A ficha mudou. Confira a resposta atual antes de confirmar.")
    if not context.get("material_card"):
        raise ApiProblem(422, "CHAT_NOT_READY", "Descreva o material antes de confirmar a solicitação.")
    card = MaterialCard.model_validate(context["material_card"])
    saved = context.get(chat_service.DUPLICATE_CHECK)
    if saved and saved.get("catalog_proof") != chat_service._catalog_proof(
        db, caller.tenant_id, chat_service.cache_rules(catalog)
    ):
        raise ApiProblem(409, "CATALOG_CHANGED", "O catálogo mudou. Atualize a conversa antes de confirmar.")
    if saved and saved.get("signature") != chat_service.card_signature(card):
        raise ApiProblem(409, "CHAT_VERIFICATION_CHANGED", "A identificação mudou. Atualize a conversa.")
    candidates = saved.get("candidates") if saved else None
    code = ((saved or {}).get("existing") or {}).get("material_code")
    status = chat_service.turn_status(
        card, candidates, context.get("dismissed_material_codes", []), context.get("offered_material_codes", []), code
    )
    material_id = None
    order_id = None
    if status == "EXISTING":
        # Escolher um similar não elimina uma dúvida técnica de identidade.
        verified = any(
            (c.get("identity_verified") or c.get("explicit_code_confirmed")) and chat_service._code_to_use(c) == code
            for c in candidates or []
        )
        if verified:
            material = db.scalar(
                select(MaterialMaster)
                .where(
                    MaterialMaster.tenant_id == caller.tenant_id,
                    MaterialMaster.material_code == code,
                    MaterialMaster.status == "ATIVO",
                )
                .with_for_update(read=True)
            )
            if material is None:
                raise ApiProblem(409, "CATALOG_CHANGED", "O código ativo mudou. Atualize a conversa.")
            material_id = material.id
    elif status == "READY_TO_SUBMIT":
        # Cadastro e solicitação compartilham a transação; qualquer falha desfaz ambos.
        submitted = chat_order_service.submit_chat_order(
            db, caller, catalog, session_id, payload.expected_session_version, key, request_id, commit=False
        )
        order = db.get(RegistrationOrder, submitted.order_id)
        if submitted.status != "READY_FOR_REVIEW" or order.candidate_material_ids or order.missing_attributes:
            raise ApiProblem(409, "CATALOG_CHANGED", "A existência do material exige nova verificação no chat.")
        order_id = submitted.order_id
    messages = db.scalars(
        select(ChatMessage.content)
        .where(ChatMessage.session_id == session_id, ChatMessage.author_type == "USER")
        .order_by(ChatMessage.sequence)
    ).all()
    try:
        request_payload = CreateMaterialRequest(
            acknowledge_open_requests=payload.acknowledge_open_requests,
            original_text="\n".join(messages),
            quantity=payload.quantity,
            unit=payload.unit,
            center_code=context["center_code"],
            material_id=material_id,
            registration_order_id=order_id,
            chat_session_id=session_id,
        )
    except ValidationError as error:
        raise ApiProblem(
            422,
            "REQUEST_SOURCE_INVALID",
            "A descrição salva precisa conter texto e ter até 10.000 caracteres. "
            "Inicie uma nova conversa com um resumo.",
        ) from error
    row = material_request_service.create_request_record(db, caller, request_payload, request_id)
    session.version = payload.expected_session_version + 1
    db.flush()
    response = _response(db, caller, session, row)
    order_service._remember(db, caller, "chat.request-material", key, digest, row.id, response.model_dump(mode="json"))
    db.commit()
    return response
