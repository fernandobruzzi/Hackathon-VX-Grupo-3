"""Dashboard com sessão local real, dados persistidos e isolamento de recursos."""

import json
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot, SanitizationProposal
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services.metrics_service import metrics

PATH = "/api/v1/dashboard/metrics"


@pytest.fixture
def dashboard_case(connection, monkeypatch):
    from approval_fixtures import seed_case

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    catalog, dataset, materials, snapshots, proposal, _ = seed_case(db, TENANT_ID)
    for snapshot in snapshots:
        snapshot.raw_record = {
            "STATUS": "ATIVO" if snapshot.material_id == materials[0].id else "BLOQUEADO",
            "NCM": "" if snapshot.material_id == materials[0].id else "8421.23.00",
            "UNIDADE_MEDIDA": "PÇ" if snapshot.material_id == materials[0].id else "PC",
        }
    db.commit()
    app = create_app(session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"))
    app.state.pdm_catalog = catalog
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client, db, dataset, materials, snapshots, proposal, app
    db.close()


def login(client, persona="GESTOR_CADASTRO"):
    response = client.post(
        "/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": "http://localhost:8000"}
    )
    assert response.status_code == 200, response.text


def principal(centers=("1100", "1200"), role="ROLE_GOVERNANCA_PDM"):
    return Identity(uuid.uuid4(), TENANT_ID, (role,), permissions_for((role,)), frozenset(centers))


def test_quality_uses_original_distinct_materials_and_has_no_financial_fields(dashboard_case, connection):
    client, _, dataset, _, _, _, _ = dashboard_case
    login(client)
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        response = client.get(PATH)
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["dataset_id"] == str(dataset.id)
    assert data["before"] == {
        "materials_total": 2,
        "active": 1,
        "blocked": 1,
        "obsolete": 0,
        "missing_ncm": 1,
        "noncanonical_unit": 1,
    }
    assert data["pipeline"] == {"proposals_total": 1, "pending": 1, "applied": 0, "rejected": 0, "stale": 0}
    assert data["comparison_status"] == "AFTER_SNAPSHOT_NOT_AVAILABLE" and data["after"] is None
    assert data["evaluation"]["merge_precision"] is None
    assert data["evaluation"]["reviewed_pairs"] == 0
    assert "financial" not in data
    assert not any("total_value" in query or "unit_price" in query for query in queries)
    assert response.headers["cache-control"] == "no-store"
    # A resposta real também respeita o contrato público, não só os exemplos fixos.
    from test_contracts import validator

    validator({"$ref": "#/components/schemas/DashboardMetrics"}).validate(data)


def test_financial_requires_fiscal_session_and_does_not_trust_role_headers(dashboard_case):
    client, _, _, _, _, _, _ = dashboard_case
    login(client)
    denied = client.get(PATH + "?view=executive", headers={"X-Role": "ROLE_AUDITOR_FISCAL"})
    assert denied.status_code == 403
    login(client, "AUDITOR_FISCAL")
    response = client.get(PATH + "?view=executive")
    assert response.status_code == 200, response.text
    financial = response.json()["financial"]
    assert financial["inventory_book_value"] == "60"
    assert financial["realized_savings"] is None and financial["estimated_savings"] is None
    assert financial["data_origin"] == "SYNTHETIC_CHALLENGE_DATA"
    assert "financial" not in client.get(PATH + "?view=quality").json()
    from test_contracts import validator

    validator({"$ref": "#/components/schemas/DashboardMetrics"}).validate(response.json())


def test_anonymous_and_requester_cannot_read_metrics(dashboard_case):
    client, *_ = dashboard_case
    assert client.get(PATH).status_code == 401
    login(client, "SOLICITANTE_OPERACAO")
    assert client.get(PATH).status_code == 403
    assert client.get(PATH + "?view=executive").status_code == 403


def test_financial_values_are_exact_and_incomplete_stock_is_not_zero(dashboard_case):
    client, db, _, _, snapshots, _, _ = dashboard_case
    snapshots[0].total_value = Decimal("123456789012345678901234567890.123456789")
    snapshots[1].total_value = Decimal("0.000000001")
    snapshots[2].total_value = Decimal("0.000000001")
    db.commit()
    login(client, "AUDITOR_FISCAL")
    assert client.get(PATH + "?view=executive").json()["financial"]["inventory_book_value"] == (
        "123456789012345678901234567890.123456791"
    )
    snapshots[0].total_value = None
    db.commit()
    assert client.get(PATH + "?view=executive").json()["financial"]["inventory_book_value"] is None


def test_center_scope_limits_counts_value_and_hides_partial_proposals(dashboard_case):
    _, db, dataset, _, _, _, _ = dashboard_case
    data = metrics(db, principal(("1100",)))
    assert data.before.materials_total == 2
    assert data.pipeline.proposals_total == 0  # O segundo membro também possui estoque em 1200.
    fiscal = metrics(db, principal(("1100",), "ROLE_AUDITOR_FISCAL"), view="executive", dataset_id=dataset.id)
    assert fiscal.financial.inventory_book_value == "30"
    assert fiscal.financial.realized_savings is None


def test_dataset_and_tenant_are_checked_even_for_known_ids(dashboard_case):
    client, db, dataset, _, _, _, app = dashboard_case
    login(client)
    assert client.get(PATH + "?dataset_id=" + str(uuid.uuid4())).status_code == 404
    app.state.request_identity_provider = lambda request, session: replace(principal(), tenant_id=uuid.uuid4())
    assert client.get(PATH + "?dataset_id=" + str(dataset.id)).status_code == 404
    app.state.request_identity_provider = lambda request, session: principal(("9999",))
    assert client.get(PATH).status_code == 404
    app.state.request_identity_provider = lambda request, session: replace(principal(), permissions=frozenset())
    assert client.get(PATH).status_code == 403


def test_counts_track_status_changes_without_inventing_after_or_accuracy(dashboard_case):
    client, db, _, materials, _, proposal, _ = dashboard_case
    login(client)
    before = client.get(PATH).json()["before"]
    materials[0].status = "BLOQUEADO"
    materials[0].ncm = "1111.11.11"
    materials[0].unit = "PC"
    for status in ["APPLIED", "REJECTED", "STALE", "PENDING"]:
        proposal.status = status
        db.commit()
        data = client.get(PATH).json()
        assert data["before"] == before
        assert data["pipeline"][status.lower()] == 1
        assert data["pipeline"]["proposals_total"] == 1
        assert data["after"] is None and data["evaluation"]["merge_precision"] is None


def test_other_datasets_legacy_proposals_and_foreign_tenants_are_not_counted(dashboard_case):
    client, db, _, _, _, proposal, _ = dashboard_case
    login(client)
    for changeset, tenant in [
        ({**proposal.changeset, "dataset_id": str(uuid.uuid4())}, TENANT_ID),
        ({}, TENANT_ID),
        (proposal.changeset, uuid.uuid4()),
    ]:
        db.add(
            SanitizationProposal(
                tenant_id=tenant,
                proposal_type="MERGE",
                members=proposal.members,
                changeset=changeset,
                changeset_hash=proposal.changeset_hash,
            )
        )
    db.commit()
    assert client.get(PATH).json()["pipeline"]["proposals_total"] == 1


def test_explicit_dataset_keeps_original_values_and_empty_funnel(dashboard_case):
    client, db, _, materials, _, _, _ = dashboard_case
    dataset = Dataset(tenant_id=TENANT_ID, files={}, real_material_codes=[])
    db.add(dataset)
    db.flush()
    db.add(
        MaterialInventorySnapshot(
            tenant_id=TENANT_ID,
            dataset_id=dataset.id,
            material_id=materials[0].id,
            center_code="1100",
            quantity=1,
            unit="PC",
            total_value=7,
            source_line=1,
            raw_record={"STATUS": "OBSOLETO", "NCM": " ", "UNIDADE_MEDIDA": "PC"},
        )
    )
    db.commit()
    login(client)
    response = client.get(PATH + "?dataset_id=" + str(dataset.id))
    data = response.json()
    assert data["before"]["materials_total"] == 1 and data["before"]["obsolete"] == 1
    assert data["pipeline"]["proposals_total"] == 0
    assert data["pipeline"]["applied"] == 0
    assert "financial" not in json.dumps(data)


def test_invalid_query_is_rejected(dashboard_case):
    client, *_ = dashboard_case
    login(client)
    assert client.get(PATH + "?view=invalid").status_code == 422
    assert client.get(PATH + "?dataset_id=invalid").status_code == 422


def test_real_approval_and_idempotent_retry_count_one_application(dashboard_case):
    client, _, _, _, _, proposal, _ = dashboard_case
    login(client)
    me = client.get("/api/v1/auth/me").json()
    body = {
        "expected_version": 1,
        "review_area": "TECHNICAL",
        "decision": "APPROVE",
        "reason": "Identidade e dados originais conferidos.",
        "primary_material_code": "100",
    }
    headers = {
        "Origin": "http://localhost:8000",
        "X-CSRF-Token": me["csrf_token"],
        "Idempotency-Key": str(uuid.uuid4()),
    }
    before = client.get(PATH).json()["before"]
    for _ in range(2):
        response = client.post(f"/api/v1/sanitization/{proposal.id}/decide", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "APPLIED"
        data = client.get(PATH).json()
        assert data["pipeline"] == {"proposals_total": 1, "pending": 0, "applied": 1, "rejected": 0, "stale": 0}
        assert data["before"] == before
        assert data["after"] is None and data["evaluation"]["merge_precision"] is None
    login(client, "AUDITOR_FISCAL")
    financial = client.get(PATH + "?view=executive").json()["financial"]
    assert financial["inventory_book_value"] == "60" and financial["realized_savings"] is None
