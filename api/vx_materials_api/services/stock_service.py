"""Disponibilidade de saldo e reserva transacional (docs/solicitacao-material.md, seções 4.1 e 7).

Disponível = saldo importado do dataset vigente (com as consolidações aprovadas) - reservas ATIVA
- saídas (entregas menos reversões) registradas contra o mesmo dataset, no mesmo centro e na unidade
do material. Os snapshots importados nunca são alterados: reservas e movimentos são registros próprios.
Consultar a disponibilidade só lê.

Entrega, cancelamento de reserva e reversão (seção 7, #240) só inserem movimentos ou mudam o estado
da reserva: a parte reservada e ainda não entregue de uma reserva `ATIVA` conta em `R`, e cada
entrega a move de `R` para `E`, sem mudar `D`.
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
    _audit as request_audit,
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
DELIVER_OPERATION = "stock.deliver"
CANCEL_RESERVATION_OPERATION = "stock.cancel-reservation"
REVERSE_OPERATION = "stock.reverse"
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


def _gross_delivered():
    """Entregas brutas de cada reserva da consulta, sem descontar reversões: o revertido volta a `D`, não à reserva."""
    return (
        select(func.coalesce(func.sum(StockMovement.quantity), 0))
        .where(StockMovement.reservation_id == StockReservation.id, StockMovement.movement_type == "ENTREGA")
        .correlate(StockReservation)
        .scalar_subquery()
    )


def _open_reserved():
    """Soma da parte reservada e ainda não entregue: é o que fica em `R` (ou `r`)."""
    return func.coalesce(func.sum(StockReservation.quantity - _gross_delivered()), 0)


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
    reserved = _decimal(db.scalar(select(_open_reserved()).where(*active)))
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


# Sem unidade ou inativo, nenhum centro atende: não há o que sugerir nem encaminhar.
MATERIAL_BLOCKS = ("INACTIVE_MATERIAL", "MATERIAL_WITHOUT_UNIT")


def other_centers(db, caller, material: MaterialMaster, center: str, needed: Decimal | None = None) -> dict:
    """Disponível em outros centros autorizados quando o destino não atende (#251, decisão D6).

    Só lê: nunca cria transferência, reserva ou movimento. Só percorre `caller.center_codes`, então
    um centro fora do escopo não aparece nem muda `suggest_purchasing`. Sem `needed`, o destino
    atende quando tem algum disponível; com `needed`, quando cobre essa quantidade.
    """
    destination = compute_availability(db, caller.tenant_id, material, center)
    available = max(destination["available"], ZERO)
    sufficient = available >= needed if needed is not None else available > 0
    sufficient = sufficient and destination["blocked_reason"] is None
    alternatives = []
    others = sorted(set(caller.center_codes) - {center})
    usable = destination["blocked_reason"] not in MATERIAL_BLOCKS
    if not sufficient and usable and others and destination["dataset_id"] is not None:
        # Uma leitura do saldo importado escolhe os candidatos: como D ≤ S, sem S positivo não há D.
        grouped, names = inventory_quantities(db, caller.tenant_id, destination["dataset_id"], others, [material.id])
        for key, imported in grouped.items():
            _, code, unit = key
            if unit != material.unit or imported <= 0:
                continue
            labels = sorted(names.get(key, ()))
            state = compute_availability(db, caller.tenant_id, material, code)
            if state["available"] > 0:
                alternatives.append(
                    {
                        "center_code": code,
                        "center_name": labels[0] if labels else None,
                        "available": state["available"],
                        "blocked_reason": state["blocked_reason"],
                    }
                )
    alternatives.sort(key=lambda item: (-item["available"], item["center_code"]))
    return {
        "destination": destination,
        "needed": needed,
        "destination_sufficient": sufficient,
        "alternatives": alternatives,
        "suggest_purchasing": not sufficient and usable and not alternatives,
    }


def other_centers_view(result: dict) -> dict:
    destination = result["destination"]
    unit = destination["material"].unit
    return {
        "destination": availability_view(destination),
        "needed": _quantity(result["needed"]) if result["needed"] is not None else None,
        "destination_sufficient": result["destination_sufficient"],
        "alternatives": [
            {
                "center_code": item["center_code"],
                "center_name": item["center_name"],
                "available": _quantity(item["available"]),
                "unit": unit,
                "reservable": item["blocked_reason"] is None,
                "blocked_reason": item["blocked_reason"],
            }
            for item in result["alternatives"]
        ],
        "suggest_purchasing": result["suggest_purchasing"],
    }


def get_other_centers(db, caller, material_id: UUID, center_code: str, quantity: Decimal | None) -> dict:
    require_permission(caller, "inventory:read")
    require_center(caller, center_code)
    material = db.scalar(
        select(MaterialMaster).where(MaterialMaster.id == material_id, MaterialMaster.tenant_id == caller.tenant_id)
    )
    if material is None:
        raise ApiProblem(404, "NOT_FOUND", "Material não encontrado no seu escopo.")
    return other_centers_view(other_centers(db, caller, material, center_code, quantity))


def fulfillment(db, row: MaterialRequest) -> dict:
    """Parcelas `r`, `e` e `c` da solicitação e o pendente `p = Q − r − e − c` (seção 4.2).

    `r` é só a parte ainda não entregue das reservas `ATIVA`, e `e` desconta as reversões; assim uma
    unidade nunca conta em duas parcelas, e entregar, cancelar ou reverter mantém `r + e + c + p = Q`.
    """
    reserved = _decimal(
        db.scalar(
            select(_open_reserved()).where(StockReservation.request_id == row.id, StockReservation.status == "ATIVA")
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


def _fixed(value) -> str:
    return format(Decimal(value).quantize(Decimal("0.000001")), "f")


def _delivered_by_reservation(db, ids) -> dict:
    """Entregas brutas por reserva (sem reversões), para saber o que ainda pode sair dela."""
    if not ids:
        return {}
    rows = db.execute(
        select(StockMovement.reservation_id, func.sum(StockMovement.quantity))
        .where(StockMovement.reservation_id.in_(ids), StockMovement.movement_type == "ENTREGA")
        .group_by(StockMovement.reservation_id)
    )
    return {reservation_id: Decimal(total) for reservation_id, total in rows}


def _reversed_by_delivery(db, ids) -> dict:
    if not ids:
        return {}
    rows = db.execute(
        select(StockMovement.reverses_movement_id, func.sum(StockMovement.quantity))
        .where(StockMovement.reverses_movement_id.in_(ids))
        .group_by(StockMovement.reverses_movement_id)
    )
    return {movement_id: Decimal(total) for movement_id, total in rows}


def reservation_view(reservation: StockReservation, delivered: Decimal = ZERO) -> dict:
    quantity = Decimal(reservation.quantity)
    return {
        "id": str(reservation.id),
        "request_id": str(reservation.request_id),
        "material_id": str(reservation.material_id),
        "center_code": reservation.center_code,
        "quantity": _fixed(quantity),
        "delivered_quantity": _fixed(delivered),
        # Só a reserva ATIVA ainda compromete saldo; cancelada ou consumida não tem parte aberta.
        "open_quantity": _fixed(quantity - delivered if reservation.status == "ATIVA" else ZERO),
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


def movement_view(movement: StockMovement, reservation: StockReservation, reversed_quantity=ZERO) -> dict:
    delivery = movement.movement_type == "ENTREGA"
    return {
        "id": str(movement.id),
        "reservation_id": str(movement.reservation_id),
        "request_id": str(reservation.request_id),
        "movement_type": movement.movement_type,
        "quantity": _fixed(movement.quantity),
        "reverses_movement_id": str(movement.reverses_movement_id) if movement.reverses_movement_id else None,
        "reversed_quantity": _fixed(reversed_quantity) if delivery else None,
        "unit": reservation.unit,
        "dataset_id": str(movement.dataset_id),
        "created_by_user_id": str(movement.created_by_user_id),
        "created_at": movement.created_at.isoformat(),
    }


def _replay(db, caller, previous, resource=StockReservation):
    found = db.get(resource, UUID(previous.resource_id))
    # Entregas e reversões guardam o movimento; o escopo vem da reserva.
    reservation = db.get(StockReservation, found.reservation_id) if isinstance(found, StockMovement) else found
    if reservation is None:
        raise ApiProblem(404, "NOT_FOUND", "Reserva não encontrada.")
    # Não devolve uma resposta antiga depois de revogar o centro ou trocar de tenant.
    require_resource_scope(caller, reservation.tenant_id, [reservation.center_code])
    return previous.response


def add_reservation(db, caller, role, row, material, state, quantity, request_version, correlation_id, origin=None):
    """Insere a reserva e grava `STOCK_RESERVED`; quem chama já bloqueou e conferiu `quantity ≤ D`.

    `request_version` é a versão da solicitação antes da operação, que quem chama já incrementou.
    `origin` registra quando a reserva vem da confirmação do solicitante na divisão parcial (#242).
    """
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
                **({"origin": origin} if origin else {}),
            },
            request_id=correlation_id,
        )
    )
    db.flush()
    return reservation, after


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
    request_version = row.version
    row.version += 1
    reservation, after = add_reservation(
        db, caller, role, row, material, state, quantity, request_version, correlation_id
    )
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
    reservations = list(
        db.scalars(
            select(StockReservation)
            .where(StockReservation.request_id == row.id)
            .order_by(StockReservation.created_at, StockReservation.id)
        )
    )
    by_id = {item.id: item for item in reservations}
    delivered = _delivered_by_reservation(db, list(by_id))
    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.reservation_id.in_(list(by_id)))
            # No mesmo instante, a entrega vem antes das reversões ("ENTREGA" < "REVERSAO").
            .order_by(StockMovement.created_at, StockMovement.movement_type, StockMovement.id)
        )
    )
    reversed_ = _reversed_by_delivery(db, [item.id for item in movements if item.movement_type == "ENTREGA"])
    return {
        "items": [reservation_view(item, delivered.get(item.id, ZERO)) for item in reservations],
        "movements": [
            movement_view(item, by_id[item.reservation_id], reversed_.get(item.id, ZERO)) for item in movements
        ],
        "fulfillment": fulfillment_view(fulfillment(db, row)),
    }


def _locked_reservation(db, caller, reservation_id: UUID):
    """Reserva no escopo do usuário; bloqueia a solicitação antes da reserva, na ordem usada ao reservar."""
    request_id = db.scalar(
        select(StockReservation.request_id).where(
            StockReservation.id == reservation_id,
            StockReservation.tenant_id == caller.tenant_id,
            StockReservation.center_code.in_(caller.center_codes),
        )
    )
    if request_id is None:
        raise ApiProblem(404, "NOT_FOUND", "Reserva não encontrada no seu escopo.")
    row = db.scalar(select(MaterialRequest).where(MaterialRequest.id == request_id).with_for_update())
    reservation = db.scalar(
        select(StockReservation)
        .where(StockReservation.id == reservation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return row, reservation


def _check_version(row, expected_version: int):
    if row.version != expected_version:
        raise ApiProblem(409, "VERSION_CONFLICT", "A solicitação mudou. Atualize antes de continuar.")


def closure_reason(values: dict, awaiting_purchasing: bool) -> str | None:
    """Motivo de encerramento da seção 5, ou None enquanto algo falta.

    `EM_ATENDIMENTO` → `ENCERRADA` só com `p = 0`, `r = 0` e nenhum encaminhamento aguardando
    Compras. Então `e + c = Q`: tudo entregue (`ATENDIDA_ESTOQUE`), parte entregue e parte com
    Compras (`ATENDIDA_PARCIAL_COMPRAS`) ou tudo com Compras (`ENCAMINHADA_COMPRAS`).
    """
    if awaiting_purchasing or values["pending"] != 0 or values["reserved"] != 0:
        return None
    if values["delivered"] == values["requested"]:
        return "ATENDIDA_ESTOQUE"
    if values["delivered"] > 0 and values["forwarded"] > 0:
        return "ATENDIDA_PARCIAL_COMPRAS"
    if values["delivered"] == 0 and values["forwarded"] == values["requested"]:
        return "ENCAMINHADA_COMPRAS"
    return None


def close_if_fulfilled(db, caller, role, row: MaterialRequest, correlation_id) -> bool:
    """Único ponto de encerramento por atendimento, usado pela entrega e pelo aceite de Compras.

    O encerramento é uma transição própria: incrementa a versão e grava `MATERIAL_REQUEST_CLOSED`
    no histórico da solicitação. Reverter uma entrega depois não reabre a solicitação.
    """
    if row.status != "EM_ATENDIMENTO":
        return False
    awaiting = db.scalar(
        select(PurchaseForward.id)
        .where(PurchaseForward.material_request_id == row.id, PurchaseForward.status == "ENCAMINHADO")
        .limit(1)
    )
    reason = closure_reason(fulfillment(db, row), awaiting is not None)
    if reason is None:
        return False
    before = request_summary(row, caller)
    row.status, row.closure_reason = "ENCERRADA", reason
    row.version += 1
    db.flush()
    request_audit(db, caller, role, row, before, None, correlation_id, action="MATERIAL_REQUEST_CLOSED")
    return True


def _audit(db, caller, role, action, entity_type, entity_id, before, after, correlation_id, reason=None):
    db.add(
        AuditLog(
            tenant_id=caller.tenant_id,
            actor_user_id=caller.user_id,
            actor_type="USER",
            roles_snapshot=list(caller.roles),
            effective_role=role,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            before_json=before,
            after_json=after,
            reason=reason,
            request_id=correlation_id,
        )
    )


def _movement_response(db, caller, row, reservation, movement, after) -> dict:
    delivered = _delivered_by_reservation(db, [reservation.id]).get(reservation.id, ZERO)
    reversed_ = _reversed_by_delivery(db, [movement.id]).get(movement.id, ZERO)
    return {
        "movement": movement_view(movement, reservation, reversed_),
        "reservation": reservation_view(reservation, delivered),
        "request": request_summary(row, caller),
        "fulfillment": fulfillment_view(fulfillment(db, row)),
        "availability": availability_view(after),
    }


def deliver(db, caller, reservation_id: UUID, payload, key, correlation_id) -> dict:
    """Confirma a saída física: move a quantidade de `R` para `E`, sem descontar `D` de novo."""
    require_permission(caller, "stock:deliver")
    digest = canonical_hash({"reservation_id": str(reservation_id), **payload.model_dump(mode="json")})
    previous = claim_idempotency(db, caller, DELIVER_OPERATION, key, digest)
    if previous:
        return _replay(db, caller, previous, StockMovement)
    row, reservation = _locked_reservation(db, caller, reservation_id)
    role = require_stock_action(caller, "stock:deliver", reservation.center_code)
    _check_version(row, payload.expected_version)
    if reservation.status != "ATIVA" or row.status != "EM_ATENDIMENTO":
        raise ApiProblem(
            409, "RESERVATION_NOT_ACTIVE", "Só reservas ativas de solicitações em atendimento são entregues."
        )
    _lock_stock(db, caller.tenant_id, reservation.material_id, reservation.center_code)
    delivered = _delivered_by_reservation(db, [reservation.id]).get(reservation.id, ZERO)
    open_quantity = Decimal(reservation.quantity) - delivered
    quantity = Decimal(payload.quantity)
    if quantity > open_quantity:
        raise ApiProblem(409, "QUANTITY_EXCEEDS_RESERVATION", "A quantidade excede o saldo reservado e não entregue.")
    material = db.get(MaterialMaster, reservation.material_id)
    before = compute_availability(db, caller.tenant_id, material, reservation.center_code)
    if before["dataset_id"] is None:
        raise ApiProblem(409, "NO_INVENTORY_DATASET", "Não há dataset de estoque vigente para registrar a saída.")
    request_before = request_summary(row, caller)
    fulfillment_before = fulfillment_view(fulfillment(db, row))
    reservation_before = reservation_view(reservation, delivered)
    movement = StockMovement(
        id=uuid4(),
        tenant_id=caller.tenant_id,
        reservation_id=reservation.id,
        movement_type="ENTREGA",
        quantity=quantity,
        # A saída desconta do dataset vigente; o snapshot seguinte já a incorpora (D4).
        dataset_id=before["dataset_id"],
        created_by_user_id=caller.user_id,
    )
    db.add(movement)
    if quantity == open_quantity:
        reservation.status = "CONSUMIDA"
    reservation.version += 1
    row.version += 1
    db.flush()
    delivered_version = row.version
    close_if_fulfilled(db, caller, role, row, correlation_id)
    db.refresh(movement)
    db.refresh(reservation)
    after = compute_availability(db, caller.tenant_id, material, reservation.center_code)
    response = _movement_response(db, caller, row, reservation, movement, after)
    _audit(
        db,
        caller,
        role,
        "STOCK_DELIVERED",
        "stock_movement",
        movement.id,
        {
            "reservation": reservation_before,
            "fulfillment": fulfillment_before,
            "request_version": request_before["version"],
        },
        {
            "movement": response["movement"],
            "reservation": response["reservation"],
            "fulfillment": response["fulfillment"],
            "request_version": delivered_version,
            "request_status": row.status,
            "available_before": _quantity(before["available"]),
            "available_after": _quantity(after["available"]),
        },
        correlation_id,
    )
    db.flush()
    remember_idempotency(db, caller, DELIVER_OPERATION, key, digest, movement, response)
    db.commit()
    return response


def cancel_reservation(db, caller, reservation_id: UUID, payload, key, correlation_id) -> dict:
    """Libera só a parte reservada e não entregue; entregas já feitas permanecem."""
    require_permission(caller, "stock:reserve")
    digest = canonical_hash({"reservation_id": str(reservation_id), **payload.model_dump(mode="json")})
    previous = claim_idempotency(db, caller, CANCEL_RESERVATION_OPERATION, key, digest)
    if previous:
        return _replay(db, caller, previous)
    row, reservation = _locked_reservation(db, caller, reservation_id)
    role = require_stock_action(caller, "stock:reserve", reservation.center_code)
    _check_version(row, payload.expected_version)
    if reservation.status != "ATIVA":
        raise ApiProblem(409, "RESERVATION_NOT_ACTIVE", "Só reservas ativas podem ser canceladas.")
    _lock_stock(db, caller.tenant_id, reservation.material_id, reservation.center_code)
    material = db.get(MaterialMaster, reservation.material_id)
    before = compute_availability(db, caller.tenant_id, material, reservation.center_code)
    delivered = _delivered_by_reservation(db, [reservation.id]).get(reservation.id, ZERO)
    released = Decimal(reservation.quantity) - delivered
    reservation_before = reservation_view(reservation, delivered)
    request_version = row.version
    reservation.status = "CANCELADA"
    reservation.version += 1
    row.version += 1
    db.flush()
    db.refresh(reservation)
    after = compute_availability(db, caller.tenant_id, material, reservation.center_code)
    response = {
        "reservation": reservation_view(reservation, delivered),
        "request": request_summary(row, caller),
        "fulfillment": fulfillment_view(fulfillment(db, row)),
        "availability": availability_view(after),
    }
    _audit(
        db,
        caller,
        role,
        "STOCK_RESERVATION_CANCELLED",
        "stock_reservation",
        reservation.id,
        {**reservation_before, "request_version": request_version},
        {
            **response["reservation"],
            "released_quantity": _fixed(released),
            "request_version": row.version,
            "available_before": _quantity(before["available"]),
            "available_after": _quantity(after["available"]),
        },
        correlation_id,
        payload.reason,
    )
    db.flush()
    remember_idempotency(db, caller, CANCEL_RESERVATION_OPERATION, key, digest, reservation, response)
    db.commit()
    return response


def reverse_delivery(db, caller, movement_id: UUID, payload, key, correlation_id) -> dict:
    """Insere uma REVERSAO apontando a entrega: devolve a quantidade a `D` e a `p`, sem editar nada.

    Uma solicitação encerrada não reabre (seção 5): a reversão é registrada, a quantidade volta ao
    saldo do centro e a solicitação continua `ENCERRADA` com o motivo original.
    """
    require_permission(caller, "stock:reverse")
    digest = canonical_hash({"movement_id": str(movement_id), **payload.model_dump(mode="json")})
    previous = claim_idempotency(db, caller, REVERSE_OPERATION, key, digest)
    if previous:
        return _replay(db, caller, previous, StockMovement)
    reservation_id = db.scalar(
        select(StockMovement.reservation_id)
        .join(StockReservation, StockReservation.id == StockMovement.reservation_id)
        .where(
            StockMovement.id == movement_id,
            StockMovement.tenant_id == caller.tenant_id,
            StockReservation.center_code.in_(caller.center_codes),
        )
    )
    if reservation_id is None:
        raise ApiProblem(404, "NOT_FOUND", "Movimento não encontrado no seu escopo.")
    row, reservation = _locked_reservation(db, caller, reservation_id)
    role = require_stock_action(caller, "stock:reverse", reservation.center_code)
    _check_version(row, payload.expected_version)
    delivery = db.get(StockMovement, movement_id)
    if delivery.movement_type != "ENTREGA":
        raise ApiProblem(409, "MOVEMENT_NOT_DELIVERY", "Só entregas podem ser revertidas.")
    _lock_stock(db, caller.tenant_id, reservation.material_id, reservation.center_code)
    material = db.get(MaterialMaster, reservation.material_id)
    before = compute_availability(db, caller.tenant_id, material, reservation.center_code)
    if delivery.dataset_id != before["dataset_id"]:
        # O snapshot novo já incorpora a saída (D4); revertê-la exige a reconciliação da seção 4.4.
        raise ApiProblem(409, "MOVEMENT_FROM_PREVIOUS_DATASET", "A entrega pertence a um dataset de estoque anterior.")
    already = _reversed_by_delivery(db, [delivery.id]).get(delivery.id, ZERO)
    quantity = Decimal(payload.quantity)
    if quantity > Decimal(delivery.quantity) - already:
        raise ApiProblem(409, "QUANTITY_EXCEEDS_REVERSIBLE", "A quantidade excede o que ainda pode ser revertido.")
    fulfillment_before = fulfillment_view(fulfillment(db, row))
    request_version = row.version
    movement = StockMovement(
        id=uuid4(),
        tenant_id=caller.tenant_id,
        reservation_id=reservation.id,
        movement_type="REVERSAO",
        quantity=quantity,
        reverses_movement_id=delivery.id,
        dataset_id=delivery.dataset_id,
        created_by_user_id=caller.user_id,
    )
    db.add(movement)
    row.version += 1
    db.flush()
    db.refresh(movement)
    after = compute_availability(db, caller.tenant_id, material, reservation.center_code)
    response = _movement_response(db, caller, row, reservation, movement, after)
    _audit(
        db,
        caller,
        role,
        "STOCK_DELIVERY_REVERSED",
        "stock_movement",
        movement.id,
        {
            "delivery": movement_view(delivery, reservation, already),
            "fulfillment": fulfillment_before,
            "request_version": request_version,
        },
        {
            "movement": response["movement"],
            "delivery": movement_view(delivery, reservation, already + quantity),
            "fulfillment": response["fulfillment"],
            "request_version": row.version,
            "request_status": row.status,
            "available_before": _quantity(before["available"]),
            "available_after": _quantity(after["available"]),
        },
        correlation_id,
        payload.reason,
    )
    db.flush()
    remember_idempotency(db, caller, REVERSE_OPERATION, key, digest, movement, response)
    db.commit()
    return response
