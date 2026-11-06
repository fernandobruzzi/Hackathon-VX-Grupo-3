"""Integração de sessão real da aplicação, RBAC e aprovação; sem provedor de identidade injetado."""

import uuid

import pytest
from approval_fixtures import seed_case
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import AuditLog
from vx_materials_api.main import create_app
from vx_materials_api.schemas.proposals import proposal_hash


@pytest.fixture
def authenticated_case(connection, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    catalog, dataset, materials, snapshots, proposal, _ = seed_case(db, TENANT_ID)

    def factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    app = create_app(session_factory=factory)
    app.state.pdm_catalog = catalog
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client, db, proposal, materials, snapshots
    db.close()


def login(client, persona):
    result = client.post(
        "/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": "http://localhost:8000"}
    )
    assert result.status_code == 200, result.text
    return client.get("/api/v1/auth/me").json()


def decision(client, me, proposal, area="TECHNICAL", version=1, key=None, **extra):
    return client.post(
        f"/api/v1/sanitization/{proposal.id}/decide",
        json={
            "expected_version": version,
            "review_area": area,
            "decision": "APPROVE",
            "reason": "Identidade e fontes conferidas.",
            **extra,
        },
        headers={
            "Origin": "http://localhost:8000",
            "X-CSRF-Token": me["csrf_token"],
            "Idempotency-Key": key or str(uuid.uuid4()),
            "X-Role": "ROLE_GOVERNANCA_PDM",
        },
    )


@pytest.mark.parametrize(
    "persona,area",
    [
        ("SOLICITANTE_OPERACAO", "TECHNICAL"),
        ("SOLICITANTE_OPERACAO", "FISCAL"),
        ("GESTOR_CADASTRO", "FISCAL"),
        ("AUDITOR_FISCAL", "TECHNICAL"),
    ],
)
def test_wrong_session_role_receives_403_even_with_a_forged_role_header(authenticated_case, persona, area):
    client, db, proposal, materials, _ = authenticated_case
    me = login(client, persona)
    response = decision(client, me, proposal, area=area)
    assert response.status_code == 403, response.text
    db.expire_all()
    assert all(material.version == 1 and material.status == "ATIVO" for material in materials)
    assert db.scalar(select(AuditLog)) is None


def test_local_governance_and_fiscal_sessions_apply_once_and_record_their_real_actors(authenticated_case):
    client, db, proposal, materials, snapshots = authenticated_case
    materials[1].ncm = None
    proposal.fiscal_review_status = "PENDING"
    proposal.changeset = {**proposal.changeset, "sources": {"ncm": "Conferência fiscal dos códigos originais"}}
    proposal.changeset_hash = proposal_hash(proposal.members, proposal.changeset, proposal.evidence_ids)
    db.commit()
    original = [(row.quantity, row.total_value, row.unit) for row in snapshots]
    governance = login(client, "GESTOR_CADASTRO")
    before = client.get(f"/api/v1/sanitization/{proposal.id}")
    assert before.status_code == 200
    assert "consolidated_value_brl" not in before.json()
    assert all("value_brl" not in member for member in before.json()["members"])
    first = decision(client, governance, proposal, primary_material_code="100")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    db.expire_all()
    assert all(material.version == 1 for material in materials)
    fiscal = login(client, "AUDITOR_FISCAL")
    assert fiscal["user"]["id"] != governance["user"]["id"]
    assert fiscal["csrf_token"] != governance["csrf_token"]
    key = str(uuid.uuid4())
    second = decision(client, fiscal, proposal, "FISCAL", first.json()["version"], key)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPLIED"
    replay = decision(client, fiscal, proposal, "FISCAL", first.json()["version"], key)
    assert replay.json() == second.json()
    db.expire_all()
    events = db.scalars(select(AuditLog).where(AuditLog.entity_id == str(proposal.id))).all()
    assert len(events) == 2
    assert {(str(event.actor_user_id), event.effective_role) for event in events} == {
        (governance["user"]["id"], "ROLE_GOVERNANCA_PDM"),
        (fiscal["user"]["id"], "ROLE_AUDITOR_FISCAL"),
    }
    assert all(event.before_json and event.after_json and event.reason for event in events)
    assert [(row.quantity, row.total_value, row.unit) for row in snapshots] == original
    after = client.get(f"/api/v1/sanitization/{proposal.id}").json()
    assert after["consolidated_value_brl"] == "60"


def test_actor_cannot_be_supplied_with_an_authenticated_decision(authenticated_case):
    client, _, proposal, _, _ = authenticated_case
    me = login(client, "GESTOR_CADASTRO")
    assert decision(client, me, proposal, actor_id=str(uuid.uuid4())).status_code == 422


def test_known_proposal_uuid_does_not_bypass_inventory_center_scope(authenticated_case):
    client, db, proposal, _, snapshots = authenticated_case
    snapshots[0].center_code = "9999"
    db.commit()
    me = login(client, "GESTOR_CADASTRO")
    assert client.get(f"/api/v1/sanitization/{proposal.id}").status_code == 404
    assert decision(client, me, proposal).status_code == 404
