"""Fila manual isolada; o encaminhamento só grava uma proposta versionada e sua auditoria."""

import json
from collections import Counter
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import or_, select, text, tuple_, union

from domain.pdm_validator import validate_pdm
from domain.proposal_validation import is_approvable
from domain.proposals import canonical_hash, proposal_hash
from repositories.normalization import get_normalization_repository
from vx_materials_api.db.models import (
    AuditLog,
    BatchJob,
    Dataset,
    InventoryConsolidation,
    ManualReview,
    MaterialInventorySnapshot,
    MaterialMaster,
    OperationRequest,
    SanitizationProposal,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.proposals import ProposalChangeset
from vx_materials_api.security.rbac import require_permission
from vx_materials_api.services.approval_service import inventory_rows
from vx_materials_api.services.ncm_validation import evaluate_proposed_ncm


def scoped_query(principal):
    require_permission(principal, "merge:decide")
    stock = MaterialInventorySnapshot
    # Calcula o conjunto de centros vedados uma vez, inclusive estoques herdados por consolidação.
    # Evita varrer todos os snapshots para cada uma das milhares de pendências.
    forbidden = union(
        select(stock.dataset_id, stock.material_id).where(
            stock.tenant_id == principal.tenant_id, stock.center_code.not_in(principal.center_codes)
        ),
        select(stock.dataset_id, InventoryConsolidation.primary_material_id)
        .join(InventoryConsolidation, InventoryConsolidation.source_snapshot_id == stock.id)
        .where(
            stock.tenant_id == principal.tenant_id,
            InventoryConsolidation.tenant_id == principal.tenant_id,
            stock.center_code.not_in(principal.center_codes),
        ),
    )
    return (
        select(ManualReview)
        .join(Dataset, Dataset.id == ManualReview.dataset_id)
        .join(MaterialMaster, MaterialMaster.id == ManualReview.material_id)
        .where(
            ManualReview.tenant_id == principal.tenant_id,
            Dataset.tenant_id == principal.tenant_id,
            MaterialMaster.tenant_id == principal.tenant_id,
            tuple_(ManualReview.dataset_id, ManualReview.material_id).not_in(forbidden),
        )
    )


def serialize(row, proposal=None):
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "job_id": str(row.job_id) if row.job_id else None,
        "material_id": str(row.material_id),
        "expected_material_version": row.expected_material_version,
        "reasons": row.reasons,
        "observation": row.observation,
        "rules_signature": row.rules_signature,
        "pdm_version": row.pdm_version,
        "pdm_source_sha256": row.pdm_source_sha256,
        "proposal_id": str(row.proposal_id) if row.proposal_id else None,
        "proposal_status": proposal.status if proposal else None,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


def list_reviews(db, principal, *, run_id=None, reason=None, material_code=None, cursor=None, limit=20):
    query = scoped_query(principal).where(
        or_(
            ManualReview.job_id.is_(None),
            ManualReview.job_id.in_(
                select(BatchJob.id).where(BatchJob.tenant_id == principal.tenant_id, BatchJob.status == "SUCCEEDED")
            ),
        )
    )
    if run_id:
        query = query.where(ManualReview.run_id == run_id)
    latest = db.scalar(query.order_by(ManualReview.created_at.desc(), ManualReview.run_id.desc()).limit(1))
    if latest is None:
        return {
            "run_id": None,
            "job_id": None,
            "items": [],
            "counts_by_reason": {},
            "materials_total": 0,
            "next_cursor": None,
        }
    query = query.where(ManualReview.run_id == latest.run_id)
    reasons = list(db.scalars(query.with_only_columns(ManualReview.reasons)))
    counts = Counter(reason for row in reasons for reason in row)
    if reason:
        query = query.where(ManualReview.reasons.contains([reason]))
    if material_code:
        query = query.where(ManualReview.observation["material_code"].astext == material_code)
    if cursor:
        query = query.where(ManualReview.id > cursor)
    rows = list(db.scalars(query.order_by(ManualReview.id).limit(limit + 1)))
    proposals = {
        p.id: p
        for p in db.scalars(
            select(SanitizationProposal).where(
                SanitizationProposal.tenant_id == principal.tenant_id,
                SanitizationProposal.id.in_([row.proposal_id for row in rows if row.proposal_id]),
            )
        )
    }
    return {
        "run_id": str(latest.run_id),
        "job_id": str(latest.job_id) if latest.job_id else None,
        "items": [serialize(row, proposals.get(row.proposal_id)) for row in rows[:limit]],
        "counts_by_reason": dict(sorted(counts.items())),
        "materials_total": len(reasons),
        "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
    }


def propose_resolution(db, principal, review_id, payload, key, request_id, catalog):
    require_permission(principal, "merge:decide")
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 0))"), {"tenant": str(principal.tenant_id)})
    row = db.scalar(scoped_query(principal).where(ManualReview.id == review_id).with_for_update(of=ManualReview))
    if row is None:
        raise ApiProblem(404, "NOT_FOUND", "Pendência não encontrada no seu escopo.")
    if row.job_id:
        job = db.get(BatchJob, row.job_id)
        if job is None or job.status != "SUCCEEDED":
            raise ApiProblem(409, "RUN_NOT_FINISHED", "Aguarde a conclusão do batch antes de encaminhar a pendência.")
    digest = canonical_hash({"review_id": str(review_id), **payload.model_dump(mode="json")})
    previous = db.scalar(
        select(OperationRequest).where(
            OperationRequest.user_id == principal.user_id,
            OperationRequest.operation == "manual-review.propose",
            OperationRequest.idempotency_key == str(key),
        )
    )
    if previous:
        if previous.payload_hash != digest:
            raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "A chave já foi usada com outro conteúdo.")
        return previous.response
    if row.proposal_id:
        previous_proposal = db.get(SanitizationProposal, row.proposal_id)
        if previous_proposal.status in {"PENDING", "APPLIED"}:
            raise ApiProblem(409, "ALREADY_PROPOSED", "Esta pendência já foi encaminhada à aprovação.")
    material = db.scalar(select(MaterialMaster).where(MaterialMaster.id == row.material_id).with_for_update())
    if material.version != row.expected_material_version or material.version != payload.expected_material_version:
        raise ApiProblem(409, "STALE_MATERIAL", "O material mudou. Execute um novo batch antes de propor.")
    if material.status != "ATIVO":
        raise ApiProblem(422, "INACTIVE_MATERIAL", "Material bloqueado ou obsoleto não pode ser corrigido.")
    if row.pdm_version != catalog.version or row.pdm_source_sha256 != catalog.source_sha256:
        raise ApiProblem(409, "REFERENCE_CHANGED", "O PDM mudou. Execute um novo batch.")
    validation = validate_pdm(
        catalog, payload.pdm_class_id, payload.attributes, item_name=payload.item_name, unit=payload.unit
    )
    if not is_approvable(validation):
        raise ApiProblem(
            422,
            "PDM_INVALID",
            "Complete os atributos conforme o PDM antes de encaminhar.",
            missing=[a.name for a in validation.missing_attributes],
            invalid=[a.name for a in validation.invalid_attributes],
        )
    pdm_class = catalog.classes[payload.pdm_class_id]
    after = {
        "pdm_class_id": payload.pdm_class_id,
        "item_name": payload.item_name,
        "attributes": payload.attributes,
        "unit": payload.unit,
        "ncm": payload.ncm,
        "merchandise_group": pdm_class.group,
    }
    sources = {field: payload.source for field in ("pdm_class_id", "attributes", "unit", "ncm", "merchandise_group")}
    changes = [
        {"field": field, "before": before, "after": value, "source": payload.source}
        for field, before, value in (
            (
                "description",
                material.pdm_description or material.original_description_long,
                validation.formatted_description,
            ),
            ("merchandise_group", material.merchandise_group or material.original_merchandise_group, pdm_class.group),
            ("unit", material.unit, payload.unit),
        )
        if before != value
    ]
    changeset = {
        "schema_version": "proposal-v1",
        "dataset_id": str(row.dataset_id),
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "after": after,
        "conversions": [c.model_dump() for c in payload.conversions],
        "conflicts": [],
        "sources": sources,
        "changes": changes,
        "review_lane": {
            "tier": 3,
            "lot_key": f"PDM_CORRECTION|manual_review|{pdm_class.id}",
            "reasons": ["MANUAL_REVIEW"],
        },
    }
    parsed_changes = ProposalChangeset.model_validate_json(json.dumps(changeset))
    changeset["ncm_assessment"] = evaluate_proposed_ncm(catalog, parsed_changes)
    snapshots = list(
        db.scalars(
            select(MaterialInventorySnapshot).where(
                MaterialInventorySnapshot.tenant_id == principal.tenant_id,
                MaterialInventorySnapshot.dataset_id == row.dataset_id,
                or_(
                    MaterialInventorySnapshot.material_id == material.id,
                    MaterialInventorySnapshot.id.in_(
                        select(InventoryConsolidation.source_snapshot_id).where(
                            InventoryConsolidation.tenant_id == principal.tenant_id,
                            InventoryConsolidation.primary_material_id == material.id,
                        )
                    ),
                ),
            )
        )
    )
    # Aliases conhecidos preservam fator 1 mesmo após uma correção de grafia do mestre:
    # o snapshot original pode continuar em UN quando o cadastro já está em PC.
    normalizer = get_normalization_repository()
    conversions = changeset["conversions"]
    for conversion in conversions:
        normalized = normalizer.normalize_unit(conversion["from_unit"])
        if normalized.value == conversion["to_unit"] and Decimal(conversion["factor"]) != 1:
            raise ApiProblem(422, "UNIT_ALIAS_FACTOR", "Grafias da mesma unidade usam fator 1.")
    known = {(c["from_unit"], c["to_unit"]) for c in conversions}
    for raw_unit in sorted({s.unit for s in snapshots if s.unit} | {material.unit or ""}):
        normalized = normalizer.normalize_unit(raw_unit)
        pair = (raw_unit, payload.unit)
        if raw_unit != payload.unit and normalized.value == payload.unit and pair not in known:
            conversions.append(
                {"from_unit": raw_unit, "to_unit": payload.unit, "factor": "1", "source": normalized.rule}
            )
            known.add(pair)
    # Usa a mesma conferência de fatores e fontes da aprovação; nada é consolidado aqui.
    inventory_rows(db, snapshots, payload.unit, ProposalChangeset.model_validate_json(json.dumps(changeset)))
    members = [
        {
            "material_id": str(material.id),
            "expected_version": material.version,
            "pdm_class_id": payload.pdm_class_id,
            "item_name": payload.item_name,
            "attributes": payload.attributes,
        }
    ]
    fiscal = (
        normalizer.normalize_ncm(material.ncm).value != normalizer.normalize_ncm(payload.ncm).value
        or (material.pdm_class_id is not None and material.pdm_class_id != payload.pdm_class_id)
        or (bool(material.attributes) and material.attributes != payload.attributes)
    )
    proposal = SanitizationProposal(
        id=uuid4(),
        tenant_id=principal.tenant_id,
        job_id=row.job_id,
        proposal_type="PDM_CORRECTION",
        members=members,
        primary_material_id=material.id,
        changeset=changeset,
        changeset_hash=proposal_hash(members, changeset),
        technical_review_status="PENDING",
        fiscal_review_status="PENDING" if fiscal else "NOT_REQUIRED",
    )
    db.add(proposal)
    db.flush()
    row.proposal_id = proposal.id
    role = require_permission(principal, "merge:decide")
    db.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            actor_type="USER",
            roles_snapshot=list(principal.roles),
            effective_role=role,
            action="MANUAL_REVIEW_PROPOSE",
            entity_type="sanitization_proposal",
            entity_id=str(proposal.id),
            before_json={"manual_review_id": str(row.id), "reasons": row.reasons, "observation": row.observation},
            after_json={
                "proposal_id": str(proposal.id),
                "changeset_hash": proposal.changeset_hash,
                "source": payload.source,
            },
            reason=payload.reason,
            request_id=request_id,
            job_id=row.job_id,
        )
    )
    response = {"review_id": str(row.id), "proposal_id": str(proposal.id), "status": "PENDING"}
    db.add(
        OperationRequest(
            user_id=principal.user_id,
            operation="manual-review.propose",
            idempotency_key=str(key),
            payload_hash=digest,
            status="COMPLETED",
            resource_id=str(proposal.id),
            response=response,
        )
    )
    db.flush()
    return response
