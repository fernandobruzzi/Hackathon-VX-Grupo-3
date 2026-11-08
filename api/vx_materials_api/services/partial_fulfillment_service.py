"""Atendimento parcial: reserva do disponível e encaminhamento do restante (caminho 3, decisão D1).

O solicitante escolhe, na própria solicitação, entre `PARTIAL` (padrão: reservar até `D` e
encaminhar o restante para compras) e `PURCHASING_ONLY` (encaminhar todo o pendente, sem reserva).
Consultar a divisão só lê. Ao confirmar, a divisão é recalculada dentro dos bloqueios da reserva:
nunca se reserva mais que o disponível nem se encaminha uma quantidade já reservada.

A parcela de estoque nasce da confirmação do solicitante, com quantidade calculada pelo servidor;
isso não concede `stock:reserve`. O solicitante continua sem reservar quantidades livres, entregar,
cancelar reservas ou reverter entregas, que seguem com o Almoxarifado (seção 9).
"""

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from domain.proposals import canonical_hash
from vx_materials_api.db.models import MaterialMaster, PurchaseForward
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import require_permission
from vx_materials_api.services.material_request_service import (
    _audit,
    _find,
    _previous,
    audit_forward,
    detail,
    quantity_text,
    remember_idempotency,
    summary,
)
from vx_materials_api.services.purchase_forward_service import (
    locked_shortage,
    request_problem,
    shortage_problem,
)
from vx_materials_api.services.stock_service import add_reservation, compute_availability, fulfillment

ZERO = Decimal(0)
OPERATION = "material-request.fulfillment"
DEFAULT_OPTION = "PARTIAL"
# Registrado na reserva: a quantidade veio da escolha do solicitante, não de uma reserva livre.
RESERVATION_ORIGIN = "REQUESTER_PARTIAL_CONFIRMATION"


def split(option: str, pending: Decimal, available: Decimal) -> tuple[Decimal, Decimal]:
    """`(reservar, encaminhar)` para o pendente `p` e o disponível `D`, com soma sempre igual a `p`."""
    reserve = min(max(available, ZERO), pending) if option == "PARTIAL" else ZERO
    return reserve, pending - reserve


def _split_view(option, pending, available):
    reserve, forward = split(option, pending, available)
    return {"option": option, "reserve_quantity": quantity_text(reserve), "forward_quantity": quantity_text(forward)}


def preview(db, caller, request_id) -> dict:
    """Divisão que seria aplicada agora; não bloqueia, não reserva e não encaminha."""
    require_permission(caller, "requests:create")
    require_permission(caller, "inventory:read")
    row = _find(db, caller, request_id)
    if row.requester_user_id != caller.user_id:
        raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
    material = None
    if row.material_id is not None:
        material = db.scalar(
            select(MaterialMaster).where(
                MaterialMaster.id == row.material_id, MaterialMaster.tenant_id == caller.tenant_id
            )
        )
    values = fulfillment(db, row)
    available = ZERO
    problem = request_problem(row, material)
    if problem is None:
        state = compute_availability(db, row.tenant_id, material, row.center_code)
        available = max(state["available"], ZERO)
        problem = shortage_problem(values["pending"], state)
    options = []
    if problem is None:
        # Sem saldo algum, reservar o disponível seria encaminhar tudo: só a opção integral aparece.
        choices = ("PARTIAL", "PURCHASING_ONLY") if available > 0 else ("PURCHASING_ONLY",)
        options = [_split_view(option, values["pending"], available) for option in choices]
    return {
        "request_id": str(row.id),
        "request_version": row.version,
        "unit": row.unit,
        "center_code": row.center_code,
        **{key: quantity_text(value) for key, value in values.items()},
        "available": quantity_text(available),
        "blocked_reason": problem[1] if problem else None,
        "default_option": options[0]["option"] if options else None,
        "options": options,
    }


def confirm(db, caller, request_id, payload, key, correlation_id) -> dict:
    """Grava as duas parcelas numa transação, com a divisão recalculada dentro do bloqueio."""
    role = require_permission(caller, "requests:create")
    digest = canonical_hash({"id": str(request_id), **payload.model_dump(mode="json")})
    previous = _previous(db, caller, OPERATION, key, digest)
    if previous:
        return previous.response
    # Mesmas verificações e ordem de bloqueio do encaminhamento integral (#241): dono, versão,
    # material ativo, unidade, saldo confiável e falta confirmada (`D < p`).
    row, material, state, pending = locked_shortage(db, caller, request_id, payload.expected_version)
    reserve, forward_quantity = split(payload.option, pending, state["available"])
    before = summary(row, caller)
    request_version = row.version
    # Uma transição da solicitação para as duas parcelas: uma versão, um evento no histórico.
    row.version += 1
    reservation = None
    if reserve > 0:
        reservation, _ = add_reservation(
            db,
            caller,
            role,
            row,
            material,
            state,
            reserve,
            request_version,
            correlation_id,
            origin=RESERVATION_ORIGIN,
        )
    forward = PurchaseForward(
        id=uuid4(),
        tenant_id=row.tenant_id,
        material_request_id=row.id,
        # Unicidade por versão (#241): outra confirmação da mesma versão nunca duplica a parcela.
        request_version=request_version,
        material_id=row.material_id,
        quantity=forward_quantity,
        unit=row.unit,
        center_code=row.center_code,
        status="ENCAMINHADO",
        forwarded_by_user_id=caller.user_id,
    )
    db.add(forward)
    db.flush()
    audit_forward(db, caller, role, "PURCHASE_FORWARD_CREATED", forward, None, None, correlation_id)
    split_record = {
        "option": payload.option,
        "pending_before": quantity_text(pending),
        "available_at_confirmation": quantity_text(max(state["available"], ZERO)),
        "reserved_quantity": quantity_text(reserve),
        "forwarded_quantity": quantity_text(forward_quantity),
        "reservation_id": str(reservation.id) if reservation else None,
        "purchase_forward_id": str(forward.id),
    }
    if reservation:
        action = "MATERIAL_REQUEST_PARTIAL_FULFILLMENT"
        reason = (
            f"Atendimento parcial: {quantity_text(reserve)} {row.unit} reservado(s) do estoque e "
            f"{quantity_text(forward_quantity)} {row.unit} encaminhado(s) para compras."
        )
    else:
        action = "MATERIAL_REQUEST_FORWARDED_TO_PURCHASING"
        reason = f"Encaminhado para compras: {quantity_text(forward_quantity)} {row.unit}."
        if payload.option == "PARTIAL":
            reason += " Sem saldo disponível na confirmação, nada foi reservado."
    _audit(
        db, caller, role, row, before, reason, correlation_id, action=action, extra={"fulfillment_split": split_record}
    )
    response = {
        "option": payload.option,
        "reserved_quantity": split_record["reserved_quantity"],
        "forwarded_quantity": split_record["forwarded_quantity"],
        "available_at_confirmation": split_record["available_at_confirmation"],
        "reservation_id": split_record["reservation_id"],
        "purchase_forward_id": split_record["purchase_forward_id"],
        "request": detail(db, row, caller),
    }
    remember_idempotency(db, caller, OPERATION, key, digest, row, response)
    db.commit()
    return response
