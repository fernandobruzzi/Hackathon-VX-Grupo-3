"""Solicitações persistidas, com escopo e idempotência na mesma transação da auditoria."""

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Integer, and_, cast, or_, select, text

from domain.proposals import canonical_hash
from vx_materials_api.db.models import (
    AuditLog,
    ChatSession,
    MaterialMaster,
    MaterialRequest,
    OperationRequest,
    RegistrationOrder,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import (
    has_permission,
    require_center,
    require_conversation_owner,
    require_permission,
    require_resource_scope,
)

QUEUE_STATES = ("EM_IDENTIFICACAO", "AGUARDANDO_CADASTRO")


def scoped_query(caller, *, mine=False):
    require_permission(caller, "requests:read_own")
    visible = MaterialRequest.requester_user_id == caller.user_id
    if not mine and has_permission(caller, "requests:read_queue"):
        visible = or_(visible, MaterialRequest.status.in_(QUEUE_STATES))
    if not mine and has_permission(caller, "requests:read_fiscal"):
        fiscal_orders = select(RegistrationOrder.id).where(
            RegistrationOrder.tenant_id == caller.tenant_id, RegistrationOrder.status == "PENDING_FISCAL"
        )
        visible = or_(
            visible,
            and_(
                MaterialRequest.status == "AGUARDANDO_CADASTRO",
                MaterialRequest.registration_order_id.in_(fiscal_orders),
            ),
        )
    return select(MaterialRequest).where(
        MaterialRequest.tenant_id == caller.tenant_id,
        MaterialRequest.center_code.in_(caller.center_codes),
        visible,
    )


def _find(db, caller, request_id, *, lock=False):
    query = scoped_query(caller).where(MaterialRequest.id == request_id)
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada no seu escopo.")
    return row


def summary(row, caller):
    return {
        "id": str(row.id),
        "protocol": f"SM-{row.protocol_number:08d}",
        "requester_user_id": str(row.requester_user_id),
        "original_text": row.original_text,
        "material_id": str(row.material_id) if row.material_id else None,
        "quantity": format(row.quantity.quantize(Decimal("0.000001")), "f"),
        "unit": row.unit,
        "center_code": row.center_code,
        "status": row.status,
        "closure_reason": row.closure_reason,
        "chat_session_id": str(row.chat_session_id) if row.chat_session_id else None,
        "registration_order_id": str(row.registration_order_id) if row.registration_order_id else None,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "can_cancel": row.requester_user_id == caller.user_id
        and row.status != "ENCERRADA"
        and has_permission(caller, "requests:cancel_own"),
    }


def detail(db, row, caller):
    events = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == caller.tenant_id,
            AuditLog.entity_type == "material_request",
            AuditLog.entity_id == str(row.id),
        )
        .order_by(cast(AuditLog.after_json["version"].astext, Integer), AuditLog.created_at, AuditLog.id)
    )
    return {
        **summary(row, caller),
        "history": [
            {
                "id": str(event.id),
                "actor_user_id": str(event.actor_user_id),
                "before_status": (event.before_json or {}).get("status"),
                "after_status": event.after_json["status"],
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }


def get_request(db, caller, request_id):
    return detail(db, _find(db, caller, request_id), caller)


def list_requests(db, caller, *, mine=False, status=None, cursor=None, limit=20):
    query = scoped_query(caller, mine=mine)
    if status:
        query = query.where(MaterialRequest.status == status)
    if cursor:
        query = query.where(MaterialRequest.id > cursor)
    rows = list(db.scalars(query.order_by(MaterialRequest.id).limit(limit + 1)))
    return {
        "items": [summary(row, caller) for row in rows[:limit]],
        "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
    }


def _previous(db, caller, operation, key, digest):
    # Serializa também a primeira chamada: uma chave concorrente ainda não tem linha para bloquear.
    lock = f"{caller.tenant_id}:{caller.user_id}:{operation}:{key}"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock, 0))"), {"lock": lock})
    previous = db.scalar(
        select(OperationRequest).where(
            OperationRequest.user_id == caller.user_id,
            OperationRequest.operation == operation,
            OperationRequest.idempotency_key == str(key),
        )
    )
    if previous and previous.payload_hash != digest:
        raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "A chave já foi usada com outro conteúdo.")
    if previous:
        # Não devolve uma resposta antiga depois de revogar o centro ou trocar de tenant.
        row = db.get(MaterialRequest, previous.resource_id)
        if row is None:
            raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
        require_resource_scope(caller, row.tenant_id, [row.center_code])
        if row.requester_user_id != caller.user_id:
            raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
    return previous


def _remember(db, caller, operation, key, digest, row, response):
    db.add(
        OperationRequest(
            user_id=caller.user_id,
            operation=operation,
            idempotency_key=str(key),
            payload_hash=digest,
            status="SUCCEEDED",
            resource_id=str(row.id),
            response=response,
        )
    )


def _audit(db, caller, role, row, before, reason, request_id):
    db.add(
        AuditLog(
            tenant_id=caller.tenant_id,
            actor_user_id=caller.user_id,
            actor_type="USER",
            roles_snapshot=list(caller.roles),
            effective_role=role,
            action="MATERIAL_REQUEST_CREATED" if before is None else "MATERIAL_REQUEST_CANCELLED",
            entity_type="material_request",
            entity_id=str(row.id),
            before_json=before,
            after_json=summary(row, caller),
            reason=reason,
            request_id=request_id,
        )
    )
    db.flush()


def _links(db, caller, payload):
    chat = None
    order = None
    if payload.chat_session_id:
        chat = db.scalar(
            select(ChatSession).where(ChatSession.id == payload.chat_session_id).with_for_update(read=True)
        )
        require_conversation_owner(caller, chat)
        if chat.context.get("center_code") != payload.center_code:
            raise ApiProblem(422, "CENTER_MISMATCH", "A conversa pertence a outro centro.")
    if payload.registration_order_id:
        order = db.scalar(
            select(RegistrationOrder)
            .where(
                RegistrationOrder.id == payload.registration_order_id,
                RegistrationOrder.tenant_id == caller.tenant_id,
                RegistrationOrder.requester_user_id == caller.user_id,
                RegistrationOrder.center_code == payload.center_code,
            )
            .with_for_update(read=True)
        )
        if order is None:
            raise ApiProblem(404, "NOT_FOUND", "Pedido de cadastro não encontrado no seu escopo.")
        if order.status in {"REJECTED", "OUT_OF_SCOPE"}:
            raise ApiProblem(422, "ORDER_NOT_LINKABLE", "Este pedido não está disponível para atendimento.")
    if chat and chat.registration_order_id != payload.registration_order_id:
        raise ApiProblem(422, "ORDER_MISMATCH", "O pedido informado não corresponde à conversa.")
    return order


def create_request(db, caller, payload, key, request_id):
    role = require_permission(caller, "requests:create")
    require_center(caller, payload.center_code)
    digest = canonical_hash(payload.model_dump(mode="json"))
    previous = _previous(db, caller, "material-request.create", key, digest)
    if previous:
        return previous.response
    order = _links(db, caller, payload)
    material_id = payload.material_id or (order.material_id if order else None)
    if order and order.material_id and material_id != order.material_id:
        raise ApiProblem(422, "MATERIAL_MISMATCH", "O material difere do pedido de cadastro vinculado.")
    if order and not order.material_id and material_id:
        raise ApiProblem(422, "ORDER_NOT_RESOLVED", "Resolva o pedido de cadastro antes de vincular outro material.")
    unit = payload.unit
    if material_id:
        material = db.scalar(
            select(MaterialMaster)
            .where(
                MaterialMaster.id == material_id,
                MaterialMaster.tenant_id == caller.tenant_id,
            )
            .with_for_update(read=True)
        )
        if material is None:
            raise ApiProblem(404, "NOT_FOUND", "Material não encontrado no seu escopo.")
        if material.status != "ATIVO":
            raise ApiProblem(422, "INACTIVE_MATERIAL", "Selecione um material ativo.")
        if not material.unit or unit != material.unit:
            raise ApiProblem(422, "UNIT_MISMATCH", "Use a unidade do material; conversões não são presumidas.")
    row = MaterialRequest(
        id=uuid4(),
        tenant_id=caller.tenant_id,
        requester_user_id=caller.user_id,
        original_text=payload.original_text,
        quantity=Decimal(payload.quantity),
        unit=unit,
        center_code=payload.center_code,
        material_id=material_id,
        chat_session_id=payload.chat_session_id,
        registration_order_id=payload.registration_order_id,
        status="EM_ATENDIMENTO" if material_id else "AGUARDANDO_CADASTRO" if order else "EM_IDENTIFICACAO",
    )
    db.add(row)
    db.flush()
    _audit(db, caller, role, row, None, None, request_id)
    response = detail(db, row, caller)
    _remember(db, caller, "material-request.create", key, digest, row, response)
    db.commit()
    return response


def cancel_request(db, caller, request_id, payload, key, correlation_id):
    role = require_permission(caller, "requests:cancel_own")
    digest = canonical_hash({"id": str(request_id), **payload.model_dump(mode="json")})
    previous = _previous(db, caller, "material-request.cancel", key, digest)
    if previous:
        return previous.response
    row = _find(db, caller, request_id, lock=True)
    if row.requester_user_id != caller.user_id:
        raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
    if row.version != payload.expected_version:
        raise ApiProblem(409, "VERSION_CONFLICT", "A solicitação mudou. Atualize antes de cancelar.")
    if row.status == "ENCERRADA":
        raise ApiProblem(409, "REQUEST_CLOSED", "A solicitação já está encerrada.")
    before = summary(row, caller)
    row.status, row.closure_reason, row.version = "ENCERRADA", "CANCELADA", row.version + 1
    db.flush()
    _audit(db, caller, role, row, before, payload.reason, correlation_id)
    response = detail(db, row, caller)
    _remember(db, caller, "material-request.cancel", key, digest, row, response)
    db.commit()
    return response
