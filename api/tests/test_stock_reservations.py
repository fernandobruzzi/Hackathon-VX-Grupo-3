"""Reserva transacional e disponibilidade de saldo, com PostgreSQL real (#239)."""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_contracts import validator as contract

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import (
    AuditLog,
    Dataset,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialMaster,
    MaterialRequest,
    OperationRequest,
    SanitizationProposal,
    StockMovement,
    StockReservation,
    UserSso,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.main import create_app
from vx_materials_api.schemas.stock import CreateStockReservation
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services import stock_service

ORIGIN = "http://localhost:8000"
REQUESTS = "/api/v1/material-requests"
AVAILABILITY = "/api/v1/stock/availability"
# Datas distantes: o dataset do teste é sempre o vigente do tenant, mesmo com o kit carregado.
BASE_DATE = datetime(2099, 1, 1, tzinfo=UTC)
NEWER_DATE = datetime(2099, 2, 1, tzinfo=UTC)


def login(client, persona):
    response = client.post("/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()


def headers(me, key=None):
    return {"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": key or str(uuid.uuid4())}


@pytest.fixture
def case(connection, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    app = create_app(session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"))
    with TestClient(app, base_url=ORIGIN) as client:
        with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
            yield client, db


def add_dataset(db, imported_at=BASE_DATE, tenant_id=TENANT_ID):
    row = Dataset(id=uuid.uuid4(), tenant_id=tenant_id, imported_at=imported_at)
    db.add(row)
    db.commit()
    return row


def add_material(db, tenant_id=TENANT_ID, **values):
    row = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        source_system="TEST",
        material_code=str(uuid.uuid4()),
        **{"status": "ATIVO", "unit": "PC", **values},
    )
    db.add(row)
    db.commit()
    return row


def add_stock(db, dataset, material, quantity, center="1200", unit="PC"):
    row = MaterialInventorySnapshot(
        id=uuid.uuid4(),
        tenant_id=dataset.tenant_id,
        dataset_id=dataset.id,
        material_id=material.id,
        center_code=center,
        quantity=Decimal(quantity),
        unit=unit,
        unit_price=Decimal("12.50"),
        total_value=Decimal(quantity) * Decimal("12.50"),
        source_line=db.scalar(select(func.coalesce(func.max(MaterialInventorySnapshot.source_line), 0))) + 1,
        raw_record={},
    )
    db.add(row)
    db.commit()
    return row


def new_request(client, me, material, quantity, center="1200"):
    body = {
        "original_text": "Preciso deste material.",
        "quantity": quantity,
        "unit": material.unit,
        "center_code": center,
        "material_id": str(material.id),
        # Várias solicitações do mesmo material e centro são intencionais aqui (#248).
        "acknowledge_open_requests": True,
    }
    response = client.post(REQUESTS, json=body, headers=headers(me))
    assert response.status_code == 201, response.text
    return response.json()


def reserve(client, me, request, quantity, key=None, version=None):
    return client.post(
        f"{REQUESTS}/{request['id']}/reservations",
        json={"expected_version": version or request["version"], "quantity": quantity},
        headers=headers(me, key),
    )


def availability(client, material, center="1200"):
    response = client.get(AVAILABILITY, params={"material_id": str(material.id), "center_code": center})
    assert response.status_code == 200, response.text
    return response.json()


def snapshot_state(db):
    return db.execute(
        select(
            MaterialInventorySnapshot.id,
            MaterialInventorySnapshot.quantity,
            MaterialInventorySnapshot.unit,
            MaterialInventorySnapshot.total_value,
        ).order_by(MaterialInventorySnapshot.id)
    ).all()


def counts(db):
    return {
        table.__tablename__: db.scalar(select(func.count()).select_from(table))
        for table in (StockReservation, StockMovement, AuditLog, OperationRequest, MaterialRequest)
    }


def test_reservation_reduces_availability_seen_by_other_requests(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "6")
    requester = login(client, "SOLICITANTE_OPERACAO")
    first = new_request(client, requester, material, "4")
    second = new_request(client, requester, material, "5")
    before = snapshot_state(db)

    clerk = login(client, "ALMOXARIFADO")
    response = reserve(client, clerk, first, "4")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["reservation"]["status"] == "ATIVA"
    assert result["reservation"]["quantity"] == "4.000000"
    assert result["reservation"]["dataset_id"] == str(dataset.id)
    assert result["request"]["version"] == first["version"] + 1
    assert result["fulfillment"] == {
        "requested": "4",
        "reserved": "4",
        "delivered": "0",
        "forwarded": "0",
        "pending": "0",
    }
    assert result["availability"]["available"] == "2"
    assert "unit_price" not in str(result) and "total_value" not in str(result)
    contract({"$ref": "#/components/schemas/StockReservationResult"}).validate(result)

    view = availability(client, material)
    contract({"$ref": "#/components/schemas/StockAvailability"}).validate(view)
    listing = client.get(f"{REQUESTS}/{first['id']}/reservations").json()
    contract({"$ref": "#/components/schemas/StockReservationList"}).validate(listing)
    assert view == {
        **view,
        "imported": "6",
        "reserved": "4",
        "delivered": "0",
        "available": "2",
        "reservable": True,
        "blocked_reason": None,
    }
    refused = reserve(client, clerk, second, "3")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert reserve(client, clerk, second, "2").status_code == 201
    assert availability(client, material)["available"] == "0"
    assert availability(client, material)["reservable"] is False
    assert snapshot_state(db) == before


def test_quantity_never_exceeds_the_request_pending(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "100")
    request = new_request(client, login(client, "SOLICITANTE_OPERACAO"), material, "3")
    clerk = login(client, "ALMOXARIFADO")
    refused = reserve(client, clerk, request, "4")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "QUANTITY_EXCEEDS_PENDING"
    assert reserve(client, clerk, request, "2").status_code == 201
    listing = client.get(f"{REQUESTS}/{request['id']}/reservations").json()
    assert listing["fulfillment"]["pending"] == "1"
    refused = reserve(client, clerk, request, "1.5", version=request["version"] + 1)
    assert refused.json()["error"]["code"] == "QUANTITY_EXCEEDS_PENDING"


def test_availability_query_creates_no_records(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "6")
    login(client, "ALMOXARIFADO")
    before = counts(db)
    snapshots = snapshot_state(db)
    for _ in range(3):
        availability(client, material)
    assert counts(db) == before
    assert snapshot_state(db) == snapshots


def test_reservation_outside_authorized_centers_is_refused(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "6")
    requester = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, requester, material, "2")
    assert reserve(client, requester, request, "1").status_code == 403
    clerk = login(client, "ALMOXARIFADO")
    identity = Identity(
        uuid.UUID(clerk["user"]["id"]),
        TENANT_ID,
        ("ROLE_ALMOXARIFADO",),
        permissions_for(("ROLE_ALMOXARIFADO",)),
        frozenset({"1100"}),
        authentication_method="bearer",
    )
    client.app.state.request_identity_provider = lambda request, session: identity
    before = counts(db)
    response = client.post(
        f"{REQUESTS}/{request['id']}/reservations",
        json={"expected_version": request["version"], "quantity": "1"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 404
    other_center = client.get(AVAILABILITY, params={"material_id": str(material.id), "center_code": "1200"})
    assert other_center.status_code == 403
    assert client.get(f"{REQUESTS}/{request['id']}/reservations").status_code == 404
    assert counts(db) == before


def test_reservation_is_idempotent_versioned_and_audited(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "6")
    request = new_request(client, login(client, "SOLICITANTE_OPERACAO"), material, "5")
    clerk = login(client, "ALMOXARIFADO")
    key = str(uuid.uuid4())
    first = reserve(client, clerk, request, "2", key=key)
    assert first.status_code == 201
    assert reserve(client, clerk, request, "2", key=key).json() == first.json()
    changed = reserve(client, clerk, request, "3", key=key)
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    stale = reserve(client, clerk, request, "1")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert db.scalar(select(func.count()).select_from(StockReservation)) == 1
    events = list(db.scalars(select(AuditLog).where(AuditLog.action == "STOCK_RESERVED")))
    assert len(events) == 1
    event = events[0]
    assert event.entity_id == first.json()["reservation"]["id"]
    assert event.effective_role == "ROLE_ALMOXARIFADO"
    assert event.actor_user_id == uuid.UUID(clerk["user"]["id"])
    assert event.after_json["available_before"] == "6" and event.after_json["available_after"] == "4"
    assert event.after_json["request_version_after"] == request["version"] + 1


def test_reservation_requires_csrf_and_origin(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "6")
    request = new_request(client, login(client, "SOLICITANTE_OPERACAO"), material, "5")
    clerk = login(client, "ALMOXARIFADO")
    url = f"{REQUESTS}/{request['id']}/reservations"
    body = {"expected_version": request["version"], "quantity": "1"}
    assert (
        client.post(url, json=body, headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())}).status_code == 403
    )
    hostile = {**headers(clerk), "Origin": "https://hostil.example"}
    assert client.post(url, json=body, headers=hostile).status_code == 403
    assert db.scalar(select(func.count()).select_from(StockReservation)) == 0


def test_cancelling_the_request_releases_active_reservations(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "6")
    requester = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, requester, material, "5")
    clerk = login(client, "ALMOXARIFADO")
    reserved = reserve(client, clerk, request, "5").json()
    assert availability(client, material)["available"] == "1"
    requester = login(client, "SOLICITANTE_OPERACAO")
    response = client.post(
        f"{REQUESTS}/{request['id']}/cancel",
        json={"expected_version": reserved["request"]["version"], "reason": "Não preciso mais."},
        headers=headers(requester),
    )
    assert response.status_code == 200, response.text
    reservation = db.get(StockReservation, uuid.UUID(reserved["reservation"]["id"]))
    db.refresh(reservation)
    assert reservation.status == "CANCELADA"
    assert availability(client, material)["available"] == "6"
    assert db.scalar(select(func.count()).where(AuditLog.action == "STOCK_RESERVATION_CANCELLED")) == 1


def test_consolidations_and_deliveries_of_the_current_dataset_count(case):
    client, db = case
    old = add_dataset(db, imported_at=BASE_DATE)
    material = add_material(db)
    member = add_material(db, status="BLOQUEADO")
    add_stock(db, old, material, "50")
    request = new_request(client, login(client, "SOLICITANTE_OPERACAO"), material, "10")
    clerk = login(client, "ALMOXARIFADO")
    old_reservation = reserve(client, clerk, request, "1").json()["reservation"]
    current = add_dataset(db, imported_at=NEWER_DATE)
    add_stock(db, current, material, "6")
    add_stock(db, current, material, "3", unit="CX")
    merged = add_stock(db, current, member, "2")
    proposal = SanitizationProposal(
        tenant_id=TENANT_ID, proposal_type="MERGE", changeset_hash="teste", status="APPLIED"
    )
    db.add(proposal)
    db.flush()
    db.add(
        InventoryConsolidation(
            source_snapshot_id=merged.id,
            tenant_id=TENANT_ID,
            primary_material_id=material.id,
            proposal_id=proposal.id,
            factor=Decimal("1"),
            unit="PC",
            conversion_source="TESTE",
        )
    )
    user = uuid.UUID(clerk["user"]["id"])
    reservation_id = uuid.UUID(old_reservation["id"])
    # A #240 grava os movimentos; aqui eles são inseridos direto para validar a fórmula.
    db.add_all(
        [
            StockMovement(
                tenant_id=TENANT_ID,
                reservation_id=reservation_id,
                movement_type="ENTREGA",
                quantity=Decimal("4"),
                dataset_id=old.id,
                created_by_user_id=user,
            ),
            StockMovement(
                id=(delivery := uuid.uuid4()),
                tenant_id=TENANT_ID,
                reservation_id=reservation_id,
                movement_type="ENTREGA",
                quantity=Decimal("3"),
                dataset_id=current.id,
                created_by_user_id=user,
            ),
        ]
    )
    db.flush()
    db.add(
        StockMovement(
            tenant_id=TENANT_ID,
            reservation_id=reservation_id,
            movement_type="REVERSAO",
            quantity=Decimal("1"),
            reverses_movement_id=delivery,
            dataset_id=current.id,
            created_by_user_id=user,
        )
    )
    db.commit()
    view = availability(client, material)
    # S = 6 + 2 consolidado; R = 1 ativa do dataset anterior; E = 3 - 1 só do dataset vigente.
    assert view["dataset_id"] == str(current.id)
    assert (view["imported"], view["reserved"], view["delivered"], view["available"]) == ("8", "1", "2", "5")
    assert view["unconverted_units"] == ["CX"]
    # A reserva do dataset anterior continua contando e bloqueia novas até a reconciliação (D4).
    assert view["reservable"] is False and view["blocked_reason"] == "RECONCILIATION_REQUIRED"
    refused = reserve(client, clerk, request, "1", version=request["version"] + 1)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "RECONCILIATION_REQUIRED"


def test_inactive_material_is_not_reserved(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "6")
    request = new_request(client, login(client, "SOLICITANTE_OPERACAO"), material, "2")
    material.status = "OBSOLETO"
    db.commit()
    clerk = login(client, "ALMOXARIFADO")
    refused = reserve(client, clerk, request, "1")
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "INACTIVE_MATERIAL"
    assert availability(client, material)["blocked_reason"] == "INACTIVE_MATERIAL"


def test_database_privileges_keep_snapshots_and_movements_immutable(case, connection):
    from test_db_schema import denied

    denied(connection, "api_user", "UPDATE material_inventory_snapshots SET quantity = 0")
    denied(connection, "api_user", "UPDATE stock_movements SET quantity = 1")
    denied(connection, "api_user", "DELETE FROM stock_movements")
    denied(connection, "api_user", "DELETE FROM stock_reservations")
    for role in ("batch_user", "mcp_reader"):
        denied(connection, role, "SELECT * FROM stock_reservations")
        denied(connection, role, "SELECT * FROM stock_movements")


def test_concurrent_reservations_never_oversubscribe(migrated_url, monkeypatch):
    engine = create_engine(migrated_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    tenant, requester, clerk = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    roles = ("ROLE_ALMOXARIFADO",)
    identity = Identity(
        clerk, tenant, roles, permissions_for(roles), frozenset({"1200"}), authentication_method="bearer"
    )
    with factory.begin() as db:
        for user in (requester, clerk):
            db.add(UserSso(id=user, tenant_id=tenant, issuer="test-stock", subject=str(user)))
        dataset = Dataset(id=uuid.uuid4(), tenant_id=tenant)
        material = MaterialMaster(
            id=uuid.uuid4(), tenant_id=tenant, source_system="TEST", material_code="M1", status="ATIVO", unit="PC"
        )
        db.add_all([dataset, material])
        db.flush()
        db.add(
            MaterialInventorySnapshot(
                tenant_id=tenant,
                dataset_id=dataset.id,
                material_id=material.id,
                center_code="1200",
                quantity=Decimal("6"),
                unit="PC",
                source_line=1,
            )
        )
        requests = [
            MaterialRequest(
                id=uuid.uuid4(),
                tenant_id=tenant,
                requester_user_id=requester,
                original_text="Concorrente",
                material_id=material.id,
                quantity=Decimal("6"),
                unit="PC",
                center_code="1200",
                status="EM_ATENDIMENTO",
            )
            for _ in range(2)
        ]
        db.add_all(requests)

    # Atraso dentro da seção crítica: sem o bloqueio, as duas leriam D = 6 e reservariam 8.
    original = stock_service.compute_availability
    barrier = threading.Barrier(2)

    def slow(*args, **kwargs):
        state = original(*args, **kwargs)
        time.sleep(0.5)
        return state

    monkeypatch.setattr(stock_service, "compute_availability", slow)

    def run(row):
        barrier.wait(timeout=10)
        with factory() as db:
            try:
                payload = CreateStockReservation(expected_version=1, quantity="4")
                return stock_service.reserve(db, identity, row.id, payload, uuid.uuid4(), "concurrent")
            except ApiProblem as error:
                db.rollback()
                return error

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, requests))
        accepted = [result for result in results if isinstance(result, dict)]
        refused = [result for result in results if isinstance(result, ApiProblem)]
        assert len(accepted) == 1 and len(refused) == 1
        assert refused[0].status == 409 and refused[0].code == "INSUFFICIENT_STOCK"
        with factory() as db:
            total = db.scalar(
                select(func.sum(StockReservation.quantity)).where(
                    StockReservation.tenant_id == tenant, StockReservation.status == "ATIVA"
                )
            )
            assert total == Decimal("4")
            state = original(db, tenant, db.get(MaterialMaster, material.id), "1200")
            # Conservação: S = D + R + E, e o snapshot segue com a quantidade importada.
            assert state["imported"] == state["available"] + state["reserved"] + state["delivered"] == Decimal("6")
            assert db.scalar(
                select(MaterialInventorySnapshot.quantity).where(MaterialInventorySnapshot.tenant_id == tenant)
            ) == Decimal("6")
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.tenant_id == tenant, AuditLog.action == "STOCK_RESERVED")
                )
                == 1
            )
        with factory() as db:
            revoked = replace(identity, center_codes=frozenset({"1100"}))
            with pytest.raises(ApiProblem) as error:
                stock_service.reserve(
                    db,
                    revoked,
                    requests[1].id,
                    CreateStockReservation(expected_version=1, quantity="1"),
                    uuid.uuid4(),
                    "x",
                )
            assert error.value.status == 404
    finally:
        with factory.begin() as db:
            db.execute(OperationRequest.__table__.delete().where(OperationRequest.user_id == clerk))
            for table in (AuditLog, StockMovement, StockReservation, MaterialRequest, MaterialInventorySnapshot):
                db.execute(table.__table__.delete().where(table.tenant_id == tenant))
            db.execute(MaterialMaster.__table__.delete().where(MaterialMaster.tenant_id == tenant))
            db.execute(Dataset.__table__.delete().where(Dataset.tenant_id == tenant))
            db.execute(UserSso.__table__.delete().where(UserSso.tenant_id == tenant))
        engine.dispose()
