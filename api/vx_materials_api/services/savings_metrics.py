"""Valores condicionados a premissas e atendimento real, separados de economia realizada."""

from collections import Counter
from datetime import date
from decimal import Decimal, localcontext
from uuid import UUID

from sqlalchemy import select

from vx_materials_api.db.models import (
    AuditLog,
    Dataset,
    MaterialMaster,
    MaterialRequest,
    StockMovement,
    StockReservation,
)
from vx_materials_api.savings_assumptions import configured_assumptions
from vx_materials_api.schemas.metrics import SavingsComponent, StockSavingsEvidence
from vx_materials_api.services.materials_service import _quantity
from vx_materials_api.services.savings_stock_basis import legacy_stock_basis


def _money(value):
    return format(value.quantize(Decimal("0.01")), "f")


def _stock_value(db, identity, dataset_id):
    dataset = db.get(Dataset, dataset_id)

    quantities, value, unknown = Counter(), Decimal(0), False
    prices = []
    rows = list(
        db.execute(
            select(StockMovement, StockReservation)
            .join(StockReservation, StockReservation.id == StockMovement.reservation_id)
            .join(MaterialRequest, MaterialRequest.id == StockReservation.request_id)
            .where(
                StockMovement.tenant_id == identity.tenant_id,
                StockMovement.dataset_id == dataset.id,
                StockReservation.tenant_id == identity.tenant_id,
                StockReservation.center_code.in_(identity.center_codes),
                MaterialRequest.tenant_id == identity.tenant_id,
                MaterialRequest.chat_session_id.is_not(None),
                MaterialRequest.center_code.in_(identity.center_codes),
            )
        )
    )
    delivered = {
        movement.id: [movement, reservation, movement.quantity]
        for movement, reservation in rows
        if movement.movement_type == "ENTREGA"
    }
    for movement, _ in rows:
        if movement.movement_type == "REVERSAO" and movement.reverses_movement_id in delivered:
            delivered[movement.reverses_movement_id][2] -= movement.quantity
    saved = {
        event.entity_id: (event.after_json or {}).get("savings_basis")
        for event in db.scalars(
            select(AuditLog).where(
                AuditLog.tenant_id == identity.tenant_id,
                AuditLog.entity_type == "stock_movement",
                AuditLog.action == "STOCK_DELIVERED",
                AuditLog.entity_id.in_([str(key) for key in delivered]),
            )
        )
    }
    for movement, reservation, quantity in delivered.values():
        if quantity < 0:
            return None, "quantidade inválida", {}, None, []
        if quantity == 0:
            continue
        quantities[reservation.unit] += quantity
        basis = saved.get(str(movement.id))
        if basis is None:
            basis = legacy_stock_basis(
                db,
                identity.tenant_id,
                dataset,
                reservation.material_id,
                reservation.center_code,
                reservation.unit,
                movement.created_at,
            )
        if (
            basis.get("dataset_id") != str(dataset.id)
            or basis.get("material_id") != str(reservation.material_id)
            or basis.get("center_code") != reservation.center_code
            or basis.get("unit") != reservation.unit
            or basis.get("unit_price") is None
        ):
            unknown = True
            continue
        price = Decimal(basis["unit_price"])
        if not price.is_finite() or price < 0:
            unknown = True
            continue
        value += quantity * price
        prices.append(
            StockSavingsEvidence(
                delivery_id=movement.id,
                quantity=_quantity(quantity),
                unit=reservation.unit,
                unit_price=format(price, "f"),
                source=f"Snapshot original {dataset.id}",
                recorded_on=date.fromisoformat(basis["as_of"]),
                snapshot_ids=basis["snapshot_ids"],
                factors=basis["factors"],
            )
        )
    count = _quantity(next(iter(quantities.values()))) if len(quantities) == 1 else "0" if not quantities else None
    unit = next(iter(quantities)) if len(quantities) == 1 else "quantidades por unidade"
    return (
        count,
        unit,
        {key: _quantity(value) for key, value in quantities.items()},
        None if unknown or not prices else _money(value),
        prices,
    )


def savings_metrics(db, identity, dataset, proposals, allowed):
    assumptions, source = configured_assumptions()
    eligible = {str(p.id): p for p in proposals if p.status == "APPLIED"}
    blocked = set()
    reviewed = set()
    if eligible:
        current_status = dict(
            db.execute(
                select(MaterialMaster.id, MaterialMaster.status).where(MaterialMaster.tenant_id == identity.tenant_id)
            ).all()
        )
        for entity, action, before, after in db.execute(
            select(AuditLog.entity_id, AuditLog.action, AuditLog.before_json, AuditLog.after_json).where(
                AuditLog.tenant_id == identity.tenant_id,
                AuditLog.entity_type == "sanitization_proposal",
                AuditLog.entity_id.in_(eligible),
                AuditLog.action.in_(["PROPOSAL_APPROVE_TECHNICAL", "PROPOSAL_APPROVE_FISCAL"]),
            )
        ):
            proposal = eligible[entity]
            if (after or {}).get("changeset_hash") != proposal.changeset_hash:
                continue
            if (
                action == "PROPOSAL_APPROVE_TECHNICAL"
                and (after or {}).get("lot_review")
                and (after or {}).get("technical_review_status") == "APPROVED"
            ):
                reviewed.add(entity)
            if (
                proposal.proposal_type in {"MERGE", "COMPOSITE"}
                and (before or {}).get("status") == "PENDING"
                and (after or {}).get("status") == "APPLIED"
            ):
                originals = {m["id"]: m.get("status") for m in (before or {}).get("materials", [])}
                for material in (after or {}).get("materials", []):
                    key = material.get("id")
                    if (
                        key != str(proposal.primary_material_id)
                        and originals.get(key) == "ATIVO"
                        and material.get("status") == "BLOQUEADO"
                        and current_status.get(UUID(key)) == "BLOQUEADO"
                    ):
                        blocked.add(key)
    reusable = set()
    material_codes = {
        code: str(key)
        for key, code in db.execute(
            select(MaterialMaster.id, MaterialMaster.material_code).where(
                MaterialMaster.tenant_id == identity.tenant_id
            )
        )
    }
    for entity, payload in db.execute(
        select(AuditLog.entity_id, AuditLog.after_json).where(
            AuditLog.tenant_id == identity.tenant_id,
            AuditLog.action == "CHAT_EXISTING_CONFIRMED",
            AuditLog.entity_type == "chat_session",
            AuditLog.after_json["dataset_id"].astext == str(dataset),
            AuditLog.after_json["center_code"].astext.in_(identity.center_codes),
        )
    ):
        material = payload.get("material_id") or material_codes.get(payload.get("material_code"))
        if material in allowed:
            reusable.add(entity)
    components = []
    with localcontext() as context:
        context.prec = 80
        for key, label, count, unit, inputs, formula in [
            (
                "registration_reuse",
                "Reutilizações confirmadas no chat",
                len(reusable),
                "conversas",
                ["registration_cost"],
                "conversas confirmadas × custo hipotético por cadastro",
            ),
            (
                "duplicate_codes",
                "Manutenção anual de códigos desativados",
                len(blocked),
                "códigos",
                ["code_annual_cost"],
                "códigos desativados × custo anual hipotético por código",
            ),
            (
                "batch_reviews",
                "Capacidade de revisão em lote",
                len(reviewed),
                "propostas",
                ["review_minutes_before", "review_minutes_after", "hourly_cost"],
                "propostas × (minutos antes − depois) / 60 × custo da hora",
            ),
        ]:
            values = [assumptions[name] for name in inputs if name in assumptions]
            amount, hours = None, None
            if len(values) == len(inputs):
                numbers = [Decimal(a.value) for a in values]
                if key == "batch_reviews":
                    hours = Decimal(count) * (numbers[0] - numbers[1]) / 60
                    amount = _money(hours * numbers[2])
                else:
                    amount = _money(Decimal(count) * numbers[0])
            components.append(
                SavingsComponent(
                    key=key,
                    label=label,
                    kind="ESTIMATED",
                    count=str(count),
                    count_unit=unit,
                    amount_brl=amount,
                    estimated_hours=_quantity(hours) if hours is not None else None,
                    formula=formula,
                    assumptions=values,
                    unavailable_reason="Premissas quantitativas não registradas para este componente."
                    if amount is None
                    else None,
                )
            )
        count, unit, quantities, stock_value, evidence = _stock_value(db, identity, dataset)
        components.append(
            SavingsComponent(
                key="stock_fulfilled",
                label="Valor atendido com estoque",
                kind="MEASURED_KIT_VALUE",
                count=count,
                count_unit=unit,
                quantities=quantities,
                stock_evidence=evidence,
                amount_brl=stock_value,
                formula=(
                    "quantidade entregue, líquida de reversões × preço unitário original ajustado pelo fator aprovado"
                ),
                unavailable_reason="Preço ausente, heterogêneo ou unidade sem correspondência."
                if stock_value is None
                else None,
            )
        )
        # Anuidade, benefício pontual e capacidade humana permanecem componentes separados.
        return components, source, None
