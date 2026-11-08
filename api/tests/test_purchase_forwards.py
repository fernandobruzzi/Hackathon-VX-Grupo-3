"""Encaminhamento para compras do material cadastrado sem saldo, com PostgreSQL real."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import (
    AuditLog,
    Dataset,
    MaterialInventorySnapshot,
    MaterialMaster,
    PurchaseForward,
    RegistrationOrder,
)
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for

ORIGIN = "http://localhost:8000"
REQUESTS = "/api/v1/material-requests"
QUEUE = "/api/v1/purchase-forwards"


def login(client, persona="SOLICITANTE_OPERACAO"):
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
        me = login(client)
        with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
            # Dataset mais recente do tenant só neste teste; o rollback final o descarta.
            dataset = Dataset(id=uuid.uuid4(), tenant_id=TENANT_ID, imported_at=datetime(2100, 1, 1, tzinfo=UTC))
            db.add(dataset)
            db.commit()
            yield client, db, me, dataset


def add_material(db, **values):
    row = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        source_system="TEST",
        material_code=f"T{uuid.uuid4().hex[:10]}",
        status="ATIVO",
        unit="PC",
        pdm_description="CANETA ESFEROGRAFICA AZUL",
    )
    for key, value in values.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    return row


def add_stock(db, dataset, material, quantity, *, center="1200", unit="PC"):
    db.add(
        MaterialInventorySnapshot(
            tenant_id=TENANT_ID,
            dataset_id=dataset.id,
            material_id=material.id,
            center_code=center,
            quantity=Decimal(quantity),
            unit=unit,
            source_line=db.scalar(select(func.coalesce(func.max(MaterialInventorySnapshot.source_line), 0))) + 1,
        )
    )
    db.commit()


def new_request(client, me, material, quantity="10"):
    body = {
        "original_text": "Preciso de canetas.",
        "quantity": quantity,
        "unit": "PC",
        "center_code": "1200",
        "material_id": str(material.id),
    }
    response = client.post(REQUESTS, json=body, headers=headers(me))
    assert response.status_code == 201, response.text
    return response.json()


def forward(client, me, request, *, version=None, key=None):
    return client.post(
        f"{REQUESTS}/{request['id']}/purchase-forwards",
        json={"expected_version": version or request["version"]},
        headers=headers(me, key),
    )


def counts(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_request_without_stock_forwards_existing_code_once(case):
    client, db, me, dataset = case
    material = add_material(db)
    add_stock(db, dataset, material, "0")
    add_stock(db, dataset, material, "50", center="1100")  # outro centro não atende este
    snapshots = [(row.id, row.quantity) for row in db.scalars(select(MaterialInventorySnapshot))]
    orders = counts(db, RegistrationOrder)
    request = new_request(client, me, material)
    key = str(uuid.uuid4())
    response = forward(client, me, request, key=key)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["version"] == 2 and result["status"] == "EM_ATENDIMENTO"
    assert result["forwarded_quantity"] == "10.000000" and result["pending_quantity"] == "0.000000"
    [item] = result["purchase_forwards"]
    assert item["status"] == "ENCAMINHADO" and item["material_code"] == material.material_code
    assert item["quantity"] == "10.000000" and item["unit"] == "PC" and item["center_code"] == "1200"
    assert item["forwarded_by_user_id"] == me["user"]["id"] and item["can_handle"] is False
    assert result["history"][-1]["action"] == "MATERIAL_REQUEST_FORWARDED_TO_PURCHASING"
    # Repetir a mesma parcela não duplica: replay devolve a resposta, outra chave esbarra na versão.
    assert forward(client, me, request, key=key).json() == result
    again = forward(client, me, request)
    assert again.status_code == 409 and again.json()["error"]["code"] == "VERSION_CONFLICT"
    nothing = forward(client, me, request, version=2)
    assert nothing.status_code == 409 and nothing.json()["error"]["code"] == "NOTHING_PENDING"
    assert counts(db, PurchaseForward) == 1
    assert counts(db, RegistrationOrder) == orders
    assert [(row.id, row.quantity) for row in db.scalars(select(MaterialInventorySnapshot))] == snapshots
    assert client.get(f"{REQUESTS}/{request['id']}").json() == result
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_type == "purchase_forward", AuditLog.entity_id == item["id"])
        )
        == 1
    )


def test_partial_stock_forwards_whole_quantity_but_sufficient_stock_is_refused(case):
    client, db, me, dataset = case
    short = add_material(db)
    add_stock(db, dataset, short, "6")
    response = forward(client, me, new_request(client, me, short))
    assert response.status_code == 201
    assert response.json()["purchase_forwards"][0]["quantity"] == "10.000000"
    enough = add_material(db)
    add_stock(db, dataset, enough, "4")
    add_stock(db, dataset, enough, "6")
    refused = forward(client, me, new_request(client, me, enough))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "STOCK_AVAILABLE"
    other_unit = add_material(db)
    add_stock(db, dataset, other_unit, "1", unit="CX")
    refused = forward(client, me, new_request(client, me, other_unit))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "STOCK_UNIT_UNRESOLVED"
    assert counts(db, PurchaseForward) == 1


def test_unknown_stock_unidentified_and_inactive_materials_are_not_forwarded(case, monkeypatch):
    client, db, me, _ = case
    from vx_materials_api.services import purchase_forward_service

    material = add_material(db)
    request = new_request(client, me, material)
    real = purchase_forward_service.compute_availability
    monkeypatch.setattr(
        purchase_forward_service,
        "compute_availability",
        lambda *args: {**real(*args), "blocked_reason": "NO_INVENTORY_DATASET"},
    )
    unknown = forward(client, me, request)
    assert unknown.status_code == 409 and unknown.json()["error"]["code"] == "NO_INVENTORY_DATASET"
    monkeypatch.undo()
    material.status = "OBSOLETO"
    db.commit()
    inactive = forward(client, me, request)
    assert inactive.status_code == 422 and inactive.json()["error"]["code"] == "INACTIVE_MATERIAL"
    body = {"original_text": "Algo que não sei o código.", "quantity": "1", "unit": "PC", "center_code": "1200"}
    pending = client.post(REQUESTS, json=body, headers=headers(me)).json()
    unidentified = forward(client, me, pending)
    assert unidentified.status_code == 409 and unidentified.json()["error"]["code"] == "REQUEST_NOT_IN_SERVICE"
    assert counts(db, PurchaseForward) == 0


def test_only_owner_forwards_with_csrf(case):
    client, db, me, _ = case
    request = new_request(client, me, add_material(db))
    url = f"{REQUESTS}/{request['id']}/purchase-forwards"
    no_csrf = client.post(
        url, json={"expected_version": 1}, headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())}
    )
    assert no_csrf.status_code == 403
    for persona in ("GESTOR_CADASTRO", "COMPRAS", "ALMOXARIFADO"):
        other = login(client, persona)
        assert forward(client, other, request).status_code == 404
    assert counts(db, PurchaseForward) == 0


def test_purchasing_queue_is_only_for_compras_in_authorized_centers(case):
    client, db, me, _ = case
    request = new_request(client, me, add_material(db))
    item = forward(client, me, request).json()["purchase_forwards"][0]
    for persona in ("SOLICITANTE_OPERACAO", "GESTOR_CADASTRO", "AUDITOR_FISCAL", "ALMOXARIFADO", "DEV_TI"):
        other = login(client, persona)
        assert client.get(QUEUE).status_code == 403
        assert client.get(f"{QUEUE}/{item['id']}").status_code == 403
        accepted = client.post(f"{QUEUE}/{item['id']}/accept", json={"expected_version": 1}, headers=headers(other))
        assert accepted.status_code == 403
    compras = login(client, "COMPRAS")
    listed = client.get(QUEUE, params={"status": "ENCAMINHADO"}).json()["items"]
    assert [row["id"] for row in listed] == [item["id"]]
    assert listed[0]["can_handle"] is True and listed[0]["request_protocol"] == request["protocol"]
    assert client.get(QUEUE, params={"center_code": "1200"}).json()["items"] == listed
    # Pedido de cadastro ou detalhe da solicitação continuam fora do alcance de Compras.
    assert client.get(f"{REQUESTS}/{request['id']}").status_code == 404
    elsewhere = Identity(
        uuid.UUID(compras["user"]["id"]),
        TENANT_ID,
        ("ROLE_COMPRAS",),
        permissions_for(("ROLE_COMPRAS",)),
        frozenset({"1100"}),
        authentication_method="bearer",
    )
    client.app.state.request_identity_provider = lambda request, session: elsewhere
    assert client.get(QUEUE).json()["items"] == []
    assert client.get(QUEUE, params={"center_code": "1200"}).status_code == 403
    assert client.get(f"{QUEUE}/{item['id']}").status_code == 404
    bearer = {"Idempotency-Key": str(uuid.uuid4())}
    assert client.post(f"{QUEUE}/{item['id']}/accept", json={"expected_version": 1}, headers=bearer).status_code == 404
    client.app.state.request_identity_provider = lambda request, session: replace(elsewhere, tenant_id=uuid.uuid4())
    assert client.get(QUEUE, params={"center_code": "1100"}).json()["items"] == []
    assert db.get(PurchaseForward, uuid.UUID(item["id"])).status == "ENCAMINHADO"


def test_accept_closes_request_as_forwarded_and_is_idempotent(case):
    client, db, me, _ = case
    request = new_request(client, me, add_material(db))
    item = forward(client, me, request).json()["purchase_forwards"][0]
    compras = login(client, "COMPRAS")
    key = str(uuid.uuid4())
    url = f"{QUEUE}/{item['id']}/accept"
    stale = client.post(url, json={"expected_version": 2}, headers=headers(compras))
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    response = client.post(url, json={"expected_version": 1}, headers=headers(compras, key))
    assert response.status_code == 200, response.text
    accepted = response.json()
    assert accepted["status"] == "ACEITO" and accepted["version"] == 2 and accepted["can_handle"] is False
    assert accepted["handled_by_user_id"] == compras["user"]["id"] and accepted["handled_at"]
    assert client.post(url, json={"expected_version": 1}, headers=headers(compras, key)).json() == accepted
    closed = client.post(url, json={"expected_version": 2}, headers=headers(compras))
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "FORWARD_CLOSED"
    me = login(client)
    detail = client.get(f"{REQUESTS}/{request['id']}").json()
    assert detail["status"] == "ENCERRADA" and detail["closure_reason"] == "ENCAMINHADA_COMPRAS"
    assert detail["history"][-1]["action"] == "MATERIAL_REQUEST_CLOSED"
    assert detail["purchase_forwards"][0]["status"] == "ACEITO"
    events = db.scalars(select(AuditLog.action).where(AuditLog.entity_id == item["id"]).order_by(AuditLog.created_at))
    assert list(events) == ["PURCHASE_FORWARD_CREATED", "PURCHASE_FORWARD_ACCEPTED"]


def test_return_gives_quantity_back_and_allows_a_new_parcel(case):
    client, db, me, _ = case
    request = new_request(client, me, add_material(db))
    item = forward(client, me, request).json()["purchase_forwards"][0]
    compras = login(client, "COMPRAS")
    url = f"{QUEUE}/{item['id']}/return"
    assert client.post(url, json={"expected_version": 1, "reason": "  "}, headers=headers(compras)).status_code == 422
    assert client.post(url, json={"expected_version": 1}, headers=headers(compras)).status_code == 422
    returned = client.post(
        url, json={"expected_version": 1, "reason": "Fornecedor descontinuou."}, headers=headers(compras)
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "DEVOLVIDO" and returned.json()["reason"] == "Fornecedor descontinuou."
    me = login(client)
    detail = client.get(f"{REQUESTS}/{request['id']}").json()
    assert detail["status"] == "EM_ATENDIMENTO" and detail["version"] == 3
    assert detail["pending_quantity"] == "10.000000" and detail["forwarded_quantity"] == "0.000000"
    assert detail["history"][-1]["action"] == "MATERIAL_REQUEST_PURCHASE_RETURNED"
    again = forward(client, me, detail)
    assert again.status_code == 201
    assert [row["status"] for row in again.json()["purchase_forwards"]] == ["DEVOLVIDO", "ENCAMINHADO"]


def test_cancel_cancels_open_forward_and_compras_cannot_handle_it(case):
    client, db, me, _ = case
    request = new_request(client, me, add_material(db))
    detail = forward(client, me, request).json()
    item = detail["purchase_forwards"][0]
    cancelled = client.post(
        f"{REQUESTS}/{request['id']}/cancel",
        json={"expected_version": detail["version"], "reason": "Não preciso mais."},
        headers=headers(me),
    ).json()
    assert cancelled["status"] == "ENCERRADA" and cancelled["purchase_forwards"][0]["status"] == "CANCELADO"
    assert cancelled["pending_quantity"] == "10.000000"
    compras = login(client, "COMPRAS")
    response = client.post(f"{QUEUE}/{item['id']}/accept", json={"expected_version": 2}, headers=headers(compras))
    assert response.status_code == 409 and response.json()["error"]["code"] == "FORWARD_CLOSED"


def test_database_privileges_and_parcel_uniqueness(case, connection):
    from test_db_schema import denied

    client, db, me, _ = case
    request = new_request(client, me, add_material(db))
    item = forward(client, me, request).json()["purchase_forwards"][0]
    denied(connection, "batch_user", "SELECT * FROM purchase_forwards")
    denied(connection, "mcp_reader", "SELECT * FROM purchase_forwards")
    duplicate = text(
        "INSERT INTO purchase_forwards (tenant_id, material_request_id, request_version, material_id, quantity, "
        "unit, center_code, status, forwarded_by_user_id) SELECT tenant_id, material_request_id, request_version, "
        "material_id, quantity, unit, center_code, 'ENCAMINHADO', forwarded_by_user_id FROM purchase_forwards "
        "WHERE id = :id"
    )
    with pytest.raises(IntegrityError, match="uq_purchase_forwards_material_request_id_request_version"):
        with connection.begin_nested():
            connection.execute(duplicate, {"id": item["id"]})
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(
                text("UPDATE purchase_forwards SET status = 'DEVOLVIDO' WHERE id = :id"), {"id": item["id"]}
            )


def reserve(client, warehouse, request, quantity):
    return client.post(
        f"{REQUESTS}/{request['id']}/reservations",
        json={"expected_version": request["version"], "quantity": quantity},
        headers=headers(warehouse),
    )


def request_totals(db, request_id):
    """`r`, `e` e `c` gravados no banco, sem passar pela API."""
    return {
        name: Decimal(db.execute(text(sql), {"id": request_id}).scalar_one())
        for name, sql in {
            "r": "SELECT coalesce(sum(quantity), 0) FROM stock_reservations "
            "WHERE request_id = :id AND status = 'ATIVA'",
            "e": "SELECT coalesce(sum(CASE WHEN m.movement_type = 'ENTREGA' THEN m.quantity ELSE -m.quantity END), 0) "
            "FROM stock_movements m JOIN stock_reservations r ON r.id = m.reservation_id WHERE r.request_id = :id",
            "c": "SELECT coalesce(sum(quantity), 0) FROM purchase_forwards "
            "WHERE material_request_id = :id AND status IN ('ENCAMINHADO', 'ACEITO')",
        }.items()
    }


def test_reservation_and_forward_share_the_request_invariant(case):
    client, db, me, dataset = case
    # Reserva do disponível e encaminhamento do restante: r + c = Q, p = 0.
    partial = add_material(db)
    add_stock(db, dataset, partial, "6")
    request = new_request(client, me, partial)
    warehouse = login(client, "ALMOXARIFADO")
    reserved = reserve(client, warehouse, request, "6")
    assert reserved.status_code == 201, reserved.text
    me = login(client)
    detail = client.get(f"{REQUESTS}/{request['id']}").json()
    response = forward(client, me, detail)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["purchase_forwards"][0]["quantity"] == "4.000000"
    assert result["pending_quantity"] == "0.000000" and result["forwarded_quantity"] == "4.000000"
    totals = request_totals(db, uuid.UUID(request["id"]))
    assert totals == {"r": Decimal(6), "e": Decimal(0), "c": Decimal(4)}
    assert sum(totals.values()) <= Decimal(request["quantity"])
    # Encaminhado tudo com saldo parcial no centro: a reserva não pode usar a mesma unidade.
    integral = add_material(db)
    add_stock(db, dataset, integral, "8")
    second = new_request(client, me, integral)
    forwarded = forward(client, me, second).json()
    assert forwarded["forwarded_quantity"] == "10.000000"
    warehouse = login(client, "ALMOXARIFADO")
    refused = reserve(client, warehouse, forwarded, "1")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "QUANTITY_EXCEEDS_PENDING"
    listed = client.get(f"{REQUESTS}/{second['id']}/reservations").json()
    assert listed["fulfillment"]["forwarded"] == "10" and listed["fulfillment"]["pending"] == "0"
    totals = request_totals(db, uuid.UUID(second["id"]))
    assert totals == {"r": Decimal(0), "e": Decimal(0), "c": Decimal(10)}
    # Devolver devolve a quantidade a `p`: a reserva volta a ser possível dentro do disponível.
    compras = login(client, "COMPRAS")
    item = forwarded["purchase_forwards"][0]
    returned = client.post(
        f"{QUEUE}/{item['id']}/return",
        json={"expected_version": 1, "reason": "Atender pelo estoque."},
        headers=headers(compras),
    )
    assert returned.status_code == 200, returned.text
    warehouse = login(client, "ALMOXARIFADO")
    current = client.get(f"{REQUESTS}/{second['id']}/reservations").json()["fulfillment"]
    assert current["pending"] == "10"
    me = login(client)
    version = client.get(f"{REQUESTS}/{second['id']}").json()["version"]
    warehouse = login(client, "ALMOXARIFADO")
    assert reserve(client, warehouse, {**second, "version": version}, "8").status_code == 201
    totals = request_totals(db, uuid.UUID(second["id"]))
    assert totals == {"r": Decimal(8), "e": Decimal(0), "c": Decimal(0)}
