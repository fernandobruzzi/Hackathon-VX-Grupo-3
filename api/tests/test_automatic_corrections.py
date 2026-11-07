"""Automação sobre registros reais, com rollback e recuperação PostgreSQL."""

import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.automatic_corrections import POLICY_VERSION
from pipelines.automatic_corrections import current_rules
from pipelines.measure_automatic_corrections import candidates
from pipelines.sanitize import read_csv_records
from repositories.proposal_payload import approval_payload
from vx_materials_api.db.models import AuditLog, AutomaticCorrectionResult, BatchJob
from vx_materials_api.services import automatic_corrections as automatic


@pytest.fixture(scope="module")
def records():
    return {r.code: r for r in read_csv_records(Path(__file__).parents[2] / "data/desafio01/01_base_materiais.csv")}


@pytest.fixture
def auto_case(approval_case, records, connection, monkeypatch):
    case = approval_case
    monkeypatch.setenv("AUTOMATIC_CORRECTION_MODE", "APPLY")
    monkeypatch.setenv("APP_ENV", "local")

    def prepare(code="24794045", kind="UNIT_CORRECTION"):
        return prepare_case(case, records, connection, code, kind)

    return prepare


def execute(case, **kwargs):
    automatic.process_job(case["factory"], case["job"].id, case["catalog"], indexer=lambda *_: {"test": True}, **kwargs)
    case["session"].expire_all()
    return case["session"].scalar(select(AutomaticCorrectionResult))


@pytest.mark.parametrize(("code", "kind"), [("24794045", "UNIT_CORRECTION"), ("16454102", "PDM_CORRECTION")])
def test_real_applies_preserves_and_is_idempotent(auto_case, code, kind):
    case = auto_case(code, kind)
    old = automatic._material_columns(case["material"])
    inventory = automatic._inventory_columns(case["session"], case["material"].tenant_id, case["material"].id)
    result = execute(case)
    assert result.status == "APPLIED", (result.reasons, result.evidence)
    current = automatic._material_columns(case["material"])
    assert {k for k in old if old[k] != current[k]} <= automatic.ALLOWED_MATERIAL_FIELDS[kind]
    assert automatic._inventory_columns(case["session"], case["material"].tenant_id, case["material"].id) == inventory
    assert case["material"].version == 2
    assert case["proposal"].application_mode == "AUTOMATIC" and case["proposal"].technical_reviewer_id is None
    audit = case["session"].scalar(select(AuditLog).where(AuditLog.action == "PROPOSAL_AUTO_APPLY"))
    assert audit.actor_type == "SYSTEM" and audit.actor_user_id is None and not audit.roles_snapshot
    execute(case)
    assert case["material"].version == 2 and result.index_status == "CURRENT"


def test_simulation_rolls_back_writer(auto_case):
    case = auto_case()
    case["job"].automatic_corrections = {**case["job"].automatic_corrections, "mode": "SIMULATE"}
    case["session"].commit()
    before = automatic._material_columns(case["material"])
    result = execute(case)
    assert result.status == "ELIGIBLE", result.reasons
    assert automatic._material_columns(case["material"]) == before
    assert case["proposal"].status == "PENDING" and case["proposal"].application_mode == "HUMAN"
    assert not list(case["session"].scalars(select(AuditLog)))


@pytest.mark.parametrize("mode", ["OFF", "UNARMED"])
def test_off_and_old_job_not_captured(auto_case, monkeypatch, mode):
    case = auto_case()
    if mode == "OFF":
        monkeypatch.setenv("AUTOMATIC_CORRECTION_MODE", "OFF")
    else:
        case["job"].automatic_corrections = {}
        case["session"].commit()
    assert execute(case) is None
    assert case["material"].version == 1 and case["proposal"].status == "PENDING"


def test_changed_version_is_stale(auto_case):
    case = auto_case()
    case["material"].version = 2
    case["session"].commit()
    assert execute(case).status == "STALE"
    assert case["proposal"].status == "STALE" and case["material"].unit == "PCA"


def test_unknown_class_remains_human(auto_case):
    case = auto_case("24477027")
    assert execute(case).status == "REVIEW"
    assert case["proposal"].status == "PENDING"


def test_index_failure_recovers_without_reapplication(auto_case):
    case = auto_case()

    def fail(*_):
        raise RuntimeError("não registrar credenciais")

    automatic.process_job(case["factory"], case["job"].id, case["catalog"], indexer=fail)
    case["session"].expire_all()
    result = case["session"].scalar(select(AutomaticCorrectionResult))
    assert result.status == "APPLIED" and result.index_status == "FAILED"
    assert result.index_error == "INDEX_ERROR:RuntimeError"
    execute(case)
    assert result.index_status == "CURRENT" and case["material"].version == 2


def test_audit_failure_rolls_back_and_retry_recovers(auto_case, monkeypatch):
    case = auto_case()
    from vx_materials_api.services import approval_service

    audit = approval_service._audit

    def fail(*_, **__):
        raise RuntimeError("falha de escrita")

    monkeypatch.setattr(approval_service, "_audit", fail)
    result = execute(case)
    assert result.status == "ERROR", result.reasons
    assert case["material"].version == 1 and case["proposal"].status == "PENDING"
    assert not list(case["session"].scalars(select(AuditLog)))
    monkeypatch.setattr(approval_service, "_audit", audit)
    execute(case, retry_errors=True)
    assert result.status == "APPLIED" and case["material"].version == 2 and result.attempts == 2


def prepare_case(case, records, connection, code="24794045", kind="UNIT_CORRECTION"):
    session = case["session"]
    material, proposal = case["materials"][0], case["proposal"]
    record = replace(records[code], database_id=str(material.id), version=1)
    material.material_code = code
    material.original_description_long, material.original_description_short = (
        record.description,
        record.short_description,
    )
    material.original_merchandise_group = material.merchandise_group = record.group
    material.unit, material.ncm = record.unit, record.ncm or None
    material.manufacturer, material.manufacturer_reference = record.manufacturer or None, record.reference or None
    material.pdm_class_id = material.pdm_version = material.pdm_description = material.identity_key = None
    material.attributes, material.is_canonical = {}, False
    for row in case["snapshots"]:
        if row.material_id == material.id:
            row.unit = record.unit
    candidate = next(p for p in candidates(record, case["catalog"]) if p.proposal_type == kind)
    members, payload, digest = approval_payload(candidate, {code: str(material.id)}, str(case["dataset"].id))
    job = BatchJob(
        id=uuid.uuid4(),
        tenant_id=material.tenant_id,
        requested_by_user_id=case["principals"][0].user_id,
        dataset_id=case["dataset"].id,
        job_type="SANITIZE",
        pdm_version=case["catalog"].version,
        status="SUCCEEDED",
        checkpoint={"analysis_signature": current_rules(case["catalog"])},
        automatic_corrections={"mode": "APPLY", "policy_version": POLICY_VERSION, "center_codes": ["1100", "1200"]},
    )
    session.add(job)
    session.flush()
    proposal.created_at, proposal.job_id, proposal.proposal_type = job.created_at, job.id, kind
    proposal.members, proposal.changeset, proposal.changeset_hash = members, payload, digest
    session.commit()

    def factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    return {**case, "job": job, "factory": factory, "material": material}


@pytest.mark.parametrize("status", ["OPEN", "RETURNED"])
def test_lot_review_excludes_automation(auto_case, status):
    from vx_materials_api.db.models import LotReview

    case = auto_case()
    case["session"].add(
        LotReview(
            tenant_id=case["material"].tenant_id,
            lot_key="real-lot",
            tier=1,
            proposal_type="UNIT_CORRECTION",
            proposal_versions={str(case["proposal"].id): 1},
            status=status,
            created_by_user_id=case["principals"][0].user_id,
        )
    )
    case["session"].commit()
    assert execute(case).reasons == ["HUMAN_LOT_REVIEW"]
    assert case["proposal"].status == "PENDING" and case["material"].version == 1


@pytest.mark.parametrize("case_type", ["tenant", "center", "fiscal", "scope_effect", "hash", "rules"])
def test_scope_and_content_are_rechecked(auto_case, monkeypatch, case_type):
    case = auto_case()
    if case_type == "tenant":
        case["proposal"].tenant_id = uuid.uuid4()
    elif case_type == "center":
        monkeypatch.setenv("AUTHORIZED_CENTER_CODES", "9999")
    elif case_type == "fiscal":
        case["proposal"].fiscal_review_status = "PENDING"
    elif case_type == "hash":
        case["proposal"].changeset_hash = "changed"
    elif case_type == "rules":
        case["job"].checkpoint = {"analysis_signature": "other-rules"}
    elif case_type == "scope_effect":
        writer = automatic._decide_current

        def corrupted(db, actor, proposal, decision, catalog, interpretations, changes, materials, *args):
            result = writer(db, actor, proposal, decision, catalog, interpretations, changes, materials, *args)
            materials[0].manufacturer = "FORBIDDEN"
            return result

        monkeypatch.setattr(automatic, "_decide_current", corrupted)
    case["session"].commit()
    result = execute(case)
    # Proposta de outro tenant sequer entra no conjunto congelado do job.
    if case_type == "tenant":
        assert result is None
    else:
        assert result.status in {"REVIEW", "STALE"}, result.reasons
    assert case["material"].version == 1
    assert case["material"].manufacturer != "FORBIDDEN"


@pytest.mark.parametrize("human", [True, False])
def test_concurrent_worker_and_human_apply_only_once(migrated_url, records, monkeypatch, human):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from approval_fixtures import seed_case
    from sqlalchemy import create_engine, delete, func
    from sqlalchemy.orm import sessionmaker

    from vx_materials_api.db.models import (
        AutomaticCorrectionRun,
        Dataset,
        InventoryConsolidation,
        MaterialInventorySnapshot,
        MaterialMaster,
        OperationRequest,
        SanitizationProposal,
        UserSso,
    )
    from vx_materials_api.errors import ApiError
    from vx_materials_api.schemas.proposals import ProposalDecision
    from vx_materials_api.services.approval_service import decide_proposal

    monkeypatch.setenv("AUTOMATIC_CORRECTION_MODE", "APPLY")
    monkeypatch.setenv("APP_ENV", "local")
    engine = create_engine(migrated_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    tenant = uuid.uuid4()
    with engine.connect() as connection:
        with Session(connection, expire_on_commit=False) as db:
            catalog, dataset, materials, snapshots, proposal, principals = seed_case(db, tenant)
            case = {
                "session": db,
                "catalog": catalog,
                "dataset": dataset,
                "materials": materials,
                "snapshots": snapshots,
                "proposal": proposal,
                "principals": principals,
            }
            case = prepare_case(case, records, connection)
            db.commit()
        connection.commit()
    job_id, proposal_id, material_id = case["job"].id, proposal.id, materials[0].id
    run_id = automatic.initialize_run(factory, job_id, catalog)
    barrier = Barrier(2)

    def worker(index):
        barrier.wait(timeout=10)
        if not human or index == 0:
            automatic.process_proposal(factory, run_id, proposal_id, catalog)
        else:
            with factory() as db:
                try:
                    decide_proposal(
                        db,
                        principals[0],
                        proposal_id,
                        ProposalDecision(
                            expected_version=1,
                            review_area="TECHNICAL",
                            decision="APPROVE",
                            reason="Conferência humana concorrente.",
                        ),
                        uuid.uuid4(),
                        str(uuid.uuid4()),
                        catalog,
                    )
                    db.commit()
                except ApiError as error:
                    db.rollback()
                    assert error.status == 409

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker, [0, 1]))
        with factory() as db:
            assert db.get(MaterialMaster, material_id).version == 2
            assert db.get(SanitizationProposal, proposal_id).status == "APPLIED"
            assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant)) == 1
    finally:
        with factory.begin() as db:
            db.execute(
                delete(OperationRequest).where(
                    OperationRequest.user_id.in_(select(UserSso.id).where(UserSso.tenant_id == tenant))
                )
            )
            for model in (
                AutomaticCorrectionResult,
                AutomaticCorrectionRun,
                AuditLog,
                InventoryConsolidation,
                SanitizationProposal,
                MaterialInventorySnapshot,
                MaterialMaster,
                BatchJob,
                Dataset,
                UserSso,
            ):
                db.execute(delete(model).where(model.tenant_id == tenant))
        engine.dispose()


@pytest.mark.parametrize("status", ["APPLIED", "REJECTED", "STALE"])
def test_decided_proposals_are_not_frozen_into_execution(auto_case, status):
    case = auto_case()
    case["proposal"].status = status
    case["session"].commit()
    assert execute(case) is None
    assert case["material"].version == 1


def test_reused_old_proposal_is_not_armed_by_new_job(auto_case):
    from datetime import timedelta

    case = auto_case()
    case["proposal"].created_at = case["job"].created_at - timedelta(days=1)
    case["session"].commit()
    assert execute(case) is None
    assert case["proposal"].status == "PENDING" and case["material"].version == 1


def test_public_retry_recovers_index_with_off_mode_and_is_idempotent(auto_case, monkeypatch):
    case = auto_case()
    result = execute(case)
    result.index_status = "FAILED"
    case["session"].commit()
    monkeypatch.setenv("AUTOMATIC_CORRECTION_MODE", "OFF")
    monkeypatch.setattr(automatic.settings, "batch_database_url", lambda: "unused")
    monkeypatch.setattr(automatic, "refresh_automatic_materials", lambda *_: {"recovered": True})
    path = f"/api/v1/batch/jobs/{case['job'].id}/automatic-corrections/retry"
    for _ in range(2):
        response = case["client"].post(path, json={}, headers=case["headers"])
        assert response.status_code == 202, response.text
    case["session"].expire_all()
    assert result.index_status == "CURRENT"
    assert case["material"].version == 2
    assert len(list(case["session"].scalars(select(AuditLog)))) == 1


def test_retry_cannot_enable_mode_or_take_unarmed_job(auto_case):
    case = auto_case()
    path = f"/api/v1/batch/jobs/{case['job'].id}/automatic-corrections/retry"
    assert case["client"].post(path, json={"mode": "APPLY"}, headers=case["headers"]).status_code == 422
    assert case["client"].post(path, json={}, headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 403
    case["job"].automatic_corrections = {}
    case["session"].commit()
    response = case["client"].post(path, json={}, headers=case["headers"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "AUTOMATION_NOT_ARMED"
    case["app"].state.test_principal = case["principals"][2]
    assert case["client"].post(path, json={}, headers=case["headers"]).status_code == 403
    assert case["material"].version == 1
