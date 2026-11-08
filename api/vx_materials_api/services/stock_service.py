"""Disponibilidade de saldo e reserva transacional (docs/solicitacao-material.md, seções 4.1 e 7).

Disponível = saldo importado do dataset vigente (com as consolidações aprovadas) - reservas ATIVA
- saídas (entregas menos reversões) registradas contra o mesmo dataset, no mesmo centro e na unidade
do material. Os snapshots importados nunca são alterados: reservas e movimentos são registros próprios.
Consultar a disponibilidade só lê.
"""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, text

from domain.proposals import canonical_hash
from vx_materials_api.db.models import (
    AuditLog,
    MaterialMaster,
    MaterialRequest,
    PurchaseForward,
    StockMovement,
    StockReservation,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import (
    has_permission,
    require_center,
    require_permission,
    require_resource_scope,
    require_stock_action,
)
from vx_materials_api.services.material_request_service import (
    claim_idempotency,
    remember_idempotency,
)
from vx_materials_api.services.material_request_service import (
    summary as request_summary,
)
from vx_materials_api.services.materials_service import (
    _quantity,
    current_dataset_id,
    inventory_quantities,
)

ZERO = Decimal(0)
RESERVE_OPERATION = "stock.reserve"
# Encaminhamentos que contam em `c` (seção 4.2): devolvidos e cancelados voltam para `p`.
COUNTED_FORWARDS = ("ENCAMINHADO", "ACEITO")


def _decimal(value) -> Decimal:
    return Decimal(value) if value is not None else ZERO


def _signed_movements():
    """Entregas somam, reversões subtraem: `E` do modelo."""
    return func.coalesce(
        func.sum(
            case(
                (StockMovement.movement_type == "ENTREGA", StockMovement.quantity),
                else_=-StockMovement.quantity,
            )
        ),
        0,
    )


def compute_availability(db, tenant_id: UUID, material: MaterialMaster, center: str) -> dict:
    """Saldo `S`, reservado `R`, saídas `E` e disponível `D` de um material principal num centro."""
    dataset = current_dataset_id(db, tenant_id)
    imported = ZERO
    unconverted: list[str] = []
    if dataset is not None:
        grouped, _ = inventory_quantities(db, tenant_id, dataset, [center], [material.id])
        for (_, _, unit), quantity in grouped.items():
            if material.unit and unit == material.unit:
                imported = quantity
            else:
                # Sem fator conhecido, outra unidade não entra no saldo reservável.
                unconverted.append(unit)
    active = (
        StockReservation.tenant_id == tenant_id,
        StockReservation.material_id == material.id,
        StockReservation.center_code == center,
        StockReservation.status == "ATIVA",
    )
    # Reservas ativas contam mesmo se feitas contra um dataset anterior: não somem na troca (D4).
    reserved = _decimal(db.scalar(select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(*active)))
    stale = db.scalar(
        select(func.count()).select_from(StockReservation).where(*active, StockReservation.dataset_id != dataset)
    )
    delivered = ZERO
    if dataset is not None:
        # Saídas de datasets anteriores já estão incorporadas ao snapshot novo (D4).
        delivered = _decimal(
            db.scalar(
                select(_signed_movements())
                .select_from(StockMovement)
                .join(StockReservation, StockReservation.id == StockMovement.reservation_id)
                .where(
                    StockMovement.tenant_id == tenant_id,
                    StockMovement.dataset_id == dataset,
                    StockReservation.material_id == material.id,
                    StockReservation.center_code == center,
                )
            )
        )
    available = imported - reserved - delivered
    blocked = None
    if material.status != "ATIVO":
        blocked = "INACTIVE_MATERIAL"
    elif not material.unit:
        blocked = "MATERIAL_WITHOUT_UNIT"
    elif dataset is None:
        blocked = "NO_INVENTORY_DATASET"
    elif stale:
        # Reservas de um dataset anterior precisam de reconciliação antes de novas reservas.
        blocked = "RECONCILIATION_REQUIRED"
    return {
        "material": material,
        "center_code": center,
        "dataset_id": dataset,
        "imported": imported,
        "reserved": reserved,
        "delivered": delivered,
        "available": available,
        "unconverted_units": sorted(set(unconverted)),
        "blocked_reason": blocked,
    }


def availability_view(state: dict) -> dict:
    material = state["material"]
    return {
        "material_id": str(material.id),
        "material_code": material.material_code,
        "center_code": state["center_code"],
        "unit": material.unit,
        "dataset_id": str(state["dataset_id"]) if state["dataset_id"] else None,
        "imported": _quantity(state["imported"]),
        "reserved": _quantity(state["reserved"]),
        "delivered": _quantity(state["delivered"]),
        # Disponibilidade negativa nunca é oferecida; o valor real fica em imported/reserved/delivered.
        "available": _quantity(max(state["available"], ZERO)),
        "unconverted_units": state["unconverted_units"],
        "reservable": state["blocked_reason"] is None and state["available"] > 0,
        "blocked_reason": state["blocked_reason"],
    }


def get_availability(db, caller, material_id: UUID, center_code: str) -> dict:
    require_permission(caller, "inventory:read")
    require_center(caller, center_code)
    material = db.scalar(
        select(MaterialMaster).where(MaterialMaster.id == material_id, MaterialMaster.tenant_id == caller.tenant_id)
    )
    if material is None:
        raise ApiProblem(404, "NOT_FOUND", "Material não encontrado no seu escopo.")
    return availability_view(compute_availability(db, caller.tenant_id, material, center_code))


def fulfillment(db, row: MaterialRequest) -> dict:
    """Parcelas `r`, `e` e `c` da solicitação e o pendente `p = Q − r − e − c` (seção 4.2)."""
    reserved = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(
                StockReservation.request_id == row.id, StockReservation.status == "ATIVA"
            )
        )
    )
    delivered = _decimal(
        db.scalar(
            select(_signed_movements())
            .select_from(StockMovement)
            .join(StockReservation, StockReservation.id == StockMovement.reservation_id)
            .where(StockReservation.request_id == row.id)
        )
    )
    forwarded = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(PurchaseForward.quantity), 0)).where(
                PurchaseForward.material_request_id == row.id, PurchaseForward.status.in_(COUNTED_FORWARDS)
            )
        )
    )
    requested = Decimal(row.quantity)
    return {
        "requested": requested,
        "reserved": reserved,
        "delivered": delivered,
        "forwarded": forwarded,
        "pending": requested - reserved - delivered - forwarded,
    }


def fulfillment_view(values: dict) -> dict:
    return {key: _quantity(value) for key, value in values.items()}


def reservation_view(reservation: StockReservation) -> dict:
    return {
        "id": str(reservation.id),
        "request_id": str(reservation.request_id),
        "material_id": str(reservation.material_id),
        "center_code": reservation.center_code,
        "quantity": format(Decimal(reservation.quantity).quantize(Decimal("0.000001")), "f"),
        "unit": reservation.unit,
        "status": reservation.status,
        "dataset_id": str(reservation.dataset_id),
        "created_by_user_id": str(reservation.created_by_user_id),
        "version": reservation.version,
        "created_at": reservation.created_at.isoformat(),
        "updated_at": reservation.updated_at.isoformat(),
    }


def _lock_stock(db, tenant_id, material_id, center):
    """Serializa reservas do mesmo material principal e centro até o fim da transação."""
    key = f"stock:{tenant_id}:{material_id}:{center}"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})


def _replay(db, caller, previous):
    reservation = db.get(StockReservation, UUID(previous.resource_id))
    if reservation is None:
        raise ApiProblem(404, "NOT_FOUND", "Reserva não encontrada.")
    # Não devolve uma resposta antiga depois de revogar o centro ou trocar de tenant.
    require_resource_scope(caller, reservation.tenant_id, [reservation.center_code])
    return previous.response


def reserve(db, caller, request_id: UUID, payload, key, correlation_id) -> dict:
    require_permission(caller, "stock:reserve")
    digest = canonical_hash({"request_id": str(request_id), **payload.model_dump(mode="json")})
    previous = claim_idempotency(db, caller, RESERVE_OPERATION, key, digest)
    if previous:
        return _replay(db, caller, previous)
    row = db.scalar(
        select(MaterialRequest)
        .where(
            MaterialRequest.id == request_id,
            MaterialRequest.tenant_id == caller.tenant_id,
            MaterialRequest.center_code.in_(caller.center_codes),
        )
        .with_for_update()
    )
    if row is None:
        raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada no seu escopo.")
    role = require_stock_action(caller, "stock:reserve", row.center_code)
    if row.version != payload.expected_version:
        raise ApiProblem(409, "VERSION_CONFLICT", "A solicitação mudou. Atualize antes de reservar.")
    if row.status != "EM_ATENDIMENTO" or row.material_id is None:
        raise ApiProblem(409, "REQUEST_NOT_IN_FULFILLMENT", "Só solicitações em atendimento recebem reserva.")
    material = db.scalar(
        select(MaterialMaster)
        .where(MaterialMaster.id == row.material_id, MaterialMaster.tenant_id == caller.tenant_id)
        .with_for_update(read=True)
    )
    if material is None or material.status != "ATIVO":
        raise ApiProblem(422, "INACTIVE_MATERIAL", "O material da solicitação não está ativo.")
    if material.unit != row.unit:
        raise ApiProblem(422, "UNIT_MISMATCH", "A unidade da solicitação difere da unidade do material.")
    quantity = Decimal(payload.quantity)
    _lock_stock(db, caller.tenant_id, material.id, row.center_code)
    # Lido depois do bloqueio: cada comando vê as reservas já confirmadas pela transação anterior.
    state = compute_availability(db, caller.tenant_id, material, row.center_code)
    if state["blocked_reason"]:
        raise ApiProblem(409, state["blocked_reason"], "O saldo deste material e centro não pode ser reservado agora.")
    if quantity > state["available"]:
        raise ApiProblem(409, "INSUFFICIENT_STOCK", "A quantidade excede o saldo disponível no centro.")
    # O pendente já desconta encaminhamentos: `r + e + c ≤ Q` vale entre reserva e compras.
    if quantity > fulfillment(db, row)["pending"]:
        raise ApiProblem(409, "QUANTITY_EXCEEDS_PENDING", "A quantidade excede o pendente da solicitação.")
    reservation = StockReservation(
        id=uuid4(),
        tenant_id=caller.tenant_id,
        request_id=row.id,
        material_id=material.id,
        center_code=row.center_code,
        quantity=quantity,
        unit=row.unit,
        status="ATIVA",
        dataset_id=state["dataset_id"],
        created_by_user_id=caller.user_id,
    )
    db.add(reservation)
    request_version = row.version
    row.version += 1
    db.flush()
    db.refresh(reservation)
    after = compute_availability(db, caller.tenant_id, material, row.center_code)
    db.add(
        AuditLog(
            tenant_id=caller.tenant_id,
            actor_user_id=caller.user_id,
            actor_type="USER",
            roles_snapshot=list(caller.roles),
            effective_role=role,
            action="STOCK_RESERVED",
            entity_type="stock_reservation",
            entity_id=str(reservation.id),
            before_json=None,
            after_json={
                **reservation_view(reservation),
                "request_version_before": request_version,
                "request_version_after": row.version,
                "available_before": _quantity(state["available"]),
                "available_after": _quantity(after["available"]),
            },
            request_id=correlation_id,
        )
    )
    db.flush()
    response = {
        "reservation": reservation_view(reservation),
        "request": request_summary(row, caller),
        "fulfillment": fulfillment_view(fulfillment(db, row)),
        "availability": availability_view(after),
    }
    remember_idempotency(db, caller, RESERVE_OPERATION, key, digest, reservation, response)
    db.commit()
    return response


def list_reservations(db, caller, request_id: UUID) -> dict:
    """Reservas da solicitação: para o próprio solicitante ou para quem reserva no centro."""
    row = db.scalar(
        select(MaterialRequest).where(
            MaterialRequest.id == request_id,
            MaterialRequest.tenant_id == caller.tenant_id,
            MaterialRequest.center_code.in_(caller.center_codes),
        )
    )
    owner = row is not None and row.requester_user_id == caller.user_id and has_permission(caller, "requests:read_own")
    if row is None or not (owner or has_permission(caller, "stock:reserve")):
        raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada no seu escopo.")
    reservations = db.scalars(
        select(StockReservation)
        .where(StockReservation.request_id == row.id)
        .order_by(StockReservation.created_at, StockReservation.id)
    )
    return {
        "items": [reservation_view(item) for item in reservations],
        "fulfillment": fulfillment_view(fulfillment(db, row)),
    }
