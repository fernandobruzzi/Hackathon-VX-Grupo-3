"""Atendimento parcial entre estoque e compras (caminho 3, D1, #242), com PostgreSQL real."""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
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
    MaterialInventorySnapshot,
    MaterialMaster,
    MaterialRequest,
    OperationRequest,
    PurchaseForward,
    StockMovement,
    StockReservation,
    UserSso,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.main import create_app
from vx_materials_api.schemas.material_requests import ConfirmFulfillment
from vx_materials_api.schemas.stock import CreateStockReservation
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services import partial_fulfillment_service, stock_service

ORIGIN = "http://localhost:8000"
REQUESTS = "/api/v1/material-requests"
# Data distante: o dataset do teste é sempre o vigente do tenant, mesmo com o kit carregado.
DATASET_DATE = datetime(2099, 3, 1, tzinfo=UTC)


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
            dataset = Dataset(id=uuid.uuid4(), tenant_id=TENANT_ID, imported_at=DATASET_DATE)
            db.add(dataset)
            db.commit()
            yield client, db, dataset


def add_material(db, dataset, stock):
    material = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        source_system="TEST",
        material_code=f"T{uuid.uuid4().hex[:10]}",
        status="ATIVO",
        unit="PC",
        pdm_description="CANETA ESFEROGRAFICA AZUL",
    )
    db.add(material)
    db.flush()
    db.add(
        MaterialInventorySnapshot(
            tenant_id=TENANT_ID,
            dataset_id=dataset.id,
            material_id=material.id,
            center_code="1200",
            quantity=Decimal(stock),
            unit="PC",
            source_line=db.scalar(select(func.coalesce(func.max(MaterialInventorySnapshot.source_line), 0))) + 1,
        )
    )
    db.commit()
    return material


def new_request(client, me, material, quantity="10"):
    body = {
        "original_text": "Preciso de canetas.",
        "quantity": quantity,
        "unit": "PC",
        "center_code": "1200",
        "material_id": str(material.id),
        # Várias solicitações do mesmo material e centro são intencionais aqui (#248).
        "acknowledge_open_requests": True,
    }
    response = client.post(REQUESTS, json=body, headers=headers(me))
    assert response.status_code == 201, response.text
    return response.json()


def options(client, request):
    response = client.get(f"{REQUESTS}/{request['id']}/fulfillment-options")
    assert response.status_code == 200, response.text
    contract({"$ref": "#/components/schemas/FulfillmentPreview"}).validate(response.json())
    return response.json()


def confirm(client, me, request, option="PARTIAL", *, version=None, key=None, extra_headers=None):
    return client.post(
        f"{REQUESTS}/{request['id']}/fulfillment",
        json={"expected_version": version or request["version"], "option": option},
        headers={**headers(me, key), **(extra_headers or {})},
    )


def availability(client, material):
    response = client.get("/api/v1/stock/availability", params={"material_id": str(material.id), "center_code": "1200"})
    assert response.status_code == 200, response.text
    return response.json()


def written(db):
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in (StockReservation, PurchaseForward, StockMovement, AuditLog, OperationRequest)
    }


def assert_invariant(detail):
    """`r + e + c ≤ Q`, `p ≥ 0` e nenhuma unidade contada em duas parcelas (seção 4.2)."""
    requested = Decimal(detail["quantity"])
    parcels = [Decimal(detail[key]) for key in ("reserved_quantity", "delivered_quantity", "forwarded_quantity")]
    pending = Decimal(detail["pending_quantity"])
    assert sum(parcels) <= requested and pending >= 0
    assert sum(parcels) + pending == requested


def test_ten_requested_with_six_available_reserve_six_and_forward_four(case):
    client, db, dataset = case
    material = add_material(db, dataset, "6")
    owner = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, owner, material)
    before = written(db)

    preview = options(client, request)
    assert preview["default_option"] == "PARTIAL" and preview["blocked_reason"] is None
    assert preview["available"] == "6.000000" and preview["pending"] == "10.000000"
    assert [(item["option"], item["reserve_quantity"], item["forward_quantity"]) for item in preview["options"]] == [
        ("PARTIAL", "6.000000", "4.000000"),
        ("PURCHASING_ONLY", "0.000000", "10.000000"),
    ]
    # Consultar a divisão e selecionar o padrão não executa nada.
    assert written(db) == before

    key = str(uuid.uuid4())
    response = confirm(client, owner, request, key=key)
    assert response.status_code == 201, response.text
    result = response.json()
    contract({"$ref": "#/components/schemas/FulfillmentResult"}).validate(result)
    assert result["reserved_quantity"] == "6.000000" and result["forwarded_quantity"] == "4.000000"
    detail = result["request"]
    assert detail["version"] == 2 and detail["status"] == "EM_ATENDIMENTO"
    assert detail["reserved_quantity"] == "6.000000" and detail["forwarded_quantity"] == "4.000000"
    assert detail["pending_quantity"] == "0.000000"
    assert_invariant(detail)
    # As duas parcelas, com seus estados, na mesma solicitação.
    [reservation] = detail["reservations"]
    [forward] = detail["purchase_forwards"]
    assert reservation["id"] == result["reservation_id"] and reservation["status"] == "ATIVA"
    assert reservation["quantity"] == "6.000000" and reservation["open_quantity"] == "6.000000"
    assert forward["id"] == result["purchase_forward_id"] and forward["status"] == "ENCAMINHADO"
    assert forward["quantity"] == "4.000000"
    assert detail["history"][-1]["action"] == "MATERIAL_REQUEST_PARTIAL_FULFILLMENT"
    assert client.get(f"{REQUESTS}/{request['id']}").json() == detail
    assert availability(client, material)["available"] == "0"

    events = {
        event.action: event
        for event in db.scalars(
            select(AuditLog).where(
                AuditLog.entity_id.in_([request["id"], result["reservation_id"], result["purchase_forward_id"]])
            )
        )
    }
    reserved_event = events["STOCK_RESERVED"]
    assert reserved_event.effective_role == "ROLE_SOLICITANTE"
    assert reserved_event.after_json["origin"] == "REQUESTER_PARTIAL_CONFIRMATION"
    assert reserved_event.after_json["available_before"] == "6" and reserved_event.after_json["available_after"] == "0"
    assert events["PURCHASE_FORWARD_CREATED"].effective_role == "ROLE_SOLICITANTE"
    split = events["MATERIAL_REQUEST_PARTIAL_FULFILLMENT"].after_json["fulfillment_split"]
    assert split["reserved_quantity"] == "6.000000" and split["forwarded_quantity"] == "4.000000"
    assert split["available_at_confirmation"] == "6.000000" and split["option"] == "PARTIAL"

    # Replay devolve a mesma resposta sem gravar de novo; outra chave esbarra na versão.
    after = written(db)
    assert confirm(client, owner, request, key=key).json() == result
    assert written(db) == after
    again = confirm(client, owner, request)
    assert again.status_code == 409 and again.json()["error"]["code"] == "VERSION_CONFLICT"
    nothing = confirm(client, owner, request, version=2)
    assert nothing.status_code == 409 and nothing.json()["error"]["code"] == "NOTHING_PENDING"
    assert options(client, {"id": request["id"]})["blocked_reason"] == "NOTHING_PENDING"
    changed = confirm(client, owner, request, "PURCHASING_ONLY", key=key)
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert written(db) == after

    # Almoxarifado entrega a parcela de estoque; Compras aceita a sua; a solicitação encerra.
    clerk = login(client, "ALMOXARIFADO")
    delivered = client.post(
        f"/api/v1/stock/reservations/{reservation['id']}/deliveries",
        json={"expected_version": 2, "quantity": "6"},
        headers=headers(clerk),
    )
    assert delivered.status_code == 201, delivered.text
    buyer = login(client, "COMPRAS")
    accepted = client.post(
        f"/api/v1/purchase-forwards/{forward['id']}/accept", json={"expected_version": 1}, headers=headers(buyer)
    )
    assert accepted.status_code == 200, accepted.text
    login(client, "SOLICITANTE_OPERACAO")
    final = client.get(f"{REQUESTS}/{request['id']}").json()
    assert final["status"] == "ENCERRADA" and final["closure_reason"] == "ATENDIDA_PARCIAL_COMPRAS"
    assert final["delivered_quantity"] == "6.000000" and final["forwarded_quantity"] == "4.000000"
    assert [item["status"] for item in final["reservations"]] == ["CONSUMIDA"]
    assert [item["status"] for item in final["purchase_forwards"]] == ["ACEITO"]
    assert_invariant(final)


def test_split_is_recalculated_when_availability_changes_before_confirmation(case):
    client, db, dataset = case
    material = add_material(db, dataset, "6")
    owner = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, owner, material)
    other = new_request(client, owner, material, quantity="2")
    assert options(client, request)["options"][0]["reserve_quantity"] == "6.000000"

    # Outra reserva chega entre a consulta e a confirmação.
    clerk = login(client, "ALMOXARIFADO")
    taken = client.post(
        f"{REQUESTS}/{other['id']}/reservations",
        json={"expected_version": other["version"], "quantity": "2"},
        headers=headers(clerk),
    )
    assert taken.status_code == 201, taken.text

    owner = login(client, "SOLICITANTE_OPERACAO")
    response = confirm(client, owner, request)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["available_at_confirmation"] == "4.000000"
    assert result["reserved_quantity"] == "4.000000" and result["forwarded_quantity"] == "6.000000"
    assert_invariant(result["request"])
    # Nunca mais que o disponível: o centro inteiro reservou exatamente o saldo importado.
    total = db.scalar(
        select(func.sum(StockReservation.quantity)).where(
            StockReservation.material_id == material.id, StockReservation.status == "ATIVA"
        )
    )
    assert total == Decimal("6")
    assert availability(client, material)["available"] == "0"


def test_partial_without_any_stock_left_forwards_everything(case):
    client, db, dataset = case
    material = add_material(db, dataset, "3")
    owner = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, owner, material)
    other = new_request(client, owner, material, quantity="3")
    clerk = login(client, "ALMOXARIFADO")
    taken = client.post(
        f"{REQUESTS}/{other['id']}/reservations",
        json={"expected_version": other["version"], "quantity": "3"},
        headers=headers(clerk),
    )
    assert taken.status_code == 201, taken.text
    owner = login(client, "SOLICITANTE_OPERACAO")
    preview = options(client, request)
    assert preview["default_option"] == "PURCHASING_ONLY" and len(preview["options"]) == 1
    response = confirm(client, owner, request, "PARTIAL")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["reservation_id"] is None and result["reserved_quantity"] == "0.000000"
    assert result["forwarded_quantity"] == "10.000000"
    assert result["request"]["reservations"] == []
    assert result["request"]["history"][-1]["action"] == "MATERIAL_REQUEST_FORWARDED_TO_PURCHASING"
    assert "nada foi reservado" in result["request"]["history"][-1]["reason"]


def test_purchasing_only_forwards_all_pending_without_reservation(case):
    client, db, dataset = case
    material = add_material(db, dataset, "6")
    owner = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, owner, material)
    response = confirm(client, owner, request, "PURCHASING_ONLY")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["reserved_quantity"] == "0.000000" and result["forwarded_quantity"] == "10.000000"
    assert result["request"]["reservations"] == []
    assert availability(client, material)["available"] == "6"
    assert_invariant(result["request"])


def test_enough_stock_or_unknown_stock_is_not_split(case):
    client, db, dataset = case
    owner = login(client, "SOLICITANTE_OPERACAO")
    enough = add_material(db, dataset, "10")
    request = new_request(client, owner, enough)
    preview = options(client, request)
    assert preview["blocked_reason"] == "STOCK_AVAILABLE" and preview["options"] == []
    before = written(db)
    for option in ("PARTIAL", "PURCHASING_ONLY"):
        refused = confirm(client, owner, request, option)
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "STOCK_AVAILABLE"
    assert written(db) == before

    unidentified = client.post(
        REQUESTS,
        json={"original_text": "Algo parecido.", "quantity": "2", "unit": "PC", "center_code": "1200"},
        headers=headers(owner),
    ).json()
    assert options(client, unidentified)["blocked_reason"] == "REQUEST_NOT_IN_SERVICE"
    refused = confirm(client, owner, unidentified)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "REQUEST_NOT_IN_SERVICE"


def test_split_is_only_confirmed_by_the_owner_with_csrf(case):
    client, db, dataset = case
    material = add_material(db, dataset, "6")
    owner = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, owner, material)
    before = written(db)
    missing = confirm(client, owner, request, extra_headers={"X-CSRF-Token": "wrong"})
    assert missing.status_code == 403
    # O solicitante continua sem reservar quantidades livres.
    free = client.post(
        f"{REQUESTS}/{request['id']}/reservations",
        json={"expected_version": request["version"], "quantity": "1"},
        headers=headers(owner),
    )
    assert free.status_code == 403
    for persona in ("ALMOXARIFADO", "COMPRAS", "GESTOR_CADASTRO"):
        other = login(client, persona)
        refused = confirm(client, other, request)
        assert refused.status_code == 404, (persona, refused.text)
        assert client.get(f"{REQUESTS}/{request['id']}/fulfillment-options").status_code == 404
    assert written(db) == before


def test_concurrent_reservation_and_split_never_oversubscribe(migrated_url, monkeypatch):
    engine = create_engine(migrated_url)
    factory = sessionmaker(engine, expire_on_commit=False)
    tenant, requester, clerk = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    owner = Identity(
        requester,
        tenant,
        ("ROLE_SOLICITANTE",),
        permissions_for(("ROLE_SOLICITANTE",)),
        frozenset({"1200"}),
        authentication_method="bearer",
    )
    keeper = Identity(
        clerk,
        tenant,
        ("ROLE_ALMOXARIFADO",),
        permissions_for(("ROLE_ALMOXARIFADO",)),
        frozenset({"1200"}),
        authentication_method="bearer",
    )
    with factory.begin() as db:
        for user in (requester, clerk):
            db.add(UserSso(id=user, tenant_id=tenant, issuer="test-split", subject=str(user)))
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
        split_request, reserve_request = (
            MaterialRequest(
                id=uuid.uuid4(),
                tenant_id=tenant,
                requester_user_id=requester,
                original_text="Concorrente",
                material_id=material.id,
                quantity=Decimal(quantity),
                unit="PC",
                center_code="1200",
                status="EM_ATENDIMENTO",
            )
            for quantity in ("10", "4")
        )
        db.add_all([split_request, reserve_request])

    # Atraso dentro da seção crítica: sem o bloqueio, as duas leriam D = 6.
    original = stock_service.compute_availability
    barrier = threading.Barrier(2)

    def slow(*args, **kwargs):
        state = original(*args, **kwargs)
        time.sleep(0.5)
        return state

    monkeypatch.setattr(stock_service, "compute_availability", slow)
    monkeypatch.setattr(partial_fulfillment_service, "compute_availability", slow)
    from vx_materials_api.services import purchase_forward_service

    monkeypatch.setattr(purchase_forward_service, "compute_availability", slow)

    def run(job):
        barrier.wait(timeout=10)
        with factory() as db:
            try:
                if job == "split":
                    payload = ConfirmFulfillment(expected_version=1, option="PARTIAL")
                    return job, partial_fulfillment_service.confirm(
                        db, owner, split_request.id, payload, uuid.uuid4(), "split"
                    )
                payload = CreateStockReservation(expected_version=1, quantity="4")
                return job, stock_service.reserve(db, keeper, reserve_request.id, payload, uuid.uuid4(), "reserve")
            except ApiProblem as error:
                db.rollback()
                return job, error

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = dict(pool.map(run, ["split", "reserve"]))
        split = results["split"]
        assert isinstance(split, dict), split
        if isinstance(results["reserve"], ApiProblem):
            # A divisão venceu: reservou 6, encaminhou 4, e a reserva avulsa não coube.
            assert results["reserve"].code == "INSUFFICIENT_STOCK"
            assert (split["reserved_quantity"], split["forwarded_quantity"]) == ("6.000000", "4.000000")
        else:
            # A reserva avulsa venceu: a divisão foi recalculada com D = 2.
            assert (split["reserved_quantity"], split["forwarded_quantity"]) == ("2.000000", "8.000000")
        assert_invariant(split["request"])
        with factory() as db:
            total = db.scalar(
                select(func.sum(StockReservation.quantity)).where(
                    StockReservation.tenant_id == tenant, StockReservation.status == "ATIVA"
                )
            )
            assert total == Decimal("6")
            state = original(db, tenant, db.get(MaterialMaster, material.id), "1200")
            assert state["available"] == 0
            assert state["imported"] == state["available"] + state["reserved"] + state["delivered"]
            forwarded = db.scalar(
                select(func.sum(PurchaseForward.quantity)).where(
                    PurchaseForward.material_request_id == split_request.id
                )
            )
            assert Decimal(split["reserved_quantity"]) + forwarded == Decimal("10")
    finally:
        with factory.begin() as db:
            db.execute(OperationRequest.__table__.delete().where(OperationRequest.user_id.in_([requester, clerk])))
            for table in (
                AuditLog,
                StockMovement,
                PurchaseForward,
                StockReservation,
                MaterialRequest,
                MaterialInventorySnapshot,
            ):
                db.execute(table.__table__.delete().where(table.tenant_id == tenant))
            db.execute(MaterialMaster.__table__.delete().where(MaterialMaster.tenant_id == tenant))
            db.execute(Dataset.__table__.delete().where(Dataset.tenant_id == tenant))
            db.execute(UserSso.__table__.delete().where(UserSso.tenant_id == tenant))
        engine.dispose()
