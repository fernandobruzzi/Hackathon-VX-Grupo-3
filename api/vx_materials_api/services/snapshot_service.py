"""Snapshot posterior: a base como ficou depois das propostas aplicadas, para comparar com o original.

O snapshot lê a master atual e confere que cada diferença em relação ao registro importado vem de uma
proposta APPLIED do mesmo dataset. Uma diferença sem proposta aplicada impede o snapshot: a comparação
só pode mostrar o que foi aprovado. O valor do estoque é recalculado pelas consolidações e precisa
bater com o original; unificar códigos move saldos, não cria nem apaga valor.
"""

import hashlib
import json
import uuid
from collections import defaultdict
from decimal import Context, Decimal

from sqlalchemy import insert, select, text

from vx_materials_api.db.models import (
    AuditLog,
    Dataset,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialMaster,
    OperationRequest,
    QualitySnapshot,
    QualitySnapshotItem,
    SanitizationProposal,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.metrics import QualitySnapshotOut, QualitySnapshotRequest
from vx_materials_api.security.rbac import require_permission

PERMISSION = "batch:run"
OPERATION = "dashboard.snapshot"
EXPORT_FILE = "quality_snapshot.json"
FIELDS = ("status", "ncm", "unit")
_RAW_FIELDS = {"status": "STATUS", "ncm": "NCM", "unit": "UNIDADE_MEDIDA"}
# Precisão folgada para recompor preço e quantidade convertidos sem perder centavos.
_EXACT = Context(prec=60)
_CENTS = Decimal("0.01")
_SAMPLE = 10


def _empty_to_none(value):
    value = (value or "").strip()
    return value or None


def select_dataset(db, identity, dataset_id: uuid.UUID | None = None) -> uuid.UUID:
    query = select(Dataset.id).where(Dataset.tenant_id == identity.tenant_id)
    if dataset_id is not None:
        query = query.where(Dataset.id == dataset_id)
    dataset = db.scalar(query.order_by(Dataset.imported_at.desc(), Dataset.id.desc()).limit(1))
    if dataset is None:
        raise ApiProblem(404, "NOT_FOUND", "Nenhum dataset importado disponível.")
    return dataset


def applied_proposals(db, tenant_id, dataset_id) -> list[SanitizationProposal]:
    return list(
        db.scalars(
            select(SanitizationProposal)
            .where(
                SanitizationProposal.tenant_id == tenant_id,
                SanitizationProposal.status == "APPLIED",
                SanitizationProposal.changeset["schema_version"].astext == "proposal-v1",
                SanitizationProposal.changeset["dataset_id"].astext == str(dataset_id),
            )
            .order_by(SanitizationProposal.id)
        )
    )


def _baseline(db, tenant_id, dataset_id) -> dict[uuid.UUID, dict]:
    """Registro importado de cada material: a primeira linha do arquivo original, como no dashboard."""
    rows = db.execute(
        select(MaterialInventorySnapshot.material_id, MaterialInventorySnapshot.raw_record)
        .where(MaterialInventorySnapshot.tenant_id == tenant_id, MaterialInventorySnapshot.dataset_id == dataset_id)
        .order_by(MaterialInventorySnapshot.material_id, MaterialInventorySnapshot.source_line)
    )
    baseline = {}
    for material_id, raw in rows:
        if material_id not in baseline:
            baseline[material_id] = {field: _empty_to_none(raw.get(key)) for field, key in _RAW_FIELDS.items()}
    return baseline


def _inventory_totals(db, tenant_id, dataset_id) -> tuple[Decimal, Decimal, int]:
    """Valor original e valor depois das consolidações, linha a linha, sem perder nem repetir saldo."""
    rows = db.execute(
        select(
            MaterialInventorySnapshot.quantity,
            MaterialInventorySnapshot.unit_price,
            MaterialInventorySnapshot.total_value,
            InventoryConsolidation.factor,
        )
        .outerjoin(
            InventoryConsolidation,
            (InventoryConsolidation.source_snapshot_id == MaterialInventorySnapshot.id)
            & (InventoryConsolidation.tenant_id == MaterialInventorySnapshot.tenant_id),
        )
        .where(MaterialInventorySnapshot.tenant_id == tenant_id, MaterialInventorySnapshot.dataset_id == dataset_id)
    ).all()
    before = after = Decimal(0)
    missing = 0
    for quantity, price, total, factor in rows:
        if total is None or price is None:
            missing += 1
            continue
        factor = factor or Decimal(1)
        before = _EXACT.add(before, total)
        converted = _EXACT.multiply(_EXACT.multiply(quantity, factor), _EXACT.divide(price, factor))
        after = _EXACT.add(after, converted)
    return before, after, missing


def create_snapshot(
    db, identity, store, request: QualitySnapshotRequest, idempotency_key: uuid.UUID, request_id: str | None = None
) -> QualitySnapshotOut:
    role = require_permission(identity, PERMISSION)
    tenant_id = identity.tenant_id
    # Um snapshot por vez no tenant: a leitura da master e das propostas precisa ser consistente.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 0))"), {"tenant": str(tenant_id)})
    payload_hash = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    previous = db.scalar(
        select(OperationRequest).where(
            OperationRequest.user_id == identity.user_id,
            OperationRequest.operation == OPERATION,
            OperationRequest.idempotency_key == str(idempotency_key),
        )
    )
    if previous is not None:
        if previous.payload_hash != payload_hash:
            raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "A chave já foi usada com outra solicitação.")
        return QualitySnapshotOut.model_validate(previous.response["body"])
    dataset_id = select_dataset(db, identity, request.dataset_id)
    baseline = _baseline(db, tenant_id, dataset_id)
    current = {
        material.id: material
        for material in db.scalars(
            select(MaterialMaster).where(MaterialMaster.tenant_id == tenant_id, MaterialMaster.id.in_(baseline))
        )
    }
    applied = applied_proposals(db, tenant_id, dataset_id)
    touched: dict[uuid.UUID, list[str]] = defaultdict(list)
    for proposal in applied:
        for member in proposal.members or []:
            try:
                touched[uuid.UUID(member["material_id"])].append(str(proposal.id))
            except (KeyError, TypeError, ValueError):
                continue

    items, changes, untraceable = [], [], []
    for material_id, before in baseline.items():
        material = current[material_id]
        after = {"status": material.status, "ncm": material.ncm, "unit": material.unit}
        changed = [field for field in FIELDS if after[field] != before[field]]
        proposals = sorted(set(touched.get(material_id, ())))
        if changed and not proposals:
            untraceable.append(material.material_code)
        items.append({"material_id": material_id, "tenant_id": tenant_id, **after, "proposal_ids": proposals})
        if changed:
            changes.append(
                {
                    "material_code": material.material_code,
                    "fields": changed,
                    "before": {field: before[field] for field in changed},
                    "after": {field: after[field] for field in changed},
                    "proposal_ids": proposals,
                }
            )
    if untraceable:
        raise ApiProblem(
            409,
            "UNTRACEABLE_CHANGES",
            "Há materiais alterados sem proposta aplicada. O snapshot só registra alterações aprovadas.",
            material_codes=sorted(untraceable)[:_SAMPLE],
            count=len(untraceable),
        )

    value_before, value_after, missing_values = _inventory_totals(db, tenant_id, dataset_id)
    conserved = missing_values == 0 and value_before.quantize(_CENTS) == value_after.quantize(_CENTS)
    snapshot_id = uuid.uuid4()
    applied_ids = [str(proposal.id) for proposal in applied]
    summary = {
        "materials_total": len(items),
        "materials_changed": len(changes),
        "changes_by_field": {field: sum(field in change["fields"] for change in changes) for field in FIELDS},
        "inventory_value_conserved": conserved,
        "inventory_rows_without_value": missing_values,
        "inventory_value_before": format(value_before.quantize(_CENTS), "f"),
        "inventory_value_after": format(value_after.quantize(_CENTS), "f"),
    }
    export = {
        "snapshot_id": str(snapshot_id),
        "dataset_id": str(dataset_id),
        "created_by_user_id": str(identity.user_id),
        "applied_proposal_ids": applied_ids,
        "summary": summary,
        "changes": changes,
    }
    content = json.dumps(export, ensure_ascii=False, sort_keys=True).encode()
    stored = store.put_if_absent(f"exports/{snapshot_id}/{EXPORT_FILE}", content)
    snapshot = QualitySnapshot(
        id=snapshot_id,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        created_by_user_id=identity.user_id,
        applied_proposal_ids=applied_ids,
        summary=summary,
        export_key=stored.key,
        content_sha256=hashlib.sha256(content).hexdigest(),
    )
    db.add(snapshot)
    db.flush()
    if items:
        db.execute(insert(QualitySnapshotItem), [{"snapshot_id": snapshot_id, **item} for item in items])
    db.add(
        AuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_user_id=identity.user_id,
            actor_type="USER",
            roles_snapshot=list(identity.roles),
            effective_role=role,
            action="QUALITY_SNAPSHOT_CREATED",
            entity_type="quality_snapshot",
            entity_id=str(snapshot_id),
            before_json=None,
            after_json={"dataset_id": str(dataset_id), "applied_proposals": len(applied_ids), **summary},
            reason="Snapshot posterior das propostas aplicadas",
            request_id=request_id,
        )
    )
    db.flush()
    db.refresh(snapshot)
    result = to_contract(snapshot)
    db.add(
        OperationRequest(
            user_id=identity.user_id,
            operation=OPERATION,
            idempotency_key=str(idempotency_key),
            payload_hash=payload_hash,
            status="COMPLETED",
            resource_id=str(snapshot_id),
            response={"status_code": 201, "body": result.model_dump(mode="json")},
        )
    )
    db.commit()
    return result


def latest_snapshot(db, tenant_id, dataset_id) -> QualitySnapshot | None:
    return db.scalar(
        select(QualitySnapshot)
        .where(QualitySnapshot.tenant_id == tenant_id, QualitySnapshot.dataset_id == dataset_id)
        .order_by(QualitySnapshot.created_at.desc(), QualitySnapshot.id.desc())
        .limit(1)
    )


def to_contract(snapshot: QualitySnapshot) -> QualitySnapshotOut:
    summary = snapshot.summary or {}
    return QualitySnapshotOut(
        id=snapshot.id,
        dataset_id=snapshot.dataset_id,
        created_at=snapshot.created_at,
        applied_proposals=len(snapshot.applied_proposal_ids or []),
        materials_changed=summary.get("materials_changed", 0),
        inventory_value_conserved=bool(summary.get("inventory_value_conserved")),
        export_key=snapshot.export_key,
    )
