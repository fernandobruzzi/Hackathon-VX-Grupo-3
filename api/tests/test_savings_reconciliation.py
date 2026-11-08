"""Regressões de reconciliação: confirmação, escopo e evidência financeira histórica."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from test_dashboard import dashboard_case as dashboard_case
from test_dashboard import principal
from test_stock_reservations import case as case

from vx_materials_api.db.models import (
    AuditLog,
    ChatSession,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialRequest,
    StockMovement,
    StockReservation,
    UserSso,
)
from vx_materials_api.services.metrics_service import metrics


def component(db, key):
    result = metrics(db, principal(role="ROLE_AUDITOR_FISCAL"), view="executive")
    return next(row for row in result.financial.components if row.key == key)


def test_composite_merge_counts_deactivated_code_from_applied_transition(dashboard_case):
    _, db, _, materials, _, proposal, _ = dashboard_case
    proposal.proposal_type, proposal.status = "COMPOSITE", "APPLIED"
    materials[1].status = "BLOQUEADO"
    db.add(
        AuditLog(
            tenant_id=proposal.tenant_id,
            actor_type="USER",
            action="PROPOSAL_APPROVE_FISCAL",
            entity_type="sanitization_proposal",
            entity_id=str(proposal.id),
            before_json={"status": "PENDING", "materials": [{"id": str(materials[1].id), "status": "ATIVO"}]},
            after_json={
                "status": "APPLIED",
                "changeset_hash": proposal.changeset_hash,
                "materials": [{"id": str(materials[1].id), "status": "BLOQUEADO"}],
            },
        )
    )
    db.commit()
    assert component(db, "duplicate_codes").count == "1"


def test_stock_counts_chat_quantity_and_retains_price_after_later_merge(dashboard_case):
    _, db, dataset, materials, snapshots, proposal, _ = dashboard_case
    owner = db.query(UserSso).first()
    request = MaterialRequest(
        tenant_id=owner.tenant_id,
        requester_user_id=owner.id,
        original_text="2 filtros",
        material_id=materials[0].id,
        quantity=Decimal(2),
        unit="PC",
        center_code="1100",
        status="EM_ATENDIMENTO",
    )
    db.add(request)
    db.flush()
    reservation = StockReservation(
        tenant_id=owner.tenant_id,
        request_id=request.id,
        material_id=materials[0].id,
        center_code="1100",
        quantity=Decimal(2),
        unit="PC",
        status="CONSUMIDA",
        dataset_id=dataset.id,
        created_by_user_id=owner.id,
    )
    db.add(reservation)
    db.flush()
    delivery = StockMovement(
        tenant_id=owner.tenant_id,
        reservation_id=reservation.id,
        movement_type="ENTREGA",
        quantity=Decimal(2),
        dataset_id=dataset.id,
        created_by_user_id=owner.id,
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db.add(delivery)
    db.flush()
    db.add(
        StockMovement(
            tenant_id=owner.tenant_id,
            reservation_id=reservation.id,
            movement_type="REVERSAO",
            quantity=Decimal("0.5"),
            dataset_id=dataset.id,
            created_by_user_id=owner.id,
            reverses_movement_id=delivery.id,
        )
    )
    db.commit()
    # Uma entrega operacional fora do chat não pertence ao denominador pedido na #316.
    assert component(db, "stock_fulfilled").amount_brl is None
    assert component(db, "stock_fulfilled").count == "0"
    assert component(db, "stock_fulfilled").quantities == {}
    chat = ChatSession(tenant_id=owner.tenant_id, owner_user_id=owner.id, status="OPEN", context={})
    db.add(chat)
    db.flush()
    request.chat_session_id = chat.id
    db.commit()
    measured = component(db, "stock_fulfilled")
    assert Decimal(measured.count) == Decimal("1.5") and measured.count_unit == "PC"
    assert measured.amount_brl == "15.00"
    assert measured.stock_evidence[0].unit_price == "10"
    assert measured.stock_evidence[0].snapshot_ids == [str(snapshots[0].id)]
    db.add(
        InventoryConsolidation(
            source_snapshot_id=snapshots[0].id,
            tenant_id=owner.tenant_id,
            primary_material_id=materials[1].id,
            proposal_id=proposal.id,
            factor=Decimal(1),
            unit="PC",
            conversion_source="Mesma unidade",
        )
    )
    db.add(
        AuditLog(
            tenant_id=owner.tenant_id,
            actor_type="USER",
            action="PROPOSAL_APPROVE_TECHNICAL",
            entity_type="sanitization_proposal",
            entity_id=str(proposal.id),
            created_at=datetime.now(UTC),
            before_json={"status": "PENDING"},
            after_json={"status": "APPLIED", "changeset_hash": proposal.changeset_hash},
        )
    )
    db.commit()
    assert component(db, "stock_fulfilled").amount_brl == "15.00"


def test_delivery_freezes_price_privately(case):
    from sqlalchemy import select
    from test_stock_deliveries import deliver, setup

    client, db = case
    dataset, material, _, clerk, reservation = setup(client, db)
    snapshot = db.scalar(select(MaterialInventorySnapshot).where(MaterialInventorySnapshot.material_id == material.id))
    snapshot.unit_price = Decimal("12.50")
    db.commit()
    response = deliver(client, clerk, db, reservation, "2")
    assert response.status_code == 201, response.text
    assert "unit_price" not in response.text and "savings_basis" not in response.text
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "STOCK_DELIVERED"))
    assert audit.after_json["savings_basis"]["unit_price"] == "12.50"
    assert audit.after_json["savings_basis"]["dataset_id"] == str(dataset.id)


def test_mixed_periods_have_no_aggregate_and_review_hours_are_explicit(dashboard_case, tmp_path, monkeypatch):
    from test_savings_metrics import assumptions

    _, db, *_ = dashboard_case
    assumptions(tmp_path, monkeypatch)
    result = metrics(db, principal(role="ROLE_AUDITOR_FISCAL"), view="executive").financial
    assert result.estimated_savings is None
    assert component(db, "batch_reviews").estimated_hours == "0"
