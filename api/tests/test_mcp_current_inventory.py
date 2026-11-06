"""Chat e API leem a mesma observação atual, incluindo consolidação aprovada."""

import uuid
from collections import defaultdict
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from test_materials import client, search
from test_materials import engines as engines  # noqa: F401
from test_materials import kit as kit  # noqa: F401

from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_mcp.repositories.catalog_repository import CatalogRepository
from vx_materials_mcp.security import Caller, inventory_view


def read_stock(migrated_url, tenant, material_id, centers, financial=False):
    permissions = {"inventory:read"} | ({"metrics:financial"} if financial else set())
    caller = Caller("test", frozenset(permissions), frozenset(centers))
    with temporary_login(migrated_url, "mcp_reader") as url:
        reader = create_engine(url)
        try:
            return CatalogRepository(reader).inventory([str(material_id)], inventory_view(caller), caller.center_codes)
        finally:
            reader.dispose()


def material_id(engines, tenant):
    with engines[0].connect() as db:
        return db.execute(
            text("SELECT id FROM materials_master WHERE tenant_id = :t AND material_code = '10293847'"), {"t": tenant}
        ).scalar_one()


@pytest.mark.parametrize("financial", [False, True])
@pytest.mark.parametrize("centers", [("1100", "1200"), ("1200",), ("9999",)])
def test_mcp_and_api_keep_only_current_dataset_with_consolidation(migrated_url, engines, kit, financial, centers):
    # Um dataset mais novo de outra empresa nunca esconde a observação atual deste tenant.
    with engines[0].begin() as db:
        db.execute(text("INSERT INTO datasets (tenant_id, imported_at) VALUES (:t, '2099-01-01')"), {"t": uuid.uuid4()})
    identifier = material_id(engines, kit)
    rows = read_stock(migrated_url, kit, identifier, centers, financial).get(str(identifier), [])
    actual = defaultdict(lambda: Decimal(0))
    for row in rows:
        actual[row["center_code"]] += Decimal(row["quantity"])
        assert ("total_value" in row) is financial
        assert ("unit_price" in row) is financial
    api = search(client(engines, kit, centers=centers), q="10293847")["items"][0]["inventory"]
    assert dict(actual) == {row["center_code"]: Decimal(row["quantity"]) for row in api}
    expected = {
        center: quantity
        for center, quantity in {"1100": Decimal("7.5"), "1200": Decimal("20")}.items()
        if center in centers
    }
    assert dict(actual) == expected  # exclui 500 antigos; mantém 2CX * fator10 no principal
    if financial:
        expected_value = sum(Decimal({"1100": 1998, "1200": 999}.get(center, 0)) for center in centers)
        assert sum(Decimal(row["total_value"]) for row in rows) == expected_value
        converted_prices = {Decimal(row["unit_price"]) for row in rows if row["center_code"] == "1200"}
        assert converted_prices == ({Decimal(1)} if "1200" in centers else set())
    with engines[0].connect() as db:
        original = db.execute(
            text(
                "SELECT quantity, unit, unit_price, total_value FROM material_inventory_snapshots "
                "WHERE tenant_id = :t AND center_code = '1200' AND source_line = 4"
            ),
            {"t": kit},
        ).one()
        assert original == (Decimal(2), "CX", Decimal(10), Decimal(999))


def test_current_dataset_ties_use_the_same_id_order_in_api_and_mcp(migrated_url, engines, kit):
    identifier = material_id(engines, kit)
    with engines[0].begin() as db:
        # Mesmo instante do dataset atual, mas id maior. O saldo anterior não deve reaparecer.
        dataset = uuid.UUID("ffffffff-ffff-4fff-bfff-ffffffffffff")
        db.execute(
            text("INSERT INTO datasets (id, tenant_id, imported_at) VALUES (:id, :t, '2026-02-01')"),
            {"id": dataset, "t": kit},
        )
        db.execute(
            text(
                "INSERT INTO material_inventory_snapshots "
                "(tenant_id, dataset_id, material_id, center_code, quantity, unit, source_line) "
                "VALUES (:t, :d, :m, '1100', 2, 'PC', 1)"
            ),
            {"t": kit, "d": dataset, "m": identifier},
        )
    rows = read_stock(migrated_url, kit, identifier, ("1100", "1200")).get(str(identifier), [])
    assert [(row["center_code"], Decimal(row["quantity"])) for row in rows] == [("1100", Decimal(2))]
    api = search(client(engines, kit), q="10293847")["items"][0]["inventory"]
    assert [(row["center_code"], Decimal(row["quantity"])) for row in api] == [("1100", Decimal(2))]
