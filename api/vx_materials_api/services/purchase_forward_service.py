"""Encaminhamento para compras do material já cadastrado (caminho 2 e seção 8 do modelo).

O encaminhamento registra a demanda com o código existente. Não cria pedido de cadastro, não
altera snapshots de estoque e não comprova pedido ao fornecedor, recebimento nem entrega.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from domain.proposals import canonical_hash
from vx_materials_api.db.models import MaterialMaster, MaterialRequest, PurchaseForward
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import (
    require_permission,
    require_purchasing_action,
    require_resource_scope,
)
from vx_materials_api.services.material_request_service import (
    _audit,
    _find,
    _previous,
    audit_forward,
    claim_idempotency,
    detail,
    forward_snapshot,
    forward_view,
    quantity_text,
    remember_idempotency,
    summary,
)
from vx_materials_api.services.stock_service import _lock_stock, compute_availability, fulfillment


def forward_request(db, caller, request_id, payload, key, correlation_id):
    """Encaminha toda a quantidade pendente quando o centro não tem saldo para atendê-la."""
    role = require_permission(caller, "requests:create")
    digest = canonical_hash({"id": str(request_id), **payload.model_dump(mode="json")})
    previous = _previous(db, caller, "material-request.forward", key, digest)
    if previous:
        return previous.response
    row = _find(db, caller, request_id, lock=True)
    if row.requester_user_id != caller.user_id:
        raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
    if row.version != payload.expected_version:
        raise ApiProblem(409, "VERSION_CONFLICT", "A solicitação mudou. Atualize antes de encaminhar.")
    if row.status != "EM_ATENDIMENTO" or row.material_id is None:
        raise ApiProblem(409, "REQUEST_NOT_IN_SERVICE", "Só é possível encaminhar um material já identificado.")
    material = db.scalar(
        select(MaterialMaster)
        .where(MaterialMaster.id == row.material_id, MaterialMaster.tenant_id == caller.tenant_id)
        .with_for_update(read=True)
    )
    if material is None or material.status != "ATIVO":
        # Obsoleto nunca é encaminhado; bloqueado segue o código ativo indicado no cadastro.
        raise ApiProblem(422, "INACTIVE_MATERIAL", "O material não está ativo; use o código ativo indicado.")
    if material.unit != row.unit:
        raise ApiProblem(422, "UNIT_MISMATCH", "A unidade da solicitação difere da unidade do material.")
    # Mesma ordem da reserva (#239): solicitação bloqueada, depois o saldo do material e centro.
    _lock_stock(db, row.tenant_id, material.id, row.center_code)
    pending = fulfillment(db, row)["pending"]
    if pending <= 0:
        raise ApiProblem(409, "NOTHING_PENDING", "Não há quantidade pendente para encaminhar.")
    state = compute_availability(db, row.tenant_id, material, row.center_code)
    if state["blocked_reason"]:
        # Sem dataset ou com reservas a reconciliar, a falta de saldo não pode ser confirmada.
        raise ApiProblem(409, state["blocked_reason"], "Não é possível confirmar a falta de saldo agora.")
    if state["unconverted_units"]:
        # Saldo em outra unidade não é convertido sem fator conhecido nem tratado como falta.
        raise ApiProblem(
            409, "STOCK_UNIT_UNRESOLVED", "O saldo do centro está em outra unidade; a conversão precisa de revisão."
        )
    if state["available"] >= pending:
        raise ApiProblem(409, "STOCK_AVAILABLE", "O centro tem saldo para atender; a reserva fica com o Almoxarifado.")
    before = summary(row, caller)
    forward = PurchaseForward(
        id=uuid4(),
        tenant_id=row.tenant_id,
        material_request_id=row.id,
        request_version=row.version,
        material_id=row.material_id,
        quantity=pending,
        unit=row.unit,
        center_code=row.center_code,
        status="ENCAMINHADO",
        forwarded_by_user_id=caller.user_id,
    )
    db.add(forward)
    row.version += 1
    db.flush()
    audit_forward(db, caller, role, "PURCHASE_FORWARD_CREATED", forward, None, None, correlation_id)
    reason = f"Encaminhado para compras: {quantity_text(pending)} {row.unit}."
    _audit(db, caller, role, row, before, reason, correlation_id, action="MATERIAL_REQUEST_FORWARDED_TO_PURCHASING")
    response = detail(db, row, caller)
    remember_idempotency(db, caller, "material-request.forward", key, digest, row, response)
    db.commit()
    return response


def _scoped(caller, centers):
    return (
        select(PurchaseForward, MaterialMaster, MaterialRequest)
        .join(MaterialMaster, MaterialMaster.id == PurchaseForward.material_id)
        .join(MaterialRequest, MaterialRequest.id == PurchaseForward.material_request_id)
        .where(PurchaseForward.tenant_id == caller.tenant_id, PurchaseForward.center_code.in_(centers))
    )


def list_forwards(db, caller, *, status=None, center_code=None, cursor=None, limit=20):
    require_permission(caller, "purchasing:read")
    centers = sorted(caller.center_codes)
    if center_code:
        require_purchasing_action(caller, "purchasing:read", center_code)
        centers = [center_code]
    query = _scoped(caller, centers)
    if status:
        query = query.where(PurchaseForward.status == status)
    if cursor:
        query = query.where(PurchaseForward.id > cursor)
    rows = db.execute(query.order_by(PurchaseForward.id).limit(limit + 1)).all()
    return {
        "items": [forward_view(forward, material, request, caller) for forward, material, request in rows[:limit]],
        "next_cursor": str(rows[limit - 1][0].id) if len(rows) > limit else None,
    }


def get_forward(db, caller, forward_id):
    require_permission(caller, "purchasing:read")
    found = db.execute(_scoped(caller, sorted(caller.center_codes)).where(PurchaseForward.id == forward_id)).first()
    if found is None:
        raise ApiProblem(404, "NOT_FOUND", "Encaminhamento não encontrado no seu escopo.")
    return forward_view(*found, caller)


def _claim(db, caller, operation, key, digest):
    previous = claim_idempotency(db, caller, operation, key, digest)
    if previous:
        # O replay revalida o escopo atual: centro revogado não recebe a resposta antiga.
        forward = db.get(PurchaseForward, previous.resource_id)
        if forward is None:
            raise ApiProblem(404, "NOT_FOUND", "Encaminhamento não encontrado.")
        require_resource_scope(caller, forward.tenant_id, [forward.center_code])
    return previous


def _close_if_done(db, caller, role, request, correlation_id):
    """Encerra quando nada falta (`p = 0`, `r = 0`) e nenhum encaminhamento aguarda Compras."""
    if request.status != "EM_ATENDIMENTO":
        return
    awaiting = db.scalar(
        select(PurchaseForward.id).where(
            PurchaseForward.material_request_id == request.id, PurchaseForward.status == "ENCAMINHADO"
        )
    )
    quantities = fulfillment(db, request)
    if awaiting or quantities["reserved"] > 0 or quantities["pending"] > 0:
        return
    before = summary(request, caller)
    request.status = "ENCERRADA"
    request.closure_reason = "ATENDIDA_PARCIAL_COMPRAS" if quantities["delivered"] > 0 else "ENCAMINHADA_COMPRAS"
    request.version += 1
    db.flush()
    _audit(db, caller, role, request, before, None, correlation_id, action="MATERIAL_REQUEST_CLOSED")


def handle_forward(db, caller, forward_id, payload, key, correlation_id, *, accept):
    """Compras aceita ou devolve com motivo; a devolução retorna a quantidade a `p`."""
    require_permission(caller, "purchasing:handle")
    operation = "purchase-forward.accept" if accept else "purchase-forward.return"
    digest = canonical_hash({"id": str(forward_id), **payload.model_dump(mode="json")})
    previous = _claim(db, caller, operation, key, digest)
    if previous:
        return previous.response
    located = db.scalar(
        select(PurchaseForward).where(
            PurchaseForward.id == forward_id,
            PurchaseForward.tenant_id == caller.tenant_id,
            PurchaseForward.center_code.in_(caller.center_codes),
        )
    )
    if located is None:
        raise ApiProblem(404, "NOT_FOUND", "Encaminhamento não encontrado no seu escopo.")
    role = require_purchasing_action(caller, "purchasing:handle", located.center_code)
    # Mesma ordem de bloqueio do encaminhamento e do cancelamento: solicitação, depois parcela.
    request = db.scalar(
        select(MaterialRequest).where(MaterialRequest.id == located.material_request_id).with_for_update()
    )
    forward = db.scalar(select(PurchaseForward).where(PurchaseForward.id == forward_id).with_for_update())
    if forward.version != payload.expected_version:
        raise ApiProblem(409, "VERSION_CONFLICT", "O encaminhamento mudou. Atualize antes de tratar.")
    if forward.status != "ENCAMINHADO":
        raise ApiProblem(409, "FORWARD_CLOSED", "Este encaminhamento já foi tratado ou cancelado.")
    before = forward_snapshot(forward)
    forward.status = "ACEITO" if accept else "DEVOLVIDO"
    forward.reason = None if accept else payload.reason
    forward.handled_by_user_id = caller.user_id
    forward.handled_at = datetime.now(UTC)
    forward.version += 1
    db.flush()
    action = "PURCHASE_FORWARD_ACCEPTED" if accept else "PURCHASE_FORWARD_RETURNED"
    audit_forward(db, caller, role, action, forward, before, forward.reason, correlation_id)
    if accept:
        _close_if_done(db, caller, role, request, correlation_id)
    else:
        request_before = summary(request, caller)
        request.version += 1
        db.flush()
        _audit(
            db,
            caller,
            role,
            request,
            request_before,
            payload.reason,
            correlation_id,
            action="MATERIAL_REQUEST_PURCHASE_RETURNED",
        )
    material = db.get(MaterialMaster, forward.material_id)
    db.refresh(forward)
    response = forward_view(forward, material, request, caller)
    remember_idempotency(db, caller, operation, key, digest, forward, response)
    db.commit()
    return response
