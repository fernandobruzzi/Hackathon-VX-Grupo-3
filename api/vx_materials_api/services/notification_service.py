"""Notificações do solicitante (#249), derivadas da auditoria das próprias solicitações.

Nada é gravado quando uma etapa muda: a notificação é o próprio evento de auditoria de outra pessoa
(ou do sistema) sobre uma solicitação do usuário, sua reserva, seu encaminhamento ou o pedido de
cadastro vinculado. Só o dono vê, e só a leitura é guardada. O total de não lidas vem da mesma
consulta, então o contador reflete o total real.
"""

from sqlalchemy import and_, exists, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from vx_materials_api.db.models import AuditLog, MaterialRequest, NotificationRead
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import require_permission

# Transições que interessam ao solicitante; as próprias ações dele não viram notificação.
LABELS = {
    "STOCK_RESERVED": "Reserva feita no estoque",
    "STOCK_DELIVERED": "Entrega confirmada",
    "STOCK_DELIVERY_REVERSED": "Entrega revertida",
    "STOCK_RESERVATION_CANCELLED": "Reserva cancelada",
    "PURCHASE_FORWARD_CREATED": "Encaminhada para compras",
    "PURCHASE_FORWARD_ACCEPTED": "Demanda aceita por Compras",
    "PURCHASE_FORWARD_RETURNED": "Demanda devolvida por Compras",
    "PURCHASE_FORWARD_CANCELLED": "Encaminhamento cancelado",
    "MATERIAL_REQUEST_CLOSED": "Solicitação encerrada",
    "ORDER_REGISTERED": "Cadastro publicado",
    "ORDER_REJECTED": "Cadastro rejeitado",
    "ORDER_FOUND_EXISTING": "Cadastro resolvido como item já existente",
    "ORDER_INCOMPLETE": "Revisão pendente de resposta",
    "ORDER_TECHNICAL_REOPENED": "Revisão técnica reaberta",
}


def _owned(db, caller):
    rows = db.execute(
        select(MaterialRequest.id, MaterialRequest.protocol_number, MaterialRequest.registration_order_id).where(
            MaterialRequest.tenant_id == caller.tenant_id, MaterialRequest.requester_user_id == caller.user_id
        )
    ).all()
    requests = {str(row.id): f"SM-{row.protocol_number:08d}" for row in rows}
    orders = {str(row.registration_order_id): str(row.id) for row in rows if row.registration_order_id}
    return requests, orders


def _relevant(caller, requests, orders):
    ids = list(requests)
    return and_(
        AuditLog.tenant_id == caller.tenant_id,
        AuditLog.action.in_(LABELS),
        or_(AuditLog.actor_user_id.is_(None), AuditLog.actor_user_id != caller.user_id),
        or_(
            and_(AuditLog.entity_type == "material_request", AuditLog.entity_id.in_(ids)),
            and_(AuditLog.entity_type == "stock_reservation", AuditLog.after_json["request_id"].astext.in_(ids)),
            and_(
                AuditLog.entity_type == "purchase_forward",
                AuditLog.after_json["material_request_id"].astext.in_(ids),
            ),
            and_(AuditLog.entity_type == "registration_order", AuditLog.entity_id.in_(list(orders))),
        ),
    )


def _read(caller):
    return exists().where(NotificationRead.user_id == caller.user_id, NotificationRead.audit_log_id == AuditLog.id)


def _request_of(event, orders) -> str | None:
    if event.entity_type == "material_request":
        return event.entity_id
    if event.entity_type == "registration_order":
        return orders.get(event.entity_id)
    key = "request_id" if event.entity_type == "stock_reservation" else "material_request_id"
    return (event.after_json or {}).get(key)


def list_notifications(db, caller, *, unread_only=False, cursor=None, limit=20):
    require_permission(caller, "requests:read_own")
    requests, orders = _owned(db, caller)
    condition = _relevant(caller, requests, orders)
    unread = db.scalar(select(func.count()).select_from(AuditLog).where(condition, ~_read(caller)))
    query = select(AuditLog, _read(caller).label("read")).where(condition)
    if unread_only:
        query = query.where(~_read(caller))
    if cursor is not None:
        anchor = db.get(AuditLog, cursor)
        if anchor is None:
            raise ApiProblem(422, "INVALID_CURSOR", "Cursor inválido.")
        query = query.where(tuple_(AuditLog.created_at, AuditLog.id) < tuple_(anchor.created_at, anchor.id))
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)).all()
    items = []
    for event, read in rows[:limit]:
        request_id = _request_of(event, orders)
        items.append(
            {
                "id": str(event.id),
                "request_id": request_id,
                "protocol": requests.get(request_id or ""),
                "action": event.action,
                "title": LABELS[event.action],
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
                "read": bool(read),
            }
        )
    return {
        "items": items,
        "unread_count": unread,
        "next_cursor": str(rows[limit - 1][0].id) if len(rows) > limit else None,
    }


def mark_read(db, caller, payload):
    """Marca como lidas as notificações indicadas, ou todas; só as do próprio usuário contam."""
    require_permission(caller, "requests:read_own")
    requests, orders = _owned(db, caller)
    query = select(AuditLog.id).where(_relevant(caller, requests, orders), ~_read(caller))
    if not payload.all:
        if not payload.ids:
            raise ApiProblem(422, "NOTHING_TO_MARK", "Informe as notificações ou marque todas.")
        query = query.where(AuditLog.id.in_(payload.ids))
    ids = list(db.scalars(query))
    if ids:
        db.execute(
            insert(NotificationRead)
            .values([{"user_id": caller.user_id, "audit_log_id": item} for item in ids])
            .on_conflict_do_nothing()
        )
    db.commit()
    return list_notifications(db, caller, unread_only=False, limit=20)
