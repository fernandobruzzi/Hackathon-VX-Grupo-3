"""Envio explícito da ficha persistida do chat para a revisão técnica, sem publicar material."""

from sqlalchemy import select, text

from domain.pdm_validator import validate_pdm
from pipelines.import_orders import STATUS_READY, OrderAnalysis
from vx_materials_api.db.models import ChatMessage, RegistrationOrder
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.chat import ChatSubmitResponse, MaterialCard
from vx_materials_api.security.rbac import require_center, require_permission
from vx_materials_api.services import chat_service, order_service


def submit_chat_order(db, identity, catalog, session_id, expected_version, key, request_id):
    role = require_permission(identity, "orders:create")
    # A publicação usa o mesmo lock por empresa, para não perder um cadastro concorrente.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:t, 1))"), {"t": str(identity.tenant_id)})
    session = chat_service._locked_session(db, identity, session_id)
    context = session.context or {}
    require_center(identity, context.get("center_code"))
    previous, payload_hash = order_service._idempotent(
        db,
        identity,
        "chat.submit",
        key,
        {"session_id": str(session_id), "expected_session_version": expected_version},
    )
    if previous is not None:
        return ChatSubmitResponse.model_validate(previous.response["body"])
    # A ligação é a unicidade do envio, mesmo com uma chave nova após resposta perdida.
    if session.registration_order_id is not None:
        order = db.get(RegistrationOrder, session.registration_order_id)
        if order.status not in {STATUS_READY, "EXISTING"}:
            raise ApiProblem(409, "CHAT_ALREADY_SUBMITTED", "O pedido já está em processamento na revisão.")
        if expected_version != session.version - 1:
            raise ApiProblem(409, "VERSION_CONFLICT", "A versão não corresponde à ficha enviada.")
        response = ChatSubmitResponse(
            session_id=session.id, session_version=session.version, order_id=order.id, status=order.status
        )
        order_service._remember(
            db, identity, "chat.submit", key, payload_hash, order.id, response.model_dump(mode="json")
        )
        db.commit()
        return response
    if session.active_turn_id is not None:
        raise ApiProblem(409, "TURN_IN_PROGRESS", "Aguarde a conclusão do turno antes de enviar.")
    if session.version != expected_version:
        raise ApiProblem(409, "VERSION_CONFLICT", "A ficha mudou. Confira a versão atual antes de enviar.")
    if not context.get("material_card"):
        raise ApiProblem(422, "CHAT_NOT_READY", "Complete a ficha antes de enviar.")
    card = MaterialCard.model_validate(context["material_card"])
    saved = context.get(chat_service.DUPLICATE_CHECK)
    search = saved.get("candidates") if saved and saved.get("signature") == chat_service.card_signature(card) else None
    status = chat_service.turn_status(
        card, search, context.get("dismissed_material_codes", []), context.get("offered_material_codes", [])
    )
    if status != "READY_TO_SUBMIT":
        raise ApiProblem(422, "CHAT_NOT_READY", "A ficha ainda exige informações ou revisão de similares.")
    attributes = {name: value for name, value in card.attributes.items() if value is not None}
    item_name = context.get("item_name")
    validation = validate_pdm(catalog, card.pdm_class_id, attributes, item_name=item_name)
    if not validation.can_submit or validation.identity_key is None or validation.not_applicable_attributes:
        raise ApiProblem(422, "PDM_INVALID", "A ficha não atende ao PDM atual. Revise antes de enviar.")
    # O validador resolve o item único quando o contexto não precisa escolhê-lo.
    item_name = validation.formatted_description.split(";", 1)[0]
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id, ChatMessage.author_type == "USER")
        .order_by(ChatMessage.sequence)
    ).all()
    original_text = "\n".join(message.content for message in messages)
    analysis = OrderAnalysis(
        STATUS_READY,
        card.pdm_class_id,
        item_name,
        attributes,
        (),
        validation.identity_key,
        validation.formatted_description,
        source_text=original_text,
    )
    _, _, version = order_service._rules(catalog)
    status, candidates, missing = order_service._evaluate(db, identity.tenant_id, catalog, analysis, version)
    order = RegistrationOrder(
        tenant_id=identity.tenant_id,
        source_order_id=f"CHAT:{session.id}",
        requester_user_id=identity.user_id,
        origin="CHAT",
        original_text=original_text,
        center_code=context["center_code"],
        pdm_class_id=card.pdm_class_id,
        item_name=item_name,
        attributes=attributes,
        missing_attributes=list(missing),
        candidate_material_ids=candidates,
        status=status,
    )
    db.add(order)
    db.flush()
    session.registration_order_id = order.id
    session.version += 1
    order_service._audit(
        db,
        identity,
        role,
        order,
        "ORDER_SUBMITTED",
        "Enviado explicitamente pelo chat.",
        {"session_id": str(session.id), "status": "READY_TO_SUBMIT"},
        request_id,
    )
    response = ChatSubmitResponse(
        session_id=session.id, session_version=session.version, order_id=order.id, status=status
    )
    order_service._remember(db, identity, "chat.submit", key, payload_hash, order.id, response.model_dump(mode="json"))
    db.commit()
    return response
