"""Chat e API leem a mesma observação atual, incluindo consolidação aprovada."""

import json
import uuid
from collections import defaultdict
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_mcp.repositories.catalog_repository import CatalogRepository
from vx_materials_mcp.security import Caller, inventory_view


@pytest.fixture(scope="module")
def engines(database):
    admin = database["admin"]
    migrated_url = admin.url.render_as_string(hide_password=False)
    with temporary_login(migrated_url, "api_user") as api_url:
        api = create_engine(api_url)
        yield admin, api
        api.dispose()


@pytest.fixture
def kit(engines):
    """Um tenant só deste teste, com dois datasets: o estoque deve vir apenas do mais recente."""
    admin, _ = engines
    tenant = uuid.uuid4()
    with admin.begin() as db:

        def material(code, status="ATIVO", short=None, long=None, unit="PC", ncm="8481.80.95", target=None):
            return db.execute(
                text(
                    "INSERT INTO materials_master (tenant_id, source_system, material_code, status, "
                    "original_description_short, original_description_long, unit, ncm, active_code_target) "
                    "VALUES (:t, 'ERP', :c, :s, :short, :long, :u, :n, :g) RETURNING id"
                ),
                {"t": tenant, "c": code, "s": status, "short": short, "long": long, "u": unit, "n": ncm, "g": target},
            ).scalar_one()

        def dataset(imported_at):
            return db.execute(
                text("INSERT INTO datasets (tenant_id, imported_at) VALUES (:t, :at) RETURNING id"),
                {"t": tenant, "at": imported_at},
            ).scalar_one()

        def stock(dataset_id, material_id, center, quantity, line, unit="PC"):
            return db.execute(
                text(
                    "INSERT INTO material_inventory_snapshots (tenant_id, dataset_id, material_id, center_code, "
                    "quantity, unit, unit_price, total_value, source_line) "
                    "VALUES (:t, :d, :m, :c, :q, :u, 10, 999, :l) RETURNING id"
                ),
                {"t": tenant, "d": dataset_id, "m": material_id, "c": center, "q": quantity, "u": unit, "l": line},
            ).scalar_one()

        def proposal(kind, material_ids, status="PENDING"):
            members = json.dumps([{"material_id": str(value)} for value in material_ids])
            return db.execute(
                text(
                    "INSERT INTO sanitization_proposals (tenant_id, proposal_type, members, changeset_hash, status) "
                    "VALUES (:t, :k, CAST(:m AS jsonb), :h, :s) RETURNING id"
                ),
                {"t": tenant, "k": kind, "m": members, "h": uuid.uuid4().hex, "s": status},
            ).scalar_one()

        valve = material("10293847", short="VALVULA ESFERA 2POL INOX", long="VALVULA ESFERA 2POL INOX 316 ROSCA NPT")
        twin = material("10293848", short="VALV ESF 2 INOX 316", long="VALVULA ESFERA 2 POL INOX 316")
        blocked = material("10500000", status="BLOQUEADO", short="VALVULA ESFERA 2POL ANTIGA", target=valve)
        old = dataset("2026-01-01T00:00:00Z")
        new = dataset("2026-02-01T00:00:00Z")
        stock(old, valve, "1100", "500", 1)
        stock(new, valve, "1100", "6", 1)
        stock(new, valve, "1100", "1.50", 2)
        stock(new, valve, "9000", "40", 3)  # fora do escopo do usuário de teste
        consolidated = stock(new, blocked, "1200", "2", 4, unit="CX")
        stock(new, twin, "1200", "3", 5)
        merge = proposal("MERGE", [valve, twin])
        db.execute(
            text(
                "INSERT INTO inventory_consolidations (source_snapshot_id, tenant_id, primary_material_id, "
                "proposal_id, factor, unit, conversion_source) VALUES (:s, :t, :p, :x, 10, 'PC', 'teste')"
            ),
            {"s": consolidated, "t": tenant, "p": valve, "x": merge},
        )
    yield tenant
    with admin.begin() as db:
        for table in (
            "inventory_consolidations",
            "material_inventory_snapshots",
            "sanitization_proposals",
            "materials_master",
            "datasets",
        ):
            db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant})


def client(engines, tenant, *, role="ROLE_SOLICITANTE", centers=("1100", "1200"), permissions=None):
    _, api = engines
    identity = Identity(
        user_id=uuid.uuid4(),
        tenant_id=tenant,
        roles=(role,),
        permissions=permissions if permissions is not None else permissions_for((role,)),
        center_codes=frozenset(centers),
    )
    app = create_app(session_factory=sessionmaker(api, expire_on_commit=False), identity_provider=lambda db: identity)
    return TestClient(app)


def search(test_client, **query):
    response = test_client.get("/api/v1/materials", params=query)
    assert response.status_code == 200, response.text
    body = response.json()
    return body


def read_stock(database, tenant, material_id, centers, financial=False):
    permissions = {"inventory:read"} | ({"metrics:financial"} if financial else set())
    caller = Caller("test", str(tenant), frozenset(permissions), frozenset(centers))
    reader = create_engine(database["reader"])
    try:
        return CatalogRepository(reader, str(tenant)).inventory(
            [str(material_id)], inventory_view(caller), caller.center_codes
        )
    finally:
        reader.dispose()


def material_id(engines, tenant):
    with engines[0].connect() as db:
        return db.execute(
            text("SELECT id FROM materials_master WHERE tenant_id = :t AND material_code = '10293847'"), {"t": tenant}
        ).scalar_one()


@pytest.mark.parametrize("financial", [False, True])
@pytest.mark.parametrize("centers", [("1100", "1200"), ("1200",), ("9999",)])
def test_mcp_and_api_keep_only_current_dataset_with_consolidation(database, engines, kit, financial, centers):
    # Um dataset mais novo de outra empresa nunca esconde a observação atual deste tenant.
    with engines[0].begin() as db:
        db.execute(text("INSERT INTO datasets (tenant_id, imported_at) VALUES (:t, '2099-01-01')"), {"t": uuid.uuid4()})
    identifier = material_id(engines, kit)
    rows = read_stock(database, kit, identifier, centers, financial).get(str(identifier), [])
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


def test_current_dataset_ties_use_the_same_id_order_in_api_and_mcp(database, engines, kit):
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
    rows = read_stock(database, kit, identifier, ("1100", "1200")).get(str(identifier), [])
    assert [(row["center_code"], Decimal(row["quantity"])) for row in rows] == [("1100", Decimal(2))]
    api = search(client(engines, kit), q="10293847")["items"][0]["inventory"]
    assert [(row["center_code"], Decimal(row["quantity"])) for row in api] == [("1100", Decimal(2))]
