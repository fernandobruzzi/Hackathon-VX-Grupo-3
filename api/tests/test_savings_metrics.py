"""Economia distingue contagens auditadas, premissas e valores de atendimento."""

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import select
from test_dashboard import approve, login, principal
from test_dashboard import dashboard_case as dashboard_fixture

from vx_materials_api.db.models import AuditLog
from vx_materials_api.services.metrics_service import metrics

dashboard_case = dashboard_fixture


def assumptions(tmp_path, monkeypatch):
    from clients.storage import LocalObjectStore
    from vx_materials_api.savings_assumptions import register_assumptions

    entries = [
        ("registration_cost", "33.33"),
        ("code_annual_cost", "12"),
        ("review_minutes_before", "20"),
        ("review_minutes_after", "12"),
        ("hourly_cost", "100"),
    ]
    payload = {
        "version": "test-v1",
        "assumptions": [
            {"key": key, "value": value, "source": "Hipótese explícita do teste", "recorded_on": "2026-11-08"}
            for key, value in entries
        ],
    }
    register_assumptions(LocalObjectStore(tmp_path), json.dumps(payload).encode())
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("SAVINGS_ASSUMPTIONS_VERSION", "test-v1")


def test_savings_without_assumptions_keeps_counts_and_money_unavailable(dashboard_case, monkeypatch):
    monkeypatch.delenv("SAVINGS_ASSUMPTIONS_VERSION", raising=False)
    client, db, _, _, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    db.expire_all()
    login(client, "AUDITOR_FISCAL")
    result = client.get("/api/v1/dashboard/metrics?view=executive").json()["financial"]
    components = {c["key"]: c for c in result["components"]}
    assert components["duplicate_codes"]["count"] == "1"
    assert components["duplicate_codes"]["amount_brl"] is None
    assert result["estimated_savings"] is None and result["realized_savings"] is None
    assert "financial" not in client.get("/api/v1/dashboard/metrics?view=quality").json()


def test_savings_counts_audited_events_once_and_excludes_measured_stock_from_estimate(
    dashboard_case, tmp_path, monkeypatch
):
    client, db, dataset, materials, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    db.expire_all()
    event = db.scalar(
        select(AuditLog).where(AuditLog.entity_id == str(proposal.id), AuditLog.action == "PROPOSAL_APPROVE_TECHNICAL")
    )
    payload = {**event.after_json, "lot_review": {"lot_review_id": str(uuid.uuid4())}}
    for _ in range(2):
        db.add(
            AuditLog(
                tenant_id=event.tenant_id,
                actor_type="USER",
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                before_json=event.before_json,
                after_json=payload,
                roles_snapshot=[],
            )
        )
    session_id = str(uuid.uuid4())
    for _ in range(2):
        db.add(
            AuditLog(
                tenant_id=event.tenant_id,
                actor_type="USER",
                action="CHAT_EXISTING_CONFIRMED",
                entity_type="chat_session",
                entity_id=session_id,
                roles_snapshot=[],
                after_json={"dataset_id": str(dataset.id), "center_code": "1100", "material_id": str(materials[0].id)},
            )
        )
    db.commit()
    assumptions(tmp_path, monkeypatch)
    result = metrics(db, principal(role="ROLE_AUDITOR_FISCAL"), view="executive").financial
    components = {c.key: c for c in result.components}
    assert components["registration_reuse"].count == "1"
    assert components["batch_reviews"].count == "1"
    assert components["registration_reuse"].amount_brl == "33.33"
    assert components["duplicate_codes"].amount_brl == "12.00"
    assert components["batch_reviews"].amount_brl == "13.33"
    assert result.estimated_savings is None
    assert result.realized_savings is None
    assert components["stock_fulfilled"].kind == "MEASURED_KIT_VALUE"
    assert all(a.source and a.recorded_on == date(2026, 11, 8) for c in components.values() for a in c.assumptions)
    assert len(result.assumption_source.sha256) == 64
    limited = metrics(db, principal(("1100",), "ROLE_AUDITOR_FISCAL"), view="executive").financial
    assert next(c for c in limited.components if c.key == "duplicate_codes").count == "0"


@pytest.mark.parametrize("value", ["NaN", "-1", "1e8", "Infinity"])
def test_assumptions_reject_noncanonical_or_negative_values(tmp_path, value):
    from clients.storage import LocalObjectStore
    from vx_materials_api.savings_assumptions import register_assumptions

    payload = {
        "version": "invalid",
        "assumptions": [{"key": "hourly_cost", "value": value, "source": "Teste", "recorded_on": "2026-11-08"}],
    }
    with pytest.raises(ValueError):
        register_assumptions(LocalObjectStore(tmp_path), json.dumps(payload).encode())


def test_stock_value_uses_deliveries_minus_reversals_and_never_reservations(dashboard_case):
    from vx_materials_api.db.models import ChatSession, MaterialRequest, StockMovement, StockReservation, UserSso

    client, db, dataset, materials, snapshots, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    db.expire_all()
    user = db.scalar(select(UserSso.id).where(UserSso.tenant_id == dataset.tenant_id))
    chat = ChatSession(tenant_id=dataset.tenant_id, owner_user_id=user, status="OPEN", context={})
    db.add(chat)
    db.flush()
    request = MaterialRequest(
        chat_session_id=chat.id,
        tenant_id=dataset.tenant_id,
        requester_user_id=user,
        original_text="3 unidades",
        material_id=materials[0].id,
        quantity=3,
        unit="PC",
        center_code="1100",
        status="EM_ATENDIMENTO",
    )
    db.add(request)
    db.flush()
    reservation = StockReservation(
        tenant_id=dataset.tenant_id,
        request_id=request.id,
        material_id=materials[0].id,
        center_code="1100",
        quantity=3,
        unit="PC",
        dataset_id=dataset.id,
        created_by_user_id=user,
    )
    db.add(reservation)
    db.flush()

    def stock():
        result = metrics(db, principal(role="ROLE_AUDITOR_FISCAL"), view="executive").financial
        return next(c for c in result.components if c.key == "stock_fulfilled")

    assert stock().amount_brl is None and stock().count == "0"  # Reserva não registra preço de entrega.
    delivery = StockMovement(
        tenant_id=dataset.tenant_id,
        reservation_id=reservation.id,
        dataset_id=dataset.id,
        movement_type="ENTREGA",
        quantity=3,
        created_by_user_id=user,
    )
    db.add(delivery)
    db.flush()
    from vx_materials_api.services.savings_stock_basis import capture_stock_basis

    db.add(
        AuditLog(
            tenant_id=dataset.tenant_id,
            actor_type="USER",
            action="STOCK_DELIVERED",
            entity_type="stock_movement",
            entity_id=str(delivery.id),
            after_json={
                "savings_basis": capture_stock_basis(db, dataset.tenant_id, dataset.id, materials[0].id, "1100", "PC")
            },
        )
    )
    db.add(
        StockMovement(
            tenant_id=dataset.tenant_id,
            reservation_id=reservation.id,
            dataset_id=dataset.id,
            movement_type="REVERSAO",
            quantity=1,
            reverses_movement_id=delivery.id,
            created_by_user_id=user,
        )
    )
    db.commit()
    assert stock().count == "2" and stock().amount_brl == "20.00"
    snapshots[0].unit_price = None
    db.commit()
    assert stock().amount_brl == "20.00"  # A evidência da entrega não é recalculada.
    assert capture_stock_basis(db, dataset.tenant_id, dataset.id, materials[0].id, "1100", "PC")["unit_price"] is None
    snapshots[0].unit_price = 11
    db.commit()
    assert stock().amount_brl == "20.00"
    assert capture_stock_basis(db, dataset.tenant_id, dataset.id, materials[0].id, "1100", "PC")["unit_price"] is None
    # Uma entrega nova não escolheria arbitrariamente entre esses preços.
    assert (
        next(
            c
            for c in metrics(db, principal(("1200",), "ROLE_AUDITOR_FISCAL"), view="executive").financial.components
            if c.key == "stock_fulfilled"
        ).amount_brl
        is None
    )


def test_configured_assumptions_fail_explicitly_but_quality_does_not_read_them(dashboard_case, monkeypatch, tmp_path):
    client, *_ = dashboard_case
    monkeypatch.setenv("SAVINGS_ASSUMPTIONS_VERSION", "missing")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    login(client, "AUDITOR_FISCAL")
    assert client.get("/api/v1/dashboard/metrics").status_code == 200
    response = client.get("/api/v1/dashboard/metrics?view=executive")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SAVINGS_ASSUMPTIONS_UNAVAILABLE"


def test_assumption_versions_are_immutable_and_example_is_valid(tmp_path):
    from pathlib import Path

    from clients.storage import LocalObjectStore, ObjectConflictError
    from vx_materials_api.savings_assumptions import register_assumptions

    raw = (Path(__file__).parents[1] / "contracts/fixtures/savings-assumptions.example.json").read_bytes()
    store = LocalObjectStore(tmp_path)
    first = register_assumptions(store, raw)
    assert register_assumptions(store, raw) == first
    changed = json.loads(raw)
    changed["assumptions"][0]["value"] = "99"
    with pytest.raises(ObjectConflictError):
        register_assumptions(store, json.dumps(changed).encode())


def test_delivery_after_import_uses_movement_dataset(dashboard_case):
    from vx_materials_api.db.models import (
        ChatSession,
        Dataset,
        MaterialRequest,
        StockMovement,
        StockReservation,
        UserSso,
    )

    _, db, dataset, materials, _, _, _ = dashboard_case
    old = Dataset(tenant_id=dataset.tenant_id, files={}, real_material_codes=[])
    db.add(old)
    user = db.scalar(select(UserSso.id).where(UserSso.tenant_id == dataset.tenant_id))
    chat = ChatSession(tenant_id=dataset.tenant_id, owner_user_id=user, status="OPEN", context={})
    db.add(chat)
    db.flush()
    request = MaterialRequest(
        chat_session_id=chat.id,
        tenant_id=dataset.tenant_id,
        requester_user_id=user,
        original_text="2 unidades",
        material_id=materials[0].id,
        quantity=2,
        unit="PC",
        center_code="1100",
        status="EM_ATENDIMENTO",
    )
    db.add(request)
    db.flush()
    reservation = StockReservation(
        tenant_id=dataset.tenant_id,
        request_id=request.id,
        material_id=materials[0].id,
        center_code="1100",
        quantity=2,
        unit="PC",
        dataset_id=old.id,
        created_by_user_id=user,
    )
    db.add(reservation)
    db.flush()
    delivery = StockMovement(
        tenant_id=dataset.tenant_id,
        reservation_id=reservation.id,
        dataset_id=dataset.id,
        movement_type="ENTREGA",
        quantity=2,
        created_by_user_id=user,
    )
    db.add(delivery)
    db.flush()
    from vx_materials_api.services.savings_stock_basis import capture_stock_basis

    db.add(
        AuditLog(
            tenant_id=dataset.tenant_id,
            actor_type="USER",
            action="STOCK_DELIVERED",
            entity_type="stock_movement",
            entity_id=str(delivery.id),
            after_json={
                "savings_basis": capture_stock_basis(db, dataset.tenant_id, dataset.id, materials[0].id, "1100", "PC")
            },
        )
    )
    db.add(
        StockMovement(
            tenant_id=dataset.tenant_id,
            reservation_id=reservation.id,
            dataset_id=dataset.id,
            movement_type="REVERSAO",
            quantity=1,
            reverses_movement_id=delivery.id,
            created_by_user_id=user,
        )
    )
    db.commit()
    result = metrics(db, principal(role="ROLE_AUDITOR_FISCAL"), view="executive", dataset_id=dataset.id).financial
    stock = next(c for c in result.components if c.key == "stock_fulfilled")
    assert stock.amount_brl == "10.00" and stock.count == "1"


def test_foreign_primary_in_inherited_link_never_contributes_to_funnel(dashboard_case):
    from vx_materials_api.db.models import InventoryConsolidation, MaterialMaster

    _, db, _, _, snapshots, proposal, _ = dashboard_case
    foreign = MaterialMaster(tenant_id=uuid.uuid4(), source_system="ERP", material_code="foreign", status="ATIVO")
    db.add(foreign)
    db.flush()
    proposal.members = [{**proposal.members[0], "material_id": str(foreign.id)}]
    db.add(
        InventoryConsolidation(
            source_snapshot_id=snapshots[0].id,
            tenant_id=proposal.tenant_id,
            primary_material_id=foreign.id,
            proposal_id=proposal.id,
            factor=1,
            unit="PC",
            conversion_source="Vínculo inconsistente de teste",
        )
    )
    db.commit()
    assert metrics(db, principal()).pipeline.proposals_total == 0
