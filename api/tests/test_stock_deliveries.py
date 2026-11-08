"""Entrega, cancelamento de reserva e reversão com movimentos auditados, em PostgreSQL real (#240)."""

import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from test_contracts import validator as contract
from test_stock_reservations import (
    NEWER_DATE,
    ORIGIN,
    REQUESTS,
    add_dataset,
    add_material,
    add_stock,
    availability,
    headers,
    login,
    new_request,
    reserve,
    snapshot_state,
)
from test_stock_reservations import case as case  # noqa: F401  (fixture compartilhada)

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
from vx_materials_api.schemas.stock import CreateStockReservation, DeliverStockReservation
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services import stock_service

STOCK = "/api/v1/stock"
FORWARDS = "/api/v1/purchase-forwards"


def version(db, request_id):
    db.expire_all()
    return db.get(MaterialRequest, uuid.UUID(request_id)).version


def deliver(client, me, db, reservation, quantity, key=None, expected=None):
    return client.post(
        f"{STOCK}/reservations/{reservation['id']}/deliveries",
        json={"expected_version": expected or version(db, reservation["request_id"]), "quantity": quantity},
        headers=headers(me, key),
    )


def cancel(client, me, db, reservation, key=None, reason="Material não será retirado.", expected=None):
    return client.post(
        f"{STOCK}/reservations/{reservation['id']}/cancel",
        json={"expected_version": expected or version(db, reservation["request_id"]), "reason": reason},
        headers=headers(me, key),
    )


def reverse(client, me, db, movement, quantity, key=None, reason="Devolvido ao almoxarifado.", expected=None):
    current = expected or version(db, movement["request_id"])
    return client.post(
        f"{STOCK}/movements/{movement['id']}/reversal",
        json={"expected_version": current, "quantity": quantity, "reason": reason},
        headers=headers(me, key),
    )


def error_code(response):
    return response.json()["error"]["code"]


def setup(client, db, stock="10", quantity="6", reserved="6"):
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, stock)
    requester = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, requester, material, quantity)
    clerk = login(client, "ALMOXARIFADO")
    result = reserve(client, clerk, request, reserved)
    assert result.status_code == 201, result.text
    return dataset, material, request, clerk, result.json()["reservation"]


def test_delivery_moves_reserved_to_delivered_without_changing_availability(case):
    client, db = case
    _, material, request, clerk, reservation = setup(client, db)
    before = snapshot_state(db)
    assert availability(client, material)["available"] == "4"

    partial = deliver(client, clerk, db, reservation, "2")
    assert partial.status_code == 201, partial.text
    body = partial.json()
    contract({"$ref": "#/components/schemas/StockMovementResult"}).validate(body)
    assert body["movement"]["movement_type"] == "ENTREGA" and body["movement"]["quantity"] == "2.000000"
    assert body["movement"]["reversed_quantity"] == "0.000000"
    # A entrega parcial mantém o restante reservado.
    assert body["reservation"]["status"] == "ATIVA"
    assert (body["reservation"]["delivered_quantity"], body["reservation"]["open_quantity"]) == (
        "2.000000",
        "4.000000",
    )
    assert body["fulfillment"] == {
        "requested": "6",
        "reserved": "4",
        "delivered": "2",
        "forwarded": "0",
        "pending": "0",
    }
    view = availability(client, material)
    assert (view["imported"], view["reserved"], view["delivered"], view["available"]) == ("10", "4", "2", "4")

    too_much = deliver(client, clerk, db, reservation, "5")
    assert too_much.status_code == 409 and error_code(too_much) == "QUANTITY_EXCEEDS_RESERVATION"

    rest = deliver(client, clerk, db, reservation, "4")
    assert rest.status_code == 201, rest.text
    body = rest.json()
    assert body["reservation"]["status"] == "CONSUMIDA" and body["reservation"]["open_quantity"] == "0.000000"
    assert body["request"]["status"] == "ENCERRADA" and body["request"]["closure_reason"] == "ATENDIDA_ESTOQUE"
    assert body["fulfillment"] == {
        "requested": "6",
        "reserved": "0",
        "delivered": "6",
        "forwarded": "0",
        "pending": "0",
    }
    assert availability(client, material)["available"] == "4"
    again = deliver(client, clerk, db, reservation, "1")
    assert again.status_code == 409 and error_code(again) == "RESERVATION_NOT_ACTIVE"

    events = list(db.scalars(select(AuditLog).where(AuditLog.action == "STOCK_DELIVERED")))
    assert len(events) == 2
    assert {event.effective_role for event in events} == {"ROLE_ALMOXARIFADO"}
    assert all(event.after_json["available_before"] == event.after_json["available_after"] for event in events)
    closed = db.scalar(select(AuditLog).where(AuditLog.action == "MATERIAL_REQUEST_CLOSED"))
    assert closed.entity_id == request["id"] and closed.after_json["closure_reason"] == "ATENDIDA_ESTOQUE"
    login(client, "SOLICITANTE_OPERACAO")
    detail = client.get(f"{REQUESTS}/{request['id']}").json()
    assert detail["history"][-1]["after_status"] == "ENCERRADA"
    assert snapshot_state(db) == before


def test_cancelling_a_reservation_releases_only_what_was_not_delivered(case):
    client, db = case
    _, material, request, clerk, reservation = setup(client, db, quantity="5", reserved="5")
    assert deliver(client, clerk, db, reservation, "2").status_code == 201
    assert availability(client, material)["available"] == "5"

    response = cancel(client, clerk, db, reservation)
    assert response.status_code == 200, response.text
    body = response.json()
    contract({"$ref": "#/components/schemas/StockReservationResult"}).validate(body)
    assert body["reservation"]["status"] == "CANCELADA"
    assert body["reservation"]["delivered_quantity"] == "2.000000"
    assert body["fulfillment"] == {
        "requested": "5",
        "reserved": "0",
        "delivered": "2",
        "forwarded": "0",
        "pending": "3",
    }
    assert body["request"]["status"] == "EM_ATENDIMENTO"
    view = availability(client, material)
    assert (view["reserved"], view["delivered"], view["available"]) == ("0", "2", "8")
    event = db.scalar(select(AuditLog).where(AuditLog.action == "STOCK_RESERVATION_CANCELLED"))
    assert event.after_json["released_quantity"] == "3.000000"
    assert event.after_json["available_after"] == "8" and event.reason == "Material não será retirado."
    assert event.effective_role == "ROLE_ALMOXARIFADO"
    again = cancel(client, clerk, db, reservation)
    assert again.status_code == 409 and error_code(again) == "RESERVATION_NOT_ACTIVE"
    # A entrega feita permanece e pode ser revertida à parte.
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 1


def test_reversal_inserts_a_compensating_movement_and_returns_availability(case):
    client, db = case
    _, material, request, clerk, reservation = setup(client, db, quantity="4", reserved="4")
    delivered = deliver(client, clerk, db, reservation, "4").json()
    assert delivered["request"]["status"] == "ENCERRADA"
    movement = delivered["movement"]
    assert availability(client, material)["available"] == "6"

    response = reverse(client, clerk, db, movement, "1")
    assert response.status_code == 201, response.text
    body = response.json()
    contract({"$ref": "#/components/schemas/StockMovementResult"}).validate(body)
    assert body["movement"]["movement_type"] == "REVERSAO"
    assert body["movement"]["reverses_movement_id"] == movement["id"]
    assert body["movement"]["reversed_quantity"] is None
    assert body["fulfillment"] == {
        "requested": "4",
        "reserved": "0",
        "delivered": "3",
        "forwarded": "0",
        "pending": "1",
    }
    # Encerrada não reabre: o restante volta ao saldo do centro, não à solicitação.
    assert body["request"]["status"] == "ENCERRADA" and body["request"]["closure_reason"] == "ATENDIDA_ESTOQUE"
    assert body["reservation"]["status"] == "CONSUMIDA"
    view = availability(client, material)
    assert (view["reserved"], view["delivered"], view["available"]) == ("0", "3", "7")

    original = db.get(StockMovement, uuid.UUID(movement["id"]))
    db.refresh(original)
    assert original.quantity == Decimal("4") and original.movement_type == "ENTREGA"
    too_much = reverse(client, clerk, db, movement, "4")
    assert too_much.status_code == 409 and error_code(too_much) == "QUANTITY_EXCEEDS_REVERSIBLE"
    assert reverse(client, clerk, db, movement, "3").status_code == 201
    exhausted = reverse(client, clerk, db, movement, "0.5")
    assert exhausted.status_code == 409 and error_code(exhausted) == "QUANTITY_EXCEEDS_REVERSIBLE"
    not_delivery = reverse(client, clerk, db, body["movement"], "1")
    assert not_delivery.status_code == 409 and error_code(not_delivery) == "MOVEMENT_NOT_DELIVERY"
    assert availability(client, material)["available"] == "10"

    events = list(db.scalars(select(AuditLog).where(AuditLog.action == "STOCK_DELIVERY_REVERSED")))
    assert len(events) == 2
    assert all(event.reason == "Devolvido ao almoxarifado." for event in events)
    assert all(event.effective_role == "ROLE_ALMOXARIFADO" for event in events)
    listing = client.get(f"{REQUESTS}/{request['id']}/reservations").json()
    contract({"$ref": "#/components/schemas/StockReservationList"}).validate(listing)
    assert [item["movement_type"] for item in listing["movements"]] == ["ENTREGA", "REVERSAO", "REVERSAO"]
    assert listing["movements"][0]["reversed_quantity"] == "4.000000"


def test_reversal_of_a_delivery_from_a_previous_dataset_is_refused(case):
    client, db = case
    _, material, _, clerk, reservation = setup(client, db, quantity="4", reserved="4")
    movement = deliver(client, clerk, db, reservation, "2").json()["movement"]
    current = add_dataset(db, imported_at=NEWER_DATE)
    add_stock(db, current, material, "8")
    refused = reverse(client, clerk, db, movement, "1")
    assert refused.status_code == 409 and error_code(refused) == "MOVEMENT_FROM_PREVIOUS_DATASET"
    # Entregar a reserva antiga registra a saída no dataset vigente; `D` não muda.
    before = availability(client, material)
    response = deliver(client, clerk, db, reservation, "2")
    assert response.status_code == 201, response.text
    assert response.json()["movement"]["dataset_id"] == str(current.id)
    after = availability(client, material)
    assert after["available"] == before["available"]
    assert (after["reserved"], after["delivered"]) == ("0", "2")


def test_only_authorized_roles_in_scope_deliver_cancel_or_reverse(case):
    client, db = case
    _, _, request, clerk, reservation = setup(client, db, quantity="4", reserved="4")
    movement = deliver(client, clerk, db, reservation, "1").json()["movement"]
    for persona in ("SOLICITANTE_OPERACAO", "GESTOR_CADASTRO", "COMPRAS"):
        me = login(client, persona)
        assert deliver(client, me, db, reservation, "1").status_code == 403
        assert cancel(client, me, db, reservation).status_code == 403
        assert reverse(client, me, db, movement, "1").status_code == 403
    clerk = login(client, "ALMOXARIFADO")
    other_center = Identity(
        uuid.UUID(clerk["user"]["id"]),
        TENANT_ID,
        ("ROLE_ALMOXARIFADO",),
        permissions_for(("ROLE_ALMOXARIFADO",)),
        frozenset({"1100"}),
        authentication_method="bearer",
    )
    client.app.state.request_identity_provider = lambda request, session: other_center
    plain = {"Idempotency-Key": str(uuid.uuid4())}
    current = version(db, request["id"])
    paths = [
        (f"{STOCK}/reservations/{reservation['id']}/deliveries", {"expected_version": current, "quantity": "1"}),
        (f"{STOCK}/reservations/{reservation['id']}/cancel", {"expected_version": current, "reason": "x"}),
        (f"{STOCK}/movements/{movement['id']}/reversal", {"expected_version": current, "quantity": "1", "reason": "x"}),
    ]
    for path, body in paths:
        assert client.post(path, json=body, headers=plain).status_code == 404
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 1
    assert db.scalar(select(StockReservation.status)) == "ATIVA"


def test_operations_are_idempotent_versioned_and_require_csrf(case):
    client, db = case
    _, _, request, clerk, reservation = setup(client, db, quantity="6", reserved="6")
    key = str(uuid.uuid4())
    first = deliver(client, clerk, db, reservation, "2", key=key)
    assert first.status_code == 201
    replay = deliver(client, clerk, db, reservation, "2", key=key, expected=first.json()["request"]["version"] - 1)
    assert replay.json() == first.json()
    changed = deliver(client, clerk, db, reservation, "3", key=key)
    assert changed.status_code == 409 and error_code(changed) == "IDEMPOTENCY_CONFLICT"
    stale = deliver(client, clerk, db, reservation, "1", expected=first.json()["request"]["version"] - 1)
    assert stale.status_code == 409 and error_code(stale) == "VERSION_CONFLICT"
    url = f"{STOCK}/reservations/{reservation['id']}/deliveries"
    body = {"expected_version": version(db, request["id"]), "quantity": "1"}
    assert client.post(url, json=body, headers={"Origin": ORIGIN, "Idempotency-Key": key}).status_code == 403
    hostile = {**headers(clerk), "Origin": "https://hostil.example"}
    assert client.post(url, json=body, headers=hostile).status_code == 403
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 1
    assert db.scalar(select(func.count()).where(AuditLog.action == "STOCK_DELIVERED")) == 1

    movement = first.json()["movement"]
    reversal_key = str(uuid.uuid4())
    reversal = reverse(client, clerk, db, movement, "1", key=reversal_key)
    assert reversal.status_code == 201
    replayed = reverse(
        client, clerk, db, movement, "1", key=reversal_key, expected=reversal.json()["request"]["version"] - 1
    )
    assert replayed.json() == reversal.json()
    cancel_key = str(uuid.uuid4())
    cancelled = cancel(client, clerk, db, reservation, key=cancel_key)
    assert cancelled.status_code == 200
    replayed = cancel(
        client, clerk, db, reservation, key=cancel_key, expected=cancelled.json()["request"]["version"] - 1
    )
    assert replayed.json() == cancelled.json()
    assert db.scalar(select(func.count()).where(AuditLog.action == "STOCK_DELIVERY_REVERSED")) == 1
    assert db.scalar(select(func.count()).where(AuditLog.action == "STOCK_RESERVATION_CANCELLED")) == 1


@pytest.mark.parametrize("seed", [240, 2026, 7])
def test_any_sequence_keeps_quantities_conserved(case, seed):
    """Sequência aleatória de reservas, entregas, cancelamentos, reversões e encaminhamentos (seção 11)."""
    client, db = case
    rng = random.Random(seed)
    dataset = add_dataset(db)
    material = add_material(db)
    # Saldo menor que a soma das solicitações (6 + 7), para que encaminhar para compras seja possível.
    add_stock(db, dataset, material, "5")
    persona = {"name": "SOLICITANTE_OPERACAO", "me": login(client, "SOLICITANTE_OPERACAO")}
    requests = [new_request(client, persona["me"], material, quantity) for quantity in ("6", "7")]
    request_ids = [uuid.UUID(item["id"]) for item in requests]
    before_snapshots = snapshot_state(db)
    reservations, movements = [], []
    amounts = ["1", "2", "3", "4", "0.5", "1.5"]
    accepted = {name: 0 for name in ("reserve", "deliver", "cancel", "reverse", "forward", "handle")}

    def as_(name):
        if persona["name"] != name:
            persona.update(name=name, me=login(client, name))
        return persona["me"]

    def state():
        db.expire_all()
        return stock_service.compute_availability(db, TENANT_ID, db.get(MaterialMaster, material.id), "1200")

    choices = ["reserve", "deliver", "deliver", "cancel", "reverse", "reverse", "forward", "handle"]
    for _ in range(60):
        operation = rng.choice(choices)
        quantity = rng.choice(amounts)
        previous = state()
        if operation == "reserve":
            request = rng.choice(requests)
            response = reserve(client, as_("ALMOXARIFADO"), request, quantity, version=version(db, request["id"]))
            allowed = {"INSUFFICIENT_STOCK", "QUANTITY_EXCEEDS_PENDING", "REQUEST_NOT_IN_FULFILLMENT"}
            if response.status_code == 201:
                reservations.append(response.json()["reservation"])
        elif operation == "deliver" and reservations:
            response = deliver(client, as_("ALMOXARIFADO"), db, rng.choice(reservations), quantity)
            allowed = {"RESERVATION_NOT_ACTIVE", "QUANTITY_EXCEEDS_RESERVATION"}
            if response.status_code == 201:
                movements.append(response.json()["movement"])
        elif operation == "cancel" and reservations:
            response = cancel(client, as_("ALMOXARIFADO"), db, rng.choice(reservations))
            allowed = {"RESERVATION_NOT_ACTIVE"}
        elif operation == "reverse" and movements:
            response = reverse(client, as_("ALMOXARIFADO"), db, rng.choice(movements), quantity)
            allowed = {"QUANTITY_EXCEEDS_REVERSIBLE", "MOVEMENT_NOT_DELIVERY"}
            if response.status_code == 201:
                movements.append(response.json()["movement"])
        elif operation == "forward":
            request = rng.choice(requests)
            response = client.post(
                f"{REQUESTS}/{request['id']}/purchase-forwards",
                json={"expected_version": version(db, request["id"])},
                headers=headers(as_("SOLICITANTE_OPERACAO")),
            )
            allowed = {"STOCK_AVAILABLE", "NOTHING_PENDING", "REQUEST_NOT_IN_SERVICE"}
        elif operation == "handle":
            db.expire_all()
            # Ordem estável (não pelos UUIDs aleatórios), para a semente reproduzir a mesma sequência.
            forwards = sorted(
                db.scalars(select(PurchaseForward).where(PurchaseForward.material_request_id.in_(request_ids))),
                key=lambda item: (request_ids.index(item.material_request_id), item.request_version),
            )
            if not forwards:
                continue
            forward = rng.choice(forwards)
            accept = rng.random() < 0.5
            body = (
                {"expected_version": forward.version}
                if accept
                else {
                    "expected_version": forward.version,
                    "reason": "Sem fornecedor.",
                }
            )
            response = client.post(
                f"{FORWARDS}/{forward.id}/{'accept' if accept else 'return'}",
                json=body,
                headers=headers(as_("COMPRAS")),
            )
            allowed = {"FORWARD_CLOSED"}
        else:
            continue
        if response.status_code in (200, 201):
            accepted[operation] += 1
        else:
            assert response.status_code == 409 and error_code(response) in allowed, response.text
        current = state()
        delta = current["available"] - previous["available"]
        if operation in ("deliver", "forward", "handle") or response.status_code not in (200, 201):
            assert delta == 0  # entregar e encaminhar não mudam `D`; recusas não mudam nada
        elif operation == "reverse":
            assert delta == Decimal(quantity)
        elif operation == "reserve":
            assert delta == -Decimal(quantity)
        assert current["available"] >= 0 and current["reserved"] >= 0 and current["delivered"] >= 0
        assert current["imported"] == current["available"] + current["reserved"] + current["delivered"]
        for request_id in request_ids:
            values = stock_service.fulfillment(db, db.get(MaterialRequest, request_id))
            assert min(values["reserved"], values["delivered"], values["forwarded"], values["pending"]) >= 0
            parts = values["reserved"] + values["delivered"] + values["forwarded"] + values["pending"]
            assert parts == values["requested"]
    assert all(accepted.values()), accepted
    assert snapshot_state(db) == before_snapshots


def forward_all(client, db, request):
    response = client.post(
        f"{REQUESTS}/{request['id']}/purchase-forwards",
        json={"expected_version": version(db, request["id"])},
        headers=headers(login(client, "SOLICITANTE_OPERACAO")),
    )
    assert response.status_code == 201, response.text
    return response.json()["purchase_forwards"][-1]


def accept_forward(client, db, forward_id):
    db.expire_all()
    forward = db.get(PurchaseForward, uuid.UUID(forward_id))
    response = client.post(
        f"{FORWARDS}/{forward_id}/accept",
        json={"expected_version": forward.version},
        headers=headers(login(client, "COMPRAS")),
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("accept_first", [False, True])
def test_delivery_and_purchasing_close_the_request_in_one_place(case, accept_first):
    """Entrega de 6 e encaminhamento de 4: encerra `ATENDIDA_PARCIAL_COMPRAS` em qualquer ordem."""
    client, db = case
    _, _, request, _, reservation = setup(client, db, stock="6", quantity="10", reserved="6")
    forward = forward_all(client, db, request)
    assert forward["quantity"] == "4.000000"
    if accept_first:
        accept_forward(client, db, forward["id"])
    body = deliver(client, login(client, "ALMOXARIFADO"), db, reservation, "6").json()
    expected = {"requested": "10", "reserved": "0", "delivered": "6", "forwarded": "4", "pending": "0"}
    assert body["fulfillment"] == expected
    if accept_first:
        assert body["request"]["status"] == "ENCERRADA"
    else:
        # Encaminhamento ainda com Compras: a solicitação espera o aceite.
        assert body["request"]["status"] == "EM_ATENDIMENTO"
        accept_forward(client, db, forward["id"])
    db.expire_all()
    row = db.get(MaterialRequest, uuid.UUID(request["id"]))
    assert (row.status, row.closure_reason) == ("ENCERRADA", "ATENDIDA_PARCIAL_COMPRAS")
    assert db.scalar(select(func.count()).where(AuditLog.action == "MATERIAL_REQUEST_CLOSED")) == 1


def test_closure_reason_follows_section_5():
    base = {"requested": Decimal(10), "reserved": Decimal(0), "pending": Decimal(0)}
    reason = stock_service.closure_reason
    assert reason({**base, "delivered": Decimal(10), "forwarded": Decimal(0)}, False) == "ATENDIDA_ESTOQUE"
    assert reason({**base, "delivered": Decimal(6), "forwarded": Decimal(4)}, False) == "ATENDIDA_PARCIAL_COMPRAS"
    assert reason({**base, "delivered": Decimal(0), "forwarded": Decimal(10)}, False) == "ENCAMINHADA_COMPRAS"
    assert reason({**base, "delivered": Decimal(6), "forwarded": Decimal(4)}, True) is None
    assert reason({**base, "reserved": Decimal(1), "delivered": Decimal(9), "forwarded": Decimal(0)}, False) is None


def test_cancelling_the_request_releases_each_reservation_once(case):
    client, db = case
    _, material, request, clerk, reservation = setup(client, db, stock="6", quantity="10", reserved="6")
    assert deliver(client, clerk, db, reservation, "2").status_code == 201
    forward = forward_all(client, db, request)
    requester = login(client, "SOLICITANTE_OPERACAO")
    response = client.post(
        f"{REQUESTS}/{request['id']}/cancel",
        json={"expected_version": version(db, request["id"]), "reason": "Não preciso mais."},
        headers=headers(requester),
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(PurchaseForward, uuid.UUID(forward["id"])).status == "CANCELADO"
    events = list(db.scalars(select(AuditLog).where(AuditLog.action == "STOCK_RESERVATION_CANCELLED")))
    assert len(events) == 1 and events[0].after_json["released_quantity"] == "4.000000"
    clerk = login(client, "ALMOXARIFADO")
    view = availability(client, material)
    # S = 6: a entrega de 2 continua em `E`; os 4 não entregues voltam uma vez só.
    assert (view["reserved"], view["delivered"], view["available"]) == ("0", "2", "4")
    again = cancel(client, clerk, db, reservation)
    assert again.status_code == 409 and error_code(again) == "RESERVATION_NOT_ACTIVE"
    assert availability(client, material)["available"] == "4"


@pytest.mark.parametrize("check_version", [True, False])
def test_concurrent_deliveries_never_exceed_the_reservation(migrated_url, monkeypatch, check_version):
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
                quantity=Decimal("10"),
                unit="PC",
                source_line=1,
            )
        )
        row = MaterialRequest(
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
        db.add(row)
    with factory() as db:
        created = stock_service.reserve(
            db, identity, row.id, CreateStockReservation(expected_version=1, quantity="6"), uuid.uuid4(), "setup"
        )
    reservation_id = uuid.UUID(created["reservation"]["id"])
    if not check_version:
        # Sem a versão otimista, o limite da reserva sob o bloqueio é o que impede a dupla saída.
        monkeypatch.setattr(stock_service, "_check_version", lambda row, expected: None)
    original = stock_service.compute_availability
    barrier = threading.Barrier(2)

    def slow(*args, **kwargs):
        state = original(*args, **kwargs)
        time.sleep(0.5)
        return state

    monkeypatch.setattr(stock_service, "compute_availability", slow)

    def run(_):
        barrier.wait(timeout=10)
        with factory() as db:
            try:
                payload = DeliverStockReservation(expected_version=2, quantity="4")
                return stock_service.deliver(db, identity, reservation_id, payload, uuid.uuid4(), "concurrent")
            except ApiProblem as error:
                db.rollback()
                return error

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        accepted = [result for result in results if isinstance(result, dict)]
        refused = [result for result in results if isinstance(result, ApiProblem)]
        assert len(accepted) == 1 and len(refused) == 1
        expected = "VERSION_CONFLICT" if check_version else "QUANTITY_EXCEEDS_RESERVATION"
        assert refused[0].status == 409 and refused[0].code == expected
        with factory() as db:
            delivered = db.scalar(
                select(func.sum(StockMovement.quantity)).where(
                    StockMovement.tenant_id == tenant, StockMovement.movement_type == "ENTREGA"
                )
            )
            assert delivered == Decimal("4")
            state = original(db, tenant, db.get(MaterialMaster, material.id), "1200")
            assert (state["reserved"], state["delivered"], state["available"]) == (2, 4, 4)
            assert state["imported"] == state["available"] + state["reserved"] + state["delivered"]
            values = stock_service.fulfillment(db, db.get(MaterialRequest, row.id))
            assert (
                values["reserved"] + values["delivered"] + values["forwarded"] + values["pending"]
                == values["requested"]
            )
    finally:
        with factory.begin() as db:
            db.execute(OperationRequest.__table__.delete().where(OperationRequest.user_id == clerk))
            for table in (AuditLog, StockMovement, StockReservation, MaterialRequest, MaterialInventorySnapshot):
                db.execute(table.__table__.delete().where(table.tenant_id == tenant))
            db.execute(MaterialMaster.__table__.delete().where(MaterialMaster.tenant_id == tenant))
            db.execute(Dataset.__table__.delete().where(Dataset.tenant_id == tenant))
            db.execute(UserSso.__table__.delete().where(UserSso.tenant_id == tenant))
        engine.dispose()
