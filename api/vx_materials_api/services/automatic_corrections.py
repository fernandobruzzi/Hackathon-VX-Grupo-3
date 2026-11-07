"""Aplicação no contexto da API: transação por proposta, ator SYSTEM e índice recuperável."""

import os
import uuid
from collections import Counter
from copy import deepcopy

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.automatic_corrections import ALLOWED_MATERIAL_FIELDS, POLICY_VERSION
from domain.contracts import MaterialRecord
from pipelines.automatic_corrections import assess_record, current_rules
from repositories.automatic_index import refresh_automatic_materials
from vx_materials_api import settings
from vx_materials_api.db.models import (
    AuditLog,
    AutomaticCorrectionResult,
    AutomaticCorrectionRun,
    BatchJob,
    InventoryConsolidation,
    LotReview,
    MaterialInventorySnapshot,
    MaterialMaster,
    SanitizationProposal,
    UserSso,
)
from vx_materials_api.errors import ApiError
from vx_materials_api.schemas.proposals import ProposalDecision, proposal_hash
from vx_materials_api.security.automatic_actor import AutomaticActor
from vx_materials_api.security.local_session import CENTERS
from vx_materials_api.security.rbac import has_permission, require_permission
from vx_materials_api.services.approval_service import (
    _check_review_bindings,
    _decide_current,
    consolidated_inventory,
    inventory_rows,
    load_members,
    material_state,
    merchandise_group,
    proposal_state,
)


def capture_context(identity) -> dict:
    mode = settings.automatic_correction_mode()
    if mode == "OFF" or not (has_permission(identity, "batch:run") and has_permission(identity, "merge:decide")):
        return {}
    return {"mode": mode, "policy_version": POLICY_VERSION, "center_codes": sorted(identity.center_codes)}


def _lock(db, tenant_id):
    # A mesma ordem de travas usada pelas decisões humanas e pela abertura de lotes.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant,0))"), {"tenant": str(tenant_id)})


def _actor(job, execution=None):
    codes = set(job.automatic_corrections.get("center_codes", []))
    configured = os.environ.get("AUTHORIZED_CENTER_CODES")
    current = (
        set(part.strip() for part in configured.split(",") if part.strip())
        if configured
        else (set(CENTERS) if settings.app_env() == "local" else set())
    )
    return AutomaticActor(job.tenant_id, frozenset(codes & current), execution or {})


def _eligible_job(db, job, run):
    if (
        job.status != "SUCCEEDED"
        or job.job_type != "SANITIZE"
        or run.policy_version != POLICY_VERSION
        or job.automatic_corrections.get("policy_version") != POLICY_VERSION
    ):
        raise ApiError(422, "AUTOMATION_JOB_NOT_ELIGIBLE", "O job não autoriza esta política automática.")
    owner = db.scalar(select(UserSso).where(UserSso.id == job.requested_by_user_id).with_for_update())
    if (
        owner is None
        or owner.tenant_id != job.tenant_id
        or owner.disabled_at is not None
        or "ROLE_GOVERNANCA_PDM" not in owner.roles_snapshot
    ):
        raise ApiError(403, "AUTOMATION_SCOPE_REVOKED", "A autorização do job não está vigente.")


def _record(material) -> MaterialRecord:
    return MaterialRecord(
        material.material_code,
        material.status,
        material.original_description_long or material.original_description_short or "",
        short_description=material.original_description_short or "",
        group=merchandise_group(material) or "",
        manufacturer=material.manufacturer or "",
        reference=material.manufacturer_reference or "",
        unit=material.unit or "",
        ncm=material.ncm or "",
        version=material.version,
        database_id=str(material.id),
    )


def _material_columns(material) -> dict:
    return {column.name: deepcopy(getattr(material, column.name)) for column in MaterialMaster.__table__.columns}


def _inventory_columns(db, tenant_id, material_id, related=()):
    snapshots = list(
        db.scalars(
            select(MaterialInventorySnapshot)
            .where(
                MaterialInventorySnapshot.tenant_id == tenant_id,
                or_(
                    MaterialInventorySnapshot.material_id == material_id,
                    MaterialInventorySnapshot.id.in_([snapshot.id for snapshot in related]),
                ),
            )
            .order_by(MaterialInventorySnapshot.id)
        )
    )
    ids = [row.id for row in snapshots]
    links = list(
        db.scalars(
            select(InventoryConsolidation)
            .where(InventoryConsolidation.tenant_id == tenant_id, InventoryConsolidation.source_snapshot_id.in_(ids))
            .order_by(InventoryConsolidation.source_snapshot_id)
        )
    )
    return [
        [{column.name: deepcopy(getattr(row, column.name)) for column in type(row).__table__.columns} for row in group]
        for group in (snapshots, links)
    ]


def _lot_claimed(db, tenant_id, proposal_id):
    return any(
        str(proposal_id) in review.proposal_versions
        for review in db.scalars(
            select(LotReview).where(LotReview.tenant_id == tenant_id, LotReview.status.in_(["OPEN", "RETURNED"]))
        )
    )


def _new_result(run, proposal_id):
    return AutomaticCorrectionResult(
        id=uuid.uuid5(run.id, str(proposal_id)),
        tenant_id=run.tenant_id,
        run_id=run.id,
        proposal_id=proposal_id,
        status="REVIEW",
        reasons=[],
        evidence={},
        attempts=1,
        index_status="NOT_REQUIRED",
        eligible=False,
    )


def _stale(db, run, result, proposal, before, reasons):
    result.status, result.reasons = "STALE", reasons
    if run.mode == "APPLY":
        proposal.status = "STALE"
        proposal.version += 1
        db.add(
            AuditLog(
                id=uuid.uuid4(),
                tenant_id=run.tenant_id,
                actor_type="SYSTEM",
                roles_snapshot=[],
                actor_user_id=None,
                effective_role=None,
                action="PROPOSAL_AUTO_STALE",
                entity_type="sanitization_proposal",
                entity_id=str(proposal.id),
                before_json=before,
                after_json={
                    **proposal_state(proposal),
                    "automatic_correction": {
                        "execution_id": str(run.id),
                        "policy_version": run.policy_version,
                        "reasons": reasons,
                    },
                },
                reason="A proposta exige nova análise.",
                request_id=str(run.id),
                job_id=run.job_id,
            )
        )


def process_proposal(factory, run_id, proposal_id, catalog, *, retry_errors=False):
    """Uma transação por item: qualquer efeito indevido desfaz material, decisão e auditoria."""
    try:
        with factory() as db, db.begin():
            run = db.get(AutomaticCorrectionRun, run_id)
            if run is None:
                return
            _lock(db, run.tenant_id)
            job = db.get(BatchJob, run.job_id)
            if settings.automatic_correction_mode() == "OFF" or (
                run.mode == "APPLY" and settings.automatic_correction_mode() != "APPLY"
            ):
                return
            previous = db.scalar(
                select(AutomaticCorrectionResult)
                .where(AutomaticCorrectionResult.run_id == run.id, AutomaticCorrectionResult.proposal_id == proposal_id)
                .with_for_update()
            )
            if previous and (previous.status != "ERROR" or not retry_errors):
                return
            result = previous or _new_result(run, proposal_id)
            if previous:
                result.attempts += 1
            else:
                db.add(result)
            result.eligible, result.index_error = False, None
            proposal = db.scalar(
                select(SanitizationProposal)
                .where(SanitizationProposal.id == proposal_id, SanitizationProposal.tenant_id == run.tenant_id)
                .with_for_update()
            )
            if proposal is None or proposal.job_id != job.id or proposal.created_at < job.created_at:
                result.reasons, result.status = ["NOT_A_NEW_JOB_PROPOSAL"], "REVIEW"
                return
            if proposal.status != "PENDING" or proposal.technical_review_status != "PENDING":
                result.status, result.reasons = "SKIPPED", ["PROPOSAL_ALREADY_DECIDED"]
                return
            if _lot_claimed(db, run.tenant_id, proposal.id):
                result.status, result.reasons = "REVIEW", ["HUMAN_LOT_REVIEW"]
                return
            try:
                _eligible_job(db, job, run)
                actor = _actor(job)
                interpretations, changes, materials, snapshots = load_members(db, proposal, actor, lock=True)
            except ApiError as error:
                result.status, result.reasons = "REVIEW", [error.code]
                return
            before = {
                **proposal_state(proposal),
                "members": proposal.members,
                "changeset": proposal.changeset,
                "materials": [material_state(material) for material in materials],
                "snapshot_ids": [str(row.id) for row in snapshots],
                "inventory": consolidated_inventory(inventory_rows(db, snapshots, None, changes), financial=True),
            }
            result.evidence = {
                "proposal_version": proposal.version,
                "changeset_hash": proposal.changeset_hash,
                "policy_version": run.policy_version,
                "rules_signature": run.rules_signature,
            }
            if (
                proposal_hash(proposal.members, proposal.changeset, proposal.evidence_ids) != proposal.changeset_hash
                or any(
                    material.version
                    != next(item.expected_version for item in interpretations if item.material_id == material.id)
                    for material in materials
                )
                or not _check_review_bindings(db, proposal)
                or current_rules(catalog) != run.rules_signature
                or changes.pdm_version != catalog.version
                or changes.pdm_source_sha256 != catalog.source_sha256
            ):
                _stale(db, run, result, proposal, before, ["PROPOSAL_OR_RULES_CHANGED"])
                return
            if (
                len(materials) != 1
                or proposal.proposal_type not in ALLOWED_MATERIAL_FIELDS
                or proposal.fiscal_review_status != "NOT_REQUIRED"
                or proposal.evidence_ids
            ):
                result.status, result.reasons = "REVIEW", ["UNSUPPORTED_OR_FISCAL_PROPOSAL"]
                return
            material = materials[0]
            result.material_id = material.id
            verdict = assess_record(
                catalog,
                _record(material),
                proposal.proposal_type,
                proposal.changeset,
                material_state(material),
                str(changes.dataset_id),
            )
            result.evidence = {**result.evidence, **verdict.evidence}
            result.reasons = list(verdict.reasons)
            if not verdict.eligible:
                result.status = "REVIEW"
                return
            # O mesmo caminho valida simulação e aplicação. Somente a aplicação confirma o savepoint.
            original_material = _material_columns(material)
            original_inventory = _inventory_columns(db, run.tenant_id, material.id, snapshots)
            savepoint = db.begin_nested()
            try:
                context = {
                    "execution_id": str(run.id),
                    "job_id": str(job.id),
                    "policy_version": run.policy_version,
                    "rules_signature": run.rules_signature,
                    "reasons": list(verdict.reasons),
                    "evidence": verdict.evidence,
                }
                actor = _actor(job, context)
                if any(snapshot.center_code not in actor.center_codes for snapshot in snapshots):
                    raise ApiError(404, "AUTOMATION_SCOPE_CHANGED", "O escopo autorizado mudou.")
                if settings.automatic_correction_mode() == "OFF" or (
                    run.mode == "APPLY" and settings.automatic_correction_mode() != "APPLY"
                ):
                    raise ApiError(409, "AUTOMATION_DISABLED", "A aplicação automática foi desabilitada.")
                proposal.application_mode = "AUTOMATIC"
                decision = ProposalDecision(
                    expected_version=proposal.version,
                    review_area="TECHNICAL",
                    decision="APPROVE",
                    reason=f"Aplicação automática pela política {run.policy_version}.",
                )
                code, body = _decide_current(
                    db,
                    actor,
                    proposal,
                    decision,
                    catalog,
                    interpretations,
                    changes,
                    materials,
                    snapshots,
                    str(run.id),
                    before,
                    None,
                )
                db.flush()
                changed = {key for key, value in _material_columns(material).items() if value != original_material[key]}
                if (
                    code != 200
                    or body["status"] != "APPLIED"
                    or material.version != original_material["version"] + 1
                    or changed - ALLOWED_MATERIAL_FIELDS[proposal.proposal_type]
                    or _inventory_columns(db, run.tenant_id, material.id, snapshots) != original_inventory
                ):
                    raise ApiError(422, "OUT_OF_SCOPE_EFFECT", "A aplicação altera dados fora da política automática.")
                result.eligible = True
                result.evidence = {
                    **result.evidence,
                    "changed_fields": sorted(changed),
                    "material_version_after": material.version,
                }
                if run.mode == "SIMULATE":
                    evidence = deepcopy(result.evidence)
                    savepoint.rollback()
                    result.eligible, result.status, result.evidence = True, "ELIGIBLE", evidence
                else:
                    if settings.automatic_correction_mode() != "APPLY":
                        raise ApiError(409, "AUTOMATION_DISABLED", "A aplicação automática foi desabilitada.")
                    savepoint.commit()
                    result.status, result.index_status = "APPLIED", "PENDING"
            except (ApiError, IntegrityError) as error:
                savepoint.rollback()
                result.eligible, result.status = False, "REVIEW"
                result.reasons = [error.code if isinstance(error, ApiError) else "IDENTITY_OR_INTEGRITY_CONFLICT"]
    except Exception as error:
        # O rollback acima já desfez todos os efeitos. Registra o erro separadamente, sem dados de conexão.
        with factory() as db, db.begin():
            run = db.get(AutomaticCorrectionRun, run_id)
            if run is None:
                raise
            _lock(db, run.tenant_id)
            result = db.scalar(
                select(AutomaticCorrectionResult).where(
                    AutomaticCorrectionResult.run_id == run.id, AutomaticCorrectionResult.proposal_id == proposal_id
                )
            )
            if result is not None and result.status not in {"ERROR"}:
                return
            if result is None:
                result = _new_result(run, proposal_id)
                db.add(result)
            else:
                result.attempts += 1
            result.status, result.reasons, result.eligible = (
                "ERROR",
                [f"APPLICATION_ERROR:{type(error).__name__}"],
                False,
            )
            proposal = db.get(SanitizationProposal, proposal_id)
            result.evidence = {
                "policy_version": run.policy_version,
                "rules_signature": run.rules_signature,
                "proposal_version": proposal.version if proposal else None,
                "changeset_hash": proposal.changeset_hash if proposal else None,
            }
            if proposal and proposal.tenant_id == run.tenant_id:
                result.material_id = proposal.primary_material_id


def initialize_run(factory, job_id, catalog):
    with factory() as db, db.begin():
        job = db.get(BatchJob, job_id)
        if job is None:
            return None
        _lock(db, job.tenant_id)
        existing = db.scalar(select(AutomaticCorrectionRun).where(AutomaticCorrectionRun.job_id == job.id))
        if existing:
            return existing.id
        context = job.automatic_corrections or {}
        if (
            job.status != "SUCCEEDED"
            or context.get("mode") not in {"SIMULATE", "APPLY"}
            or context.get("policy_version") != POLICY_VERSION
            or settings.automatic_correction_mode() == "OFF"
        ):
            return None
        ids = list(
            db.scalars(
                select(SanitizationProposal.id)
                .where(
                    SanitizationProposal.job_id == job.id,
                    SanitizationProposal.tenant_id == job.tenant_id,
                    SanitizationProposal.created_at >= job.created_at,
                    SanitizationProposal.status == "PENDING",
                    SanitizationProposal.technical_review_status == "PENDING",
                )
                .order_by(SanitizationProposal.id)
            )
        )
        run = AutomaticCorrectionRun(
            id=uuid.uuid4(),
            tenant_id=job.tenant_id,
            job_id=job.id,
            mode=context["mode"],
            policy_version=POLICY_VERSION,
            rules_signature=job.checkpoint.get("analysis_signature", ""),
            target_ids=[str(value) for value in ids],
            status="RUNNING",
        )
        db.add(run)
        return run.id


def refresh_index(factory, run_id, catalog, *, indexer=None):
    with factory() as db, db.begin():
        run = db.get(AutomaticCorrectionRun, run_id)
        if run is None:
            return
        _lock(db, run.tenant_id)
        pending = list(
            db.scalars(
                select(AutomaticCorrectionResult)
                .where(
                    AutomaticCorrectionResult.run_id == run.id,
                    AutomaticCorrectionResult.status == "APPLIED",
                    AutomaticCorrectionResult.index_status != "CURRENT",
                )
                .with_for_update()
            )
        )
        if not pending:
            return
        try:
            if indexer is None:

                def indexer(tenant, ids):
                    return refresh_automatic_materials(settings.batch_database_url(), tenant, ids, catalog)

            response = indexer(str(run.tenant_id), [str(result.material_id) for result in pending])
            for result in pending:
                result.index_status, result.index_error = "CURRENT", None
                result.evidence = {**result.evidence, "index": response}
        except Exception as error:
            for result in pending:
                result.index_status, result.index_error = "FAILED", f"INDEX_ERROR:{type(error).__name__}"


def process_job(factory, job_id, catalog, *, retry_errors=False, indexer=None):
    run_id = initialize_run(factory, job_id, catalog)
    if run_id is None:
        return
    with factory() as db:
        run = db.get(AutomaticCorrectionRun, run_id)
        ids = [uuid.UUID(value) for value in run.target_ids]
        completed = run.status == "COMPLETED"
    if not completed or retry_errors:
        for proposal_id in ids:
            process_proposal(factory, run_id, proposal_id, catalog, retry_errors=retry_errors)
    refresh_index(factory, run_id, catalog, indexer=indexer)
    with factory() as db, db.begin():
        run = db.get(AutomaticCorrectionRun, run_id)
        _lock(db, run.tenant_id)
        count = db.scalar(
            select(func.count())
            .select_from(AutomaticCorrectionResult)
            .where(AutomaticCorrectionResult.run_id == run_id)
        )
        if count == len(run.target_ids):
            run.status = "COMPLETED"


def process_ready_jobs(factory, catalog, *, indexer=None):
    with factory() as db:
        pending_index = select(AutomaticCorrectionResult.run_id).where(
            AutomaticCorrectionResult.status == "APPLIED", AutomaticCorrectionResult.index_status != "CURRENT"
        )
        statement = (
            select(BatchJob.id)
            .outerjoin(AutomaticCorrectionRun, AutomaticCorrectionRun.job_id == BatchJob.id)
            .where(
                BatchJob.status == "SUCCEEDED", BatchJob.automatic_corrections["mode"].astext.in_(["SIMULATE", "APPLY"])
            )
        )
        if settings.automatic_correction_mode() == "OFF":
            statement = statement.where(AutomaticCorrectionRun.id.in_(pending_index))
        else:
            statement = statement.where(
                or_(
                    AutomaticCorrectionRun.id.is_(None),
                    AutomaticCorrectionRun.status != "COMPLETED",
                    AutomaticCorrectionRun.id.in_(pending_index),
                )
            )
        ids = list(db.scalars(statement))
    for job_id in ids:
        process_job(factory, job_id, catalog, indexer=indexer)


def summary(db, job, run):
    context = job.automatic_corrections or {}
    data = {
        "mode": context.get("mode", "OFF"),
        "configured_mode": settings.automatic_correction_mode(),
        "policy_version": context.get("policy_version", POLICY_VERSION),
        "execution_id": str(run.id) if run else None,
        "status": run.status if run else "WAITING" if context else "DISABLED",
        "counts": {},
        "reasons": {},
    }
    if context and context.get("policy_version") != POLICY_VERSION:
        data.update(status="POLICY_CHANGED", reasons={"POLICY_CHANGED": 1})
    if context and (
        settings.automatic_correction_mode() == "OFF"
        or (context.get("mode") == "APPLY" and settings.automatic_correction_mode() != "APPLY")
    ):
        data["status"] = "PAUSED" if run is None or run.status != "COMPLETED" else run.status
    if run is None:
        return data
    rows = db.execute(
        select(
            AutomaticCorrectionResult.status,
            AutomaticCorrectionResult.eligible,
            AutomaticCorrectionResult.index_status,
            AutomaticCorrectionResult.reasons,
            func.count(),
        )
        .where(AutomaticCorrectionResult.run_id == run.id)
        .group_by(
            AutomaticCorrectionResult.status,
            AutomaticCorrectionResult.eligible,
            AutomaticCorrectionResult.index_status,
            AutomaticCorrectionResult.reasons,
        )
    )
    counts = Counter(
        dict.fromkeys(["evaluated", "eligible", "applied", "review", "stale", "errors", "index_pending"], 0)
    )
    reasons = Counter()
    for status, eligible, index_status, codes, count in rows:
        counts["evaluated"] += count
        counts["eligible"] += count if eligible else 0
        counts["applied"] += count if status == "APPLIED" else 0
        counts["review"] += count if status in {"REVIEW", "SKIPPED"} else 0
        counts["stale"] += count if status == "STALE" else 0
        counts["errors"] += count if status == "ERROR" else 0
        counts["index_pending"] += count if status == "APPLIED" and index_status != "CURRENT" else 0
        if not eligible:
            for code in codes:
                reasons[code] += count
    return {
        **data,
        "mode": run.mode,
        "policy_version": run.policy_version,
        "counts": dict(counts),
        "reasons": dict(reasons),
    }


def report(db: Session, identity, job_id, *, limit=20, cursor=None):
    require_permission(identity, "batch:run")
    job = db.scalar(select(BatchJob).where(BatchJob.id == job_id, BatchJob.tenant_id == identity.tenant_id))
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Job não encontrado.")
    run = db.scalar(select(AutomaticCorrectionRun).where(AutomaticCorrectionRun.job_id == job.id))
    data = summary(db, job, run)
    if run is None:
        return {**data, "items": [], "next_cursor": None}
    statement = select(AutomaticCorrectionResult).where(AutomaticCorrectionResult.run_id == run.id)
    if cursor is not None:
        statement = statement.where(AutomaticCorrectionResult.id > cursor)
    visible = []
    more = False
    for result in db.scalars(statement.order_by(AutomaticCorrectionResult.id)):
        proposal = db.get(SanitizationProposal, result.proposal_id)
        if proposal is None:
            continue
        try:
            load_members(db, proposal, identity)
        except ApiError:
            continue
        if len(visible) == limit:
            more = True
            break
        visible.append(result)
    # Busca um registro a mais após o guard de recurso para decidir o cursor.
    items = [
        {
            "proposal_id": str(row.proposal_id),
            "id": str(row.id),
            "material_id": str(row.material_id) if row.material_id else None,
            "status": row.status,
            "eligible": row.eligible,
            "reasons": row.reasons,
            "attempts": row.attempts,
            "index_status": row.index_status,
            "index_error": row.index_error,
        }
        for row in visible
    ]
    return {**data, "items": items, "next_cursor": str(visible[-1].id) if more else None}
