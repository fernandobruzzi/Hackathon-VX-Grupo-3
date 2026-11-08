"""Evidência imutável do preço original na entrega; alterações futuras não reescrevem a medição."""

from decimal import Decimal, localcontext

from sqlalchemy import Text, cast, or_, select

from vx_materials_api.db.models import (
    AuditLog,
    Dataset,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    SanitizationProposal,
)


def _basis(dataset, material_id, center, unit, rows):
    prices = [price for _, price, _ in rows]
    price = prices[0] if prices and all(value is not None for value in prices) and len(set(prices)) == 1 else None
    if price is not None and (not price.is_finite() or price < 0):
        price = None
    return {
        "dataset_id": str(dataset.id),
        "material_id": str(material_id),
        "center_code": center,
        "unit": unit,
        "unit_price": format(price, "f") if price is not None else None,
        "as_of": dataset.imported_at.date().isoformat(),
        "snapshot_ids": sorted(str(snapshot.id) for snapshot, _, _ in rows),
        "factors": {str(snapshot.id): format(factor, "f") for snapshot, _, factor in rows},
    }


def capture_stock_basis(db, tenant_id, dataset_id, material_id, center, unit):
    """Chamado na transação da entrega. O resultado permanece somente na auditoria privada."""
    dataset = db.get(Dataset, dataset_id)
    rows = []
    with localcontext() as context:
        context.prec = 60
        for snapshot, consolidation in db.execute(
            select(MaterialInventorySnapshot, InventoryConsolidation)
            .outerjoin(
                InventoryConsolidation, InventoryConsolidation.source_snapshot_id == MaterialInventorySnapshot.id
            )
            .where(
                MaterialInventorySnapshot.tenant_id == tenant_id,
                MaterialInventorySnapshot.dataset_id == dataset_id,
                MaterialInventorySnapshot.center_code == center,
                or_(
                    MaterialInventorySnapshot.material_id == material_id,
                    InventoryConsolidation.primary_material_id == material_id,
                ),
            )
        ):
            target = consolidation.primary_material_id if consolidation else snapshot.material_id
            target_unit = consolidation.unit if consolidation else snapshot.unit
            if target != material_id or target_unit != unit:
                continue
            factor = consolidation.factor if consolidation else Decimal(1)
            price = (
                snapshot.unit_price / factor
                if snapshot.unit_price is not None and factor.is_finite() and factor > 0
                else None
            )
            rows.append((snapshot, price, factor))
    return _basis(dataset, material_id, center, unit, rows)


def legacy_stock_basis(db, tenant_id, dataset, material_id, center, unit, delivered_at):
    """Legado sem evidência congelada: só a origem sem transformação anterior é comprovável.

    Os vínculos atuais podem ter sido sobrescritos por merges encadeados. Não são uma
    versão histórica: depois de uma transformação, o legado exige evidência da entrega.
    """
    rows = list(
        db.scalars(
            select(MaterialInventorySnapshot).where(
                MaterialInventorySnapshot.tenant_id == tenant_id,
                MaterialInventorySnapshot.dataset_id == dataset.id,
                MaterialInventorySnapshot.material_id == material_id,
                MaterialInventorySnapshot.center_code == center,
                MaterialInventorySnapshot.unit == unit,
            )
        )
    )
    events = list(
        db.scalars(
            select(AuditLog)
            .join(SanitizationProposal, AuditLog.entity_id == cast(SanitizationProposal.id, Text))
            .where(
                AuditLog.tenant_id == tenant_id,
                SanitizationProposal.tenant_id == tenant_id,
                SanitizationProposal.changeset["dataset_id"].astext == str(dataset.id),
                AuditLog.entity_type == "sanitization_proposal",
                AuditLog.action.in_(["PROPOSAL_APPROVE_TECHNICAL", "PROPOSAL_APPROVE_FISCAL"]),
                AuditLog.after_json["status"].astext == "APPLIED",
            )
        )
    )
    valid = True
    for event in events:
        after = event.after_json or {}
        if event.created_at <= delivered_at and after.get("inventory"):
            affected = {str(item.get("id")) for item in after.get("materials", [])}
            if str(material_id) in affected:
                valid = False
    # Um vínculo sem evento não informa quando a transformação ocorreu.
    known = {event.entity_id for event in events}
    for link in db.scalars(
        select(InventoryConsolidation).where(
            InventoryConsolidation.tenant_id == tenant_id,
            InventoryConsolidation.source_snapshot_id.in_([row.id for row in rows]),
        )
    ):
        if str(link.proposal_id) not in known:
            valid = False
    return _basis(
        dataset, material_id, center, unit, [(row, row.unit_price if valid else None, Decimal(1)) for row in rows]
    )
