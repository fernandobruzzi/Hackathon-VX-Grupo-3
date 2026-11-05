"""Repeticao da mesma operacao nunca duplica mudancas ou eventos."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from approval_fixtures import decide, seed_case
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from vx_materials_api.db.models import (
    AuditLog,
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


def test_identical_retry_returns_the_original_response(approval_case):
    case = approval_case
    first = decide(case)
    second = decide(case)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    db = case["session"]
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
    assert db.scalar(select(func.count()).select_from(OperationRequest)) == 1
    db.expire_all()
    assert case["materials"][0].version == 2


def test_reusing_key_with_different_body_is_conflict(approval_case):
    case = approval_case
    assert decide(case).status_code == 200
    retry = decide(case, payload=case["payload"] | {"reason": "Outra justificativa"})
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_a_new_key_cannot_apply_an_already_applied_proposal(approval_case):
    case = approval_case
    assert decide(case).status_code == 200
    retry = decide(case, key=str(uuid.uuid4()))
    assert retry.status_code == 409
    assert case["session"].scalar(select(func.count()).select_from(AuditLog)) == 1


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_transactions_apply_only_once(migrated_url, same_key):
    engine = create_engine(migrated_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    tenant = uuid.uuid4()
    with factory() as db:
        catalog, dataset, materials, snapshots, proposal, principals = seed_case(db, tenant)
    barrier = Barrier(2)
    shared_key = uuid.uuid4()
    payload = ProposalDecision(
        expected_version=1,
        review_area="TECHNICAL",
        decision="APPROVE",
        primary_material_code="100",
        reason="Revisao concorrente.",
    )

    def worker(index):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                result = decide_proposal(
                    db,
                    principals[0],
                    proposal.id,
                    payload,
                    shared_key if same_key else uuid.uuid4(),
                    str(uuid.uuid4()),
                    catalog,
                )
                db.commit()
                return result
            except ApiError as error:
                db.rollback()
                return error.status, {"code": error.code}

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, [0, 1]))
        assert sorted(result[0] for result in results) == ([200, 200] if same_key else [200, 409])
        if same_key:
            assert results[0][1] == results[1][1]
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant)) == 1
            assert db.get(MaterialMaster, materials[0].id).version == 2
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(InventoryConsolidation)
                    .where(InventoryConsolidation.tenant_id == tenant)
                )
                == 3
            )
    finally:
        # Limpa somente o tenant aleatorio criado neste banco _test validado pelo conftest.
        with factory.begin() as db:
            db.execute(
                delete(OperationRequest).where(
                    OperationRequest.user_id.in_(select(UserSso.id).where(UserSso.tenant_id == tenant))
                )
            )
            for model in (
                AuditLog,
                InventoryConsolidation,
                SanitizationProposal,
                MaterialInventorySnapshot,
                MaterialMaster,
                Dataset,
                UserSso,
            ):
                db.execute(delete(model).where(model.tenant_id == tenant))
        engine.dispose()
