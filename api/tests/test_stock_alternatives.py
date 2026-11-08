"""Disponível em outros centros autorizados quando o destino não atende, com PostgreSQL real (#251)."""

import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_contracts import validator as contract
from test_stock_reservations import (
    ORIGIN,
    add_dataset,
    add_material,
    add_stock,
    counts,
    login,
    new_request,
    reserve,
    snapshot_state,
)

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.errors import ApiProblem
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services import stock_service

ALTERNATIVES = "/api/v1/stock/availability/alternatives"
# Fora dos centros das sessões locais (1100, 1200, 1300, 2100, 2200, 9000).
OUT_OF_SCOPE = "7777"


@pytest.fixture
def case(connection, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    app = create_app(session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"))
    with TestClient(app, base_url=ORIGIN) as client:
        with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
            yield client, db


def stock(db, dataset, material, quantity, center, name=None):
    row = add_stock(db, dataset, material, quantity, center=center)
    row.center_name = name
    db.commit()
    return row


def alternatives(client, material, center="1100", quantity=None, status=200):
    params = {"material_id": str(material.id), "center_code": center}
    if quantity is not None:
        params["quantity"] = quantity
    response = client.get(ALTERNATIVES, params=params)
    assert response.status_code == status, response.text
    return response.json()


def test_destination_without_stock_lists_only_authorized_centers_by_availability(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    stock(db, dataset, material, "6", "1300", "Campinas")
    stock(db, dataset, material, "9", "2100", "Recife")
    stock(db, dataset, material, "50", OUT_OF_SCOPE, "Centro de outra pessoa")
    login(client, "SOLICITANTE_OPERACAO")
    before_counts, before_snapshots = counts(db), snapshot_state(db)

    result = alternatives(client, material)

    contract({"$ref": "#/components/schemas/StockAlternatives"}).validate(result)
    assert result["destination"]["center_code"] == "1100"
    assert result["destination"]["available"] == "0"
    assert result["destination_sufficient"] is False
    assert result["needed"] is None
    assert result["alternatives"] == [
        {
            "center_code": "2100",
            "center_name": "Recife",
            "available": "9",
            "unit": "PC",
            "reservable": True,
            "blocked_reason": None,
        },
        {
            "center_code": "1300",
            "center_name": "Campinas",
            "available": "6",
            "unit": "PC",
            "reservable": True,
            "blocked_reason": None,
        },
    ]
    assert result["suggest_purchasing"] is False
    assert OUT_OF_SCOPE not in str(result) and "outra pessoa" not in str(result)
    assert "unit_price" not in str(result) and "total_value" not in str(result)
    # Informativo: nenhuma reserva, movimento, auditoria ou solicitação nova, e snapshots intactos.
    assert counts(db) == before_counts
    assert snapshot_state(db) == before_snapshots


def test_stock_only_outside_the_scope_does_not_change_the_purchasing_suggestion(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    stock(db, dataset, material, "50", OUT_OF_SCOPE)
    login(client, "SOLICITANTE_OPERACAO")

    result = alternatives(client, material, quantity="3")

    assert result["alternatives"] == []
    assert result["suggest_purchasing"] is True
    assert OUT_OF_SCOPE not in str(result)


def test_reserved_stock_and_other_units_never_count_as_an_alternative(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    stock(db, dataset, material, "4", "1300")
    add_stock(db, dataset, material, "8", center="2100", unit="CX")
    requester = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, requester, material, "4", center="1300")
    assert reserve(client, login(client, "ALMOXARIFADO"), request, "4").status_code == 201
    login(client, "SOLICITANTE_OPERACAO")

    result = alternatives(client, material)

    # 1300 tem S = 4 e R = 4; 2100 só tem CX, sem fator conhecido para PC.
    assert result["alternatives"] == []
    assert result["suggest_purchasing"] is True


def test_sufficiency_follows_the_needed_quantity(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    stock(db, dataset, material, "5", "1100")
    stock(db, dataset, material, "7", "1200")
    login(client, "SOLICITANTE_OPERACAO")

    enough = alternatives(client, material, quantity="5")
    assert enough["destination_sufficient"] is True
    assert enough["alternatives"] == [] and enough["suggest_purchasing"] is False
    assert alternatives(client, material)["destination_sufficient"] is True

    short = alternatives(client, material, quantity="10.5")
    assert short["needed"] == "10.5"
    assert short["destination_sufficient"] is False
    assert [item["center_code"] for item in short["alternatives"]] == ["1200"]
    assert short["suggest_purchasing"] is False

    alternatives(client, material, quantity="0", status=422)
    alternatives(client, material, quantity="-1", status=422)


def test_destination_outside_the_scope_or_inactive_material_suggests_nothing(case):
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db, status="OBSOLETO")
    stock(db, dataset, material, "9", "1300")
    login(client, "SOLICITANTE_OPERACAO")

    error = alternatives(client, material, center=OUT_OF_SCOPE, status=403)
    assert error["error"]["code"] == "FORBIDDEN"
    inactive = alternatives(client, material)
    assert inactive["destination"]["blocked_reason"] == "INACTIVE_MATERIAL"
    # Obsoleto nunca é reservado nem encaminhado: nem outro centro, nem compras.
    assert inactive["alternatives"] == [] and inactive["suggest_purchasing"] is False
    assert alternatives(client, add_material(db), center="1300")["suggest_purchasing"] is True


def test_service_only_reads_the_caller_centers(case):
    _, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    stock(db, dataset, material, "3", "1200")
    stock(db, dataset, material, "40", "1300")
    caller = Identity(
        uuid.uuid4(),
        TENANT_ID,
        ("ROLE_SOLICITANTE",),
        permissions_for(("ROLE_SOLICITANTE",)),
        center_codes=frozenset({"1100", "1200"}),
    )

    result = stock_service.other_centers(db, caller, material, "1100")
    assert [item["center_code"] for item in result["alternatives"]] == ["1200"]
    narrowed = stock_service.other_centers(db, replace(caller, center_codes=frozenset({"1100"})), material, "1100")
    # 1300 tem saldo, mas está fora do escopo: o resultado é o mesmo de não haver saldo algum.
    assert narrowed["alternatives"] == [] and narrowed["suggest_purchasing"] is True
    with pytest.raises(ApiProblem) as error:
        stock_service.get_other_centers(db, caller, material.id, "1300", None)
    assert error.value.status == 403
