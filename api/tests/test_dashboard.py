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
            "STATUS": "ATIVO",
            "NCM": "" if snapshot.material_id == materials[0].id else "8421.23.00",
            "UNIDADE_MEDIDA": "PÇ" if snapshot.material_id == materials[0].id else "PC",
        }
    # Estado importado realista: os valores só mudam durante a aplicação auditada.
    materials[0].ncm, materials[0].unit = None, "PÇ"
    proposal.fiscal_review_status = "PENDING"
    proposal.changeset = {**proposal.changeset, "sources": {"ncm": "Referência PDM", "unit": "Alias da unidade"}}
    from vx_materials_api.schemas.proposals import proposal_hash

    proposal.changeset_hash = proposal_hash(proposal.members, proposal.changeset)
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
        "active": 2,
        "blocked": 0,
        "obsolete": 0,
        "missing_ncm": 1,
        "noncanonical_unit": 1,
        # Os dois membros estão ativos no original; um é duplicado proposto.
        "duplicate_codes": 1,
    }
    assert data["pipeline"] == {"proposals_total": 1, "pending": 1, "applied": 0, "rejected": 0, "stale": 0}
    assert data["comparison_status"] == "AFTER_SNAPSHOT_NOT_AVAILABLE" and data["after"] is None
    assert data["after_snapshot"] is None
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
        # Os indicadores brutos são estáveis; duplicados seguem propostas pendentes/aplicadas.
        assert data["before"] == {**before, "duplicate_codes": int(status in {"PENDING", "APPLIED"})}
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
        assert response.json()["status"] == "PENDING"
        data = client.get(PATH).json()
        assert data["pipeline"] == {"proposals_total": 1, "pending": 1, "applied": 0, "rejected": 0, "stale": 0}
        assert data["before"] == before
        assert data["after"] is None and data["evaluation"]["merge_precision"] is None
    login(client, "AUDITOR_FISCAL")
    fiscal = {**body, "expected_version": response.json()["version"], "review_area": "FISCAL"}
    fiscal.pop("primary_material_code")
    fiscal_headers = write_headers(client)
    for _ in range(2):
        applied = client.post(f"/api/v1/sanitization/{proposal.id}/decide", json=fiscal, headers=fiscal_headers)
        assert applied.status_code == 200 and applied.json()["status"] == "APPLIED", applied.text
        assert client.get(PATH).json()["pipeline"]["applied"] == 1
    financial = client.get(PATH + "?view=executive").json()["financial"]
    assert financial["inventory_book_value"] == "60" and financial["realized_savings"] is None


SNAPSHOTS = "/api/v1/dashboard/snapshots"


def write_headers(client, key=None):
    me = client.get("/api/v1/auth/me").json()
    return {
        "Origin": "http://localhost:8000",
        "X-CSRF-Token": me["csrf_token"],
        "Idempotency-Key": key or str(uuid.uuid4()),
    }


def approve(client, proposal):
    body = {
        "expected_version": proposal.version,
        "review_area": "TECHNICAL",
        "decision": "APPROVE",
        "reason": "Identidade e dados originais conferidos.",
        "primary_material_code": "100",
    }
    response = client.post(f"/api/v1/sanitization/{proposal.id}/decide", json=body, headers=write_headers(client))
    assert response.status_code == 200, response.text
    if response.json()["status"] == "PENDING":
        login(client, "AUDITOR_FISCAL")
        fiscal = {**body, "expected_version": response.json()["version"], "review_area": "FISCAL"}
        fiscal.pop("primary_material_code")
        response = client.post(f"/api/v1/sanitization/{proposal.id}/decide", json=fiscal, headers=write_headers(client))
        assert response.status_code == 200 and response.json()["status"] == "APPLIED", response.text
        login(client)


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    return tmp_path


def test_snapshot_refuses_changes_without_an_applied_proposal(dashboard_case, storage):
    """No caso semeado, a master difere do original e a unificação ainda está pendente."""
    client, db, _, materials, *_ = dashboard_case
    materials[0].unit = "KG"
    materials[1].status = "BLOQUEADO"
    db.commit()
    login(client)
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "UNTRACEABLE_CHANGES"
    assert error["details"]["material_codes"] == ["100", "200"]
    assert not list(storage.rglob("*.json"))
    assert client.get(PATH).json()["comparison_status"] == "AFTER_SNAPSHOT_NOT_AVAILABLE"


def test_snapshot_after_approval_compares_before_and_after(dashboard_case, storage):
    client, _, dataset, _, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 201, response.text
    snapshot = response.json()
    assert snapshot["dataset_id"] == str(dataset.id)
    assert snapshot["applied_proposals"] == 1 and snapshot["materials_changed"] == 2
    assert snapshot["inventory_value_conserved"] is True
    data = client.get(PATH).json()
    assert data["comparison_status"] == "AVAILABLE"
    assert data["after_snapshot"] == snapshot
    # 100 ganhou NCM e unidade canônica; 200 passou de ativo a bloqueado na unificação.
    assert data["after"] == {
        "materials_total": 2,
        "active": 1,
        "blocked": 1,
        "obsolete": 0,
        "missing_ncm": 0,
        "noncanonical_unit": 0,
        "duplicate_codes": 0,
    }
    from test_contracts import validator

    validator({"$ref": "#/components/schemas/DashboardMetrics"}).validate(data)


def test_every_change_in_the_export_traces_to_applied_proposals(dashboard_case, storage):
    client, _, _, _, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    snapshot = client.post(SNAPSHOTS, json={}, headers=write_headers(client)).json()
    export = json.loads((storage / snapshot["export_key"]).read_text())
    assert export["applied_proposal_ids"] == [str(proposal.id)]
    assert {change["material_code"] for change in export["changes"]} == {"100", "200"}
    for change in export["changes"]:
        assert change["proposal_ids"] == [str(proposal.id)]
        assert set(change["before"]) == set(change["after"]) == set(change["fields"])
    first = next(change for change in export["changes"] if change["material_code"] == "100")
    assert first["before"] == {"ncm": None, "unit": "PÇ"} and first["after"] == {"ncm": "8421.23.00", "unit": "PC"}
    assert export["summary"]["inventory_value_before"] == export["summary"]["inventory_value_after"] == "60.00"


def test_snapshot_is_idempotent_and_needs_governance(dashboard_case, storage):
    client, _, _, _, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    key = str(uuid.uuid4())
    first = client.post(SNAPSHOTS, json={}, headers=write_headers(client, key))
    again = client.post(SNAPSHOTS, json={}, headers=write_headers(client, key))
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    assert len(list(storage.rglob("quality_snapshot.json"))) == 1
    other = client.post(SNAPSHOTS, json={"dataset_id": str(uuid.uuid4())}, headers=write_headers(client, key))
    assert other.status_code == 409
    assert client.post(SNAPSHOTS, json={}, headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 403
    login(client, "AUDITOR_FISCAL")
    assert client.post(SNAPSHOTS, json={}, headers=write_headers(client)).status_code == 403


def test_after_counts_follow_the_snapshot_not_later_master_changes(dashboard_case, storage):
    client, db, _, materials, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    after = client.get(PATH).json()["after"]
    db.refresh(materials[0])
    materials[0].ncm = None
    db.commit()
    assert client.get(PATH).json()["after"] == after


def test_after_counts_respect_center_scope(dashboard_case, storage):
    client, db, _, _, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    scoped = metrics(db, principal(("1200",)))
    assert scoped.before.materials_total == scoped.after.materials_total == 1
    assert scoped.after.blocked == 1


def test_duplicates_before_and_after_follow_merge_proposals(dashboard_case, storage):
    client, db, _, _, snapshots, proposal, _ = dashboard_case
    for snapshot in snapshots:
        snapshot.raw_record = {**snapshot.raw_record, "STATUS": "ATIVO"}
    db.commit()
    login(client)
    assert client.get(PATH).json()["before"]["duplicate_codes"] == 1
    approve(client, proposal)
    client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    data = client.get(PATH).json()
    assert data["before"]["duplicate_codes"] == 1
    assert data["after"]["duplicate_codes"] == 0


@pytest.mark.parametrize("field,value", [("unit", "KG"), ("ncm", "1111.11.11"), ("status", "OBSOLETO")])
def test_snapshot_refuses_values_not_recorded_by_the_application(dashboard_case, storage, field, value):
    client, db, _, materials, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    db.refresh(materials[0])
    setattr(materials[0], field, value)
    db.commit()
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UNTRACEABLE_CHANGES"
    assert response.json()["error"]["details"]["material_codes"] == ["100"]
    assert not list(storage.rglob("quality_snapshot.json"))


def fiscal_correction(client, db, material, original_proposal, ncm):
    from copy import deepcopy

    from vx_materials_api.schemas.proposals import proposal_hash

    db.refresh(material)
    members = [{**original_proposal.members[0], "material_id": str(material.id), "expected_version": material.version}]
    changes = deepcopy(original_proposal.changeset)
    changes["after"]["ncm"] = ncm
    changes["sources"]["ncm"] = "Referência NCM do PDM"
    proposal = SanitizationProposal(
        tenant_id=TENANT_ID,
        proposal_type="NCM_CORRECTION",
        members=members,
        primary_material_id=material.id,
        changeset=changes,
        changeset_hash=proposal_hash(members, changes),
        technical_review_status="NOT_REQUIRED",
        fiscal_review_status="PENDING",
    )
    db.add(proposal)
    db.commit()
    login(client, "AUDITOR_FISCAL")
    response = client.post(
        f"/api/v1/sanitization/{proposal.id}/decide",
        json={
            "expected_version": 1,
            "review_area": "FISCAL",
            "decision": "APPROVE",
            "reason": "NCM conferido.",
        },
        headers=write_headers(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPLIED"
    login(client)
    return proposal


def test_ncm_application_does_not_authorize_an_extra_unit_change(dashboard_case, storage):
    client, db, dataset, materials, snapshots, proposal, _ = dashboard_case
    materials[0].unit = "PC"
    # O NCM é a única diferença original legítima; a unidade ganha uma diferença posterior sem revisão.
    for snapshot in snapshots:
        snapshot.raw_record = {
            "STATUS": "ATIVO",
            "NCM": next(m.ncm for m in materials if m.id == snapshot.material_id),
            "UNIDADE_MEDIDA": "PC",
        }
    db.commit()
    fiscal_correction(client, db, materials[0], proposal, "84212300")
    db.refresh(materials[0])
    materials[0].unit = "KG"
    db.commit()
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UNTRACEABLE_CHANGES"
    assert not list(storage.rglob("quality_snapshot.json"))


def test_snapshot_keeps_field_provenance_for_sequential_applications(dashboard_case, storage):
    client, db, dataset, materials, _, first, _ = dashboard_case
    login(client)
    approve(client, first)
    second = fiscal_correction(client, db, materials[0], first, "84212300")
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 201, response.text
    export = json.loads((storage / response.json()["export_key"]).read_text())
    change = next(change for change in export["changes"] if change["material_code"] == "100")
    assert change["field_proposal_ids"]["ncm"] == [str(first.id), str(second.id)]
    assert change["field_proposal_ids"]["unit"] == [str(first.id)]
    assert change["after"]["ncm"] == "84212300"
    assert export["summary"]["inventory_value_before"] == export["summary"]["inventory_value_after"] == "60.00"


def test_snapshot_requires_application_event_not_only_applied_status(dashboard_case, storage):
    client, db, _, materials, _, proposal, _ = dashboard_case
    proposal.status = "APPLIED"
    materials[0].ncm, materials[0].unit = proposal.changeset["after"]["ncm"], "PC"
    materials[1].status = "BLOQUEADO"
    db.commit()
    login(client)
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UNTRACEABLE_CHANGES"
    assert not list(storage.rglob("quality_snapshot.json"))


def test_snapshot_rejects_a_gap_between_approved_applications(dashboard_case, storage):
    client, db, _, materials, _, first, _ = dashboard_case
    login(client)
    approve(client, first)
    db.refresh(materials[0])
    materials[0].ncm = "1111.11.11"
    db.commit()
    fiscal_correction(client, db, materials[0], first, "84212300")
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UNTRACEABLE_CHANGES"
    assert not list(storage.rglob("quality_snapshot.json"))


def test_missing_initial_application_cannot_be_hidden_by_later_approval(dashboard_case, storage):
    from sqlalchemy import delete

    from vx_materials_api.db.models import AuditLog

    client, db, _, materials, snapshots, first, _ = dashboard_case
    for snapshot in snapshots:
        snapshot.raw_record = {**snapshot.raw_record, "UNIDADE_MEDIDA": "PC"}
    db.commit()
    login(client)
    approve(client, first)
    # Histórico incompleto simulado somente no banco descartável de teste.
    db.execute(delete(AuditLog).where(AuditLog.entity_id == str(first.id)))
    db.commit()
    fiscal_correction(client, db, materials[0], first, "84212300")
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UNTRACEABLE_CHANGES"
    assert not list(storage.rglob("quality_snapshot.json"))
    assert client.get(PATH).json()["after_snapshot"] is None


def test_unapproved_initial_change_is_not_hidden_by_a_noop_application(dashboard_case, storage):
    from vx_materials_api.schemas.proposals import proposal_hash

    client, db, _, materials, snapshots, proposal, _ = dashboard_case
    primary = materials[0]
    primary.unit = "PÇ"
    for snapshot in snapshots:
        snapshot.raw_record = {
            **snapshot.raw_record,
            "NCM": primary.ncm,
            "UNIDADE_MEDIDA": "PÇ" if snapshot.material_id == primary.id else "PC",
        }
    db.commit()
    primary.unit = "PC"
    primary.version += 1
    proposal.members = [
        {**member, "expected_version": next(m.version for m in materials if str(m.id) == member["material_id"])}
        for member in proposal.members
    ]
    proposal.changeset_hash = proposal_hash(proposal.members, proposal.changeset)
    db.commit()
    login(client)
    approve(client, proposal)
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "UNTRACEABLE_CHANGES"
    assert not list(storage.rglob("quality_snapshot.json"))
    assert client.get(PATH).json()["after_snapshot"] is None
