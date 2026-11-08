"""Valores condicionados a premissas e atendimento real, separados de economia realizada."""

from collections import defaultdict
from decimal import Decimal, localcontext
from uuid import UUID

from sqlalchemy import and_, func, select

from vx_materials_api.db.models import (
    AuditLog,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialMaster,
    StockMovement,
    StockReservation,
)
from vx_materials_api.savings_assumptions import configured_assumptions
from vx_materials_api.schemas.metrics import SavingsComponent


def _money(value):
    return format(value.quantize(Decimal("0.01")), "f")


def _stock_value(db, identity, dataset):
    stock, link, reservation, movement = (
        MaterialInventorySnapshot,
        InventoryConsolidation,
        StockReservation,
        StockMovement,
    )
    owner = func.coalesce(link.primary_material_id, stock.material_id)
    prices = defaultdict(set)
    for material, center, unit, price, factor in db.execute(
        select(
            owner,
            stock.center_code,
            func.coalesce(link.unit, stock.unit),
            stock.unit_price,
            func.coalesce(link.factor, 1),
        )
        .outerjoin(link, and_(link.source_snapshot_id == stock.id, link.tenant_id == stock.tenant_id))
        .where(
            stock.tenant_id == identity.tenant_id,
            stock.dataset_id == dataset,
            stock.center_code.in_(identity.center_codes),
        )
    ):
        prices[(material, center, unit)].add(price / factor if price is not None else None)
    quantities = defaultdict(lambda: Decimal(0))
    for material, center, unit, kind, quantity in db.execute(
        select(
            reservation.material_id,
            reservation.center_code,
            reservation.unit,
            movement.movement_type,
            movement.quantity,
        )
        .join(reservation, movement.reservation_id == reservation.id)
        .where(
            movement.tenant_id == identity.tenant_id,
            reservation.tenant_id == identity.tenant_id,
            movement.dataset_id == dataset,
            reservation.center_code.in_(identity.center_codes),
        )
    ):
        quantities[(material, center, unit)] += quantity if kind == "ENTREGA" else -quantity
    total = Decimal(0)
    for key, quantity in quantities.items():
        if quantity < 0:
            return None, None
        if quantity == 0:
            continue
        known = prices.get(key, set())
        if len(known) != 1 or None in known:
            return str(sum(q > 0 for q in quantities.values())), None
        price = next(iter(known))
        if not price.is_finite() or price < 0:
            return None, None
        total += quantity * price
    return str(sum(q > 0 for q in quantities.values())), _money(total)


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
            if action == "PROPOSAL_APPROVE_TECHNICAL" and (after or {}).get("lot_review"):
                reviewed.add(entity)
            if proposal.proposal_type == "MERGE" and (after or {}).get("status") == "APPLIED":
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
            amount = None
            if len(values) == len(inputs):
                numbers = [Decimal(a.value) for a in values]
                factor = (numbers[0] - numbers[1]) / 60 * numbers[2] if key == "batch_reviews" else numbers[0]
                amount = _money(Decimal(count) * factor)
            components.append(
                SavingsComponent(
                    key=key,
                    label=label,
                    kind="ESTIMATED",
                    count=str(count),
                    count_unit=unit,
                    amount_brl=amount,
                    formula=formula,
                    assumptions=values,
                    unavailable_reason="Premissas quantitativas não registradas para este componente."
                    if amount is None
                    else None,
                )
            )
        count, stock_value = _stock_value(db, identity, dataset)
        components.append(
            SavingsComponent(
                key="stock_fulfilled",
                label="Valor atendido com estoque",
                kind="MEASURED_KIT_VALUE",
                count=count,
                count_unit="itens por centro e unidade",
                amount_brl=stock_value,
                formula=(
                    "quantidade entregue, líquida de reversões × preço unitário original ajustado pelo fator aprovado"
                ),
                unavailable_reason="Preço ausente, heterogêneo ou unidade sem correspondência."
                if stock_value is None
                else None,
            )
        )
        estimates = [Decimal(c.amount_brl) for c in components if c.kind == "ESTIMATED" and c.amount_brl is not None]
        return components, source, _money(sum(estimates, Decimal(0))) if estimates else None
