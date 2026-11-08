"""Solicitações persistidas, com escopo e idempotência na mesma transação da auditoria."""

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Integer, and_, cast, func, or_, select, text

from domain.proposals import canonical_hash
from vx_materials_api.db.models import (
    AuditLog,
    ChatSession,
    MaterialMaster,
    MaterialRequest,
    OperationRequest,
    PurchaseForward,
    RegistrationOrder,
    StockMovement,
    StockReservation,
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
SIX_PLACES = Decimal("0.000001")


def quantity_text(value) -> str:
    return format(Decimal(value).quantize(SIX_PLACES), "f")


def forward_snapshot(forward) -> dict:
    """Estado auditado do encaminhamento, sem campos derivados do leitor."""
    return {
        "id": str(forward.id),
        "material_request_id": str(forward.material_request_id),
        "request_version": forward.request_version,
        "material_id": str(forward.material_id),
        "quantity": quantity_text(forward.quantity),
        "unit": forward.unit,
        "center_code": forward.center_code,
        "status": forward.status,
        "reason": forward.reason,
        "forwarded_by_user_id": str(forward.forwarded_by_user_id),
        "handled_by_user_id": str(forward.handled_by_user_id) if forward.handled_by_user_id else None,
        "version": forward.version,
    }


def forward_view(forward, material, request, caller) -> dict:
    snapshot = forward_snapshot(forward)
    del snapshot["request_version"]
    return {
        **snapshot,
        "request_protocol": f"SM-{request.protocol_number:08d}",
        "material_code": material.material_code,
        "material_description": material.pdm_description
        or material.original_description_long
        or material.original_description_short,
        "handled_at": forward.handled_at.isoformat() if forward.handled_at else None,
        "created_at": forward.created_at.isoformat(),
        "updated_at": forward.updated_at.isoformat(),
        "can_handle": forward.status == "ENCAMINHADO"
        and forward.center_code in caller.center_codes
        and has_permission(caller, "purchasing:handle"),
    }


def audit_forward(db, caller, role, action, forward, before, reason, request_id):
    db.add(
        AuditLog(
            tenant_id=caller.tenant_id,
            actor_user_id=caller.user_id,
            actor_type="USER",
            roles_snapshot=list(caller.roles),
            effective_role=role,
            action=action,
            entity_type="purchase_forward",
            entity_id=str(forward.id),
            before_json=before,
            after_json=forward_snapshot(forward),
            reason=reason,
            request_id=request_id,
        )
    )


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


def _find(db, caller, request_id, *, lock=False, mine=False):
    query = scoped_query(caller, mine=mine).where(MaterialRequest.id == request_id)
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
        "quantity": quantity_text(row.quantity),
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
    forwards = db.execute(
        select(PurchaseForward, MaterialMaster)
        .join(MaterialMaster, MaterialMaster.id == PurchaseForward.material_id)
        .where(PurchaseForward.material_request_id == row.id)
        .order_by(PurchaseForward.request_version)
    ).all()
    # Import tardio: stock_service importa este módulo para idempotência e resumo.
    from vx_materials_api.services.stock_service import _delivered_by_reservation, fulfillment, reservation_view

    reservations = list(
        db.scalars(
            select(StockReservation)
            .where(StockReservation.request_id == row.id)
            .order_by(StockReservation.created_at, StockReservation.id)
        )
    )
    delivered = _delivered_by_reservation(db, [item.id for item in reservations])
    quantities = fulfillment(db, row)
    return {
        **summary(row, caller),
        "pending_quantity": quantity_text(quantities["pending"]),
        "reserved_quantity": quantity_text(quantities["reserved"]),
        "delivered_quantity": quantity_text(quantities["delivered"]),
        "forwarded_quantity": quantity_text(quantities["forwarded"]),
        # As parcelas de estoque e de compras ficam na mesma solicitação (#242).
        "reservations": [reservation_view(item, delivered.get(item.id, Decimal(0))) for item in reservations],
        "purchase_forwards": [forward_view(forward, material, row, caller) for forward, material in forwards],
        "history": [
            {
                "id": str(event.id),
                "action": event.action,
                "actor_user_id": str(event.actor_user_id),
                "before_status": (event.before_json or {}).get("status"),
                "after_status": event.after_json["status"],
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }


def get_request(db, caller, request_id, *, mine=False):
    return detail(db, _find(db, caller, request_id, mine=mine), caller)


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


def claim_idempotency(db, caller, operation, key, digest):
    """Operação anterior com a mesma chave, ou None; conteúdo diferente com a mesma chave é recusado."""
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
    return previous


def _previous(db, caller, operation, key, digest):
    previous = claim_idempotency(db, caller, operation, key, digest)
    if previous:
        # Não devolve uma resposta antiga depois de revogar o centro ou trocar de tenant.
        row = db.get(MaterialRequest, previous.resource_id)
        if row is None:
            raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
        require_resource_scope(caller, row.tenant_id, [row.center_code])
        if row.requester_user_id != caller.user_id:
            raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
    return previous


def remember_idempotency(db, caller, operation, key, digest, row, response):
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


def _audit(db, caller, role, row, before, reason, request_id, acknowledgement=None, *, action=None, extra=None):
    after = summary(row, caller)
    if acknowledgement:
        after["open_request_acknowledgement"] = acknowledgement
    if extra:
        after.update(extra)
    db.add(
        AuditLog(
            tenant_id=caller.tenant_id,
            actor_user_id=caller.user_id,
            actor_type="USER",
            roles_snapshot=list(caller.roles),
            effective_role=role,
            action=action or ("MATERIAL_REQUEST_CREATED" if before is None else "MATERIAL_REQUEST_CANCELLED"),
            entity_type="material_request",
            entity_id=str(row.id),
            before_json=before,
            after_json=after,
            reason=reason,
            request_id=request_id,
        )
    )
    db.flush()


def _links(db, caller, payload):
    chat = None
    order = None
    if payload.chat_session_id:
        chat = db.scalar(select(ChatSession).where(ChatSession.id == payload.chat_session_id).with_for_update())
        require_conversation_owner(caller, chat)
        from vx_materials_api.services import chat_service

        chat_service._require_history_scope(db, caller, chat)
        if chat.active_turn_id is not None:
            raise ApiProblem(409, "TURN_IN_PROGRESS", "Aguarde a conclusão do turno antes de enviar.")
        if chat.context.get("center_code") != payload.center_code:
            raise ApiProblem(422, "CENTER_MISMATCH", "A conversa pertence a outro centro.")
        if chat_service.material_request_for(db, chat.id) is not None:
            raise ApiProblem(409, "CHAT_ALREADY_SUBMITTED", "Esta conversa já gerou uma solicitação.")
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


def _open_requests(db, caller, material_id, center_code):
    """Solicitações abertas do mesmo material e centro, separando as visíveis ao chamador.

    Toda reserva ativa pertence a uma solicitação não encerrada, então este critério também
    cobre reservas (#239) sem consultar a tabela delas.
    """
    # Serializa criações concorrentes do mesmo material e centro: a segunda vê a primeira.
    lock = f"material-request-open:{caller.tenant_id}:{material_id}:{center_code}"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock, 0))"), {"lock": lock})
    same = and_(
        MaterialRequest.tenant_id == caller.tenant_id,
        MaterialRequest.material_id == material_id,
        MaterialRequest.center_code == center_code,
        MaterialRequest.status != "ENCERRADA",
    )
    total = db.scalar(select(func.count()).select_from(MaterialRequest).where(same))
    if not total:
        return 0, []
    visible = list(db.scalars(scoped_query(caller).where(same).order_by(MaterialRequest.protocol_number)))
    return total, visible


def _open_request_warning(total, visible):
    return {
        "total_count": total,
        "hidden_count": total - len(visible),
        "open_requests": [
            {
                "id": str(row.id),
                "protocol": f"SM-{row.protocol_number:08d}",
                "status": row.status,
                "quantity": format(row.quantity.quantize(Decimal("0.000001")), "f"),
                "unit": row.unit,
                "created_at": row.created_at.isoformat(),
            }
            for row in visible
        ],
    }


def create_request_record(db, caller, payload, request_id):
    """Valida e grava com auditoria; a transação pertence ao comando chamador."""
    role = require_permission(caller, "requests:create")
    require_center(caller, payload.center_code)
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
    acknowledgement = None
    if material_id:
        total, visible = _open_requests(db, caller, material_id, payload.center_code)
        if total and not payload.acknowledge_open_requests:
            # Aviso, não bloqueio: o cliente reenvia com a confirmação para criar mesmo assim.
            raise ApiProblem(
                409,
                "OPEN_REQUESTS_EXIST",
                "Já existe solicitação aberta deste material para este centro. Confirme para criar outra.",
                _open_request_warning(total, visible),
            )
        if total:
            acknowledgement = {
                "total_count": total,
                "hidden_count": total - len(visible),
                "visible_request_ids": [str(row.id) for row in visible],
            }
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
    reason = (
        f"Criada com confirmação de {acknowledgement['total_count']} solicitação(ões) aberta(s) "
        "do mesmo material e centro."
        if acknowledgement
        else None
    )
    _audit(db, caller, role, row, None, reason, request_id, acknowledgement)
    return row


def create_request(db, caller, payload, key, request_id):
    require_permission(caller, "requests:create")
    require_center(caller, payload.center_code)
    content = payload.model_dump(mode="json")
    if not content["acknowledge_open_requests"]:
        # Mantém o hash das chaves gravadas antes da confirmação existir.
        del content["acknowledge_open_requests"]
    digest = canonical_hash(content)
    previous = _previous(db, caller, "material-request.create", key, digest)
    if previous:
        return previous.response
    row = create_request_record(db, caller, payload, request_id)
    response = detail(db, row, caller)
    remember_idempotency(db, caller, "material-request.create", key, digest, row, response)
    db.commit()
    return response


def _release_reservations(db, caller, role, row, reason, correlation_id):
    """Cancelar a solicitação libera suas reservas ATIVA; movimentos já feitos permanecem (seção 5)."""
    reservations = db.scalars(
        select(StockReservation)
        .where(StockReservation.request_id == row.id, StockReservation.status == "ATIVA")
        .order_by(StockReservation.id)
        .with_for_update()
    )
    for reservation in reservations:
        # Só a parte ainda não entregue é liberada; entregas já feitas continuam em `e` (#240).
        delivered = db.scalar(
            select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
                StockMovement.reservation_id == reservation.id, StockMovement.movement_type == "ENTREGA"
            )
        )
        released = quantity_text(Decimal(reservation.quantity) - Decimal(delivered))
        before = {"id": str(reservation.id), "status": reservation.status, "version": reservation.version}
        reservation.status, reservation.version = "CANCELADA", reservation.version + 1
        db.add(
            AuditLog(
                tenant_id=caller.tenant_id,
                actor_user_id=caller.user_id,
                actor_type="USER",
                roles_snapshot=list(caller.roles),
                effective_role=role,
                action="STOCK_RESERVATION_CANCELLED",
                entity_type="stock_reservation",
                entity_id=str(reservation.id),
                before_json={**before, "quantity": format(reservation.quantity, "f")},
                after_json={
                    **before,
                    "status": reservation.status,
                    "version": reservation.version,
                    "quantity": format(reservation.quantity, "f"),
                    "released_quantity": released,
                    "request_id": str(row.id),
                },
                reason=reason,
                request_id=correlation_id,
            )
        )
    db.flush()


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
    # Encaminhamentos ainda não tratados por Compras caem junto; aceitos permanecem (seção 5).
    open_forwards = db.scalars(
        select(PurchaseForward)
        .where(PurchaseForward.material_request_id == row.id, PurchaseForward.status == "ENCAMINHADO")
        .order_by(PurchaseForward.request_version)
        .with_for_update()
    )
    for forward in open_forwards:
        forward_before = forward_snapshot(forward)
        forward.status, forward.reason, forward.version = "CANCELADO", payload.reason, forward.version + 1
        db.flush()
        audit_forward(
            db, caller, role, "PURCHASE_FORWARD_CANCELLED", forward, forward_before, payload.reason, correlation_id
        )
    db.flush()
    _audit(db, caller, role, row, before, payload.reason, correlation_id)
    _release_reservations(db, caller, role, row, payload.reason, correlation_id)
    response = detail(db, row, caller)
    remember_idempotency(db, caller, "material-request.cancel", key, digest, row, response)
    db.commit()
    return response
