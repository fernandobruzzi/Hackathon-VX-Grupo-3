"""Busca de materiais: dados do banco, estoque só dos centros do usuário e nada de preço ou valor."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from test_contracts import validator

from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services.materials_service import search_terms

CONTRACT = validator({"$ref": "#/components/schemas/MaterialList"})


@pytest.fixture(scope="module")
def engines(migrated_url):
    admin = create_engine(migrated_url)
    with temporary_login(migrated_url, "api_user") as api_url:
        api = create_engine(api_url)
        yield admin, api
        api.dispose()
    admin.dispose()


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

        def stock(dataset_id, material_id, center, quantity, line, unit="PC", name=None):
            return db.execute(
                text(
                    "INSERT INTO material_inventory_snapshots "
                    "(tenant_id, dataset_id, material_id, center_code, center_name, "
                    "quantity, unit, unit_price, total_value, source_line) "
                    "VALUES (:t, :d, :m, :c, :name, :q, :u, 10, 999, :l) RETURNING id"
                ),
                {
                    "t": tenant,
                    "d": dataset_id,
                    "m": material_id,
                    "c": center,
                    "name": name,
                    "q": quantity,
                    "u": unit,
                    "l": line,
                },
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
        bolt = material("20000001", short="PARAFUSO SEXT M12", unit="PCA", ncm=None)
        old = dataset("2026-01-01T00:00:00Z")
        new = dataset("2026-02-01T00:00:00Z")
        stock(old, valve, "1100", "500", 1)
        stock(new, valve, "1100", "6", 1, name="MINA NORTE")
        stock(new, valve, "1100", "1.50", 2, name="MINA NORTE")
        stock(new, valve, "9000", "40", 3)  # fora do escopo do usuário de teste
        consolidated = stock(new, blocked, "1200", "2", 4, unit="CX")
        stock(new, twin, "1200", "3", 5)
        merge = proposal("MERGE", [valve, twin])
        proposal("UNIT_CORRECTION", [bolt])
        proposal("MERGE", [bolt], status="REJECTED")
        db.execute(
            text(
                "INSERT INTO inventory_consolidations (source_snapshot_id, tenant_id, primary_material_id, "
                "proposal_id, factor, unit, conversion_source) VALUES (:s, :t, :p, :x, 10, 'PC', 'teste')"
            ),
            {"s": consolidated, "t": tenant, "p": valve, "x": merge},
        )
    return tenant


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
    CONTRACT.validate(body)
    return body


def by_code(body):
    return {item["material_code"]: item for item in body["items"]}


def test_search_by_code_and_description_reads_the_database(engines, kit):
    test_client = client(engines, kit)
    assert [item["material_code"] for item in search(test_client, q="10293848")["items"]] == ["10293848"]
    # Todos os termos precisam aparecer, sem acento e em qualquer caixa, inclusive na descrição longa.
    found = search(test_client, q="válvula esfera 316")
    assert [item["material_code"] for item in found["items"]] == ["10293847", "10293848"]
    assert search(test_client, q="parafuso inexistente")["items"] == []
    # Curingas do LIKE são texto comum.
    assert search(test_client, q="%")["items"] == []


def test_status_filter_and_blocked_items_point_to_the_active_code(engines, kit):
    body = search(client(engines, kit), q="valvula", status="BLOQUEADO")
    assert [(item["material_code"], item["active_code_target"]) for item in body["items"]] == [("10500000", "10293847")]


def test_inventory_respects_user_centers_latest_dataset_and_consolidations(engines, kit):
    items = by_code(search(client(engines, kit), q="valvula"))
    # 6 + 1,5 no centro 1100 do dataset mais recente; o 9000 fica fora do escopo; 2 CX consolidadas
    # com fator 10 aparecem no principal em PC e saem do bloqueado.
    assert items["10293847"]["description"] == "VALVULA ESFERA 2POL INOX 316 ROSCA NPT"
    assert items["10500000"]["description"] == "VALVULA ESFERA 2POL ANTIGA"
    assert items["10293847"]["inventory"] == [
        {"center_code": "1100", "center_name": "MINA NORTE", "quantity": "7.5", "unit": "PC"},
        {"center_code": "1200", "center_name": None, "quantity": "20", "unit": "PC"},
    ]
    assert items["10500000"]["inventory"] == []
    assert items["10293848"]["inventory"] == [
        {"center_code": "1200", "center_name": None, "quantity": "3", "unit": "PC"}
    ]

    only_1200 = by_code(search(client(engines, kit, centers=("1200",)), q="valvula"))
    assert [row["center_code"] for row in only_1200["10293847"]["inventory"]] == ["1200"]
    assert by_code(search(client(engines, kit, centers=()), q="valvula"))["10293847"]["inventory"] == []


def test_session_exposes_only_authorized_center_names(engines, kit):
    response = client(engines, kit, centers=("1100", "1200")).get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["scope"] == {
        "center_codes": ["1100", "1200"],
        "center_names": {"1100": "MINA NORTE"},
    }
    assert client(engines, kit, centers=("1200",)).get("/api/v1/auth/me").json()["scope"] == {
        "center_codes": ["1200"],
        "center_names": {},
    }


def test_financial_role_still_gets_no_price_or_value(engines, kit):
    body = search(client(engines, kit, role="ROLE_AUDITOR_FISCAL", centers=("1100", "9000")), q="10293847")
    rows = body["items"][0]["inventory"]
    assert [row["center_code"] for row in rows] == ["1100", "9000"]
    assert all(set(row) == {"center_code", "center_name", "quantity", "unit"} for row in rows)


def test_flags_come_from_master_data_and_pending_proposals(engines, kit):
    items = by_code(search(client(engines, kit)))
    assert items["10293847"]["flags"] == ["DUPLICIDADE_SUSPEITA"]
    assert items["10293848"]["flags"] == ["DUPLICIDADE_SUSPEITA"]
    # A unificação rejeitada não vira sinal; a correção de unidade pendente vira.
    assert items["20000001"]["flags"] == ["SEM_NCM", "UNIDADE_NAO_CANONICA"]
    assert items["20000001"]["unit"] == "PCA"
    assert items["10500000"]["flags"] == []


def test_pagination_with_cursor(engines, kit):
    test_client = client(engines, kit)
    first = search(test_client, limit=2)
    assert [item["material_code"] for item in first["items"]] == ["10293847", "10293848"]
    assert first["next_cursor"] == "10293848"
    second = search(test_client, limit=2, cursor=first["next_cursor"])
    assert [item["material_code"] for item in second["items"]] == ["10500000", "20000001"]
    assert second["next_cursor"] is None


def test_other_tenants_are_invisible(engines, kit):
    assert search(client(engines, uuid.uuid4()), q="valvula")["items"] == []


def test_without_inventory_permission_stock_is_hidden(engines, kit):
    permissions = permissions_for(("ROLE_SOLICITANTE",)) - {"inventory:read"}
    items = by_code(search(client(engines, kit, permissions=permissions), q="valvula"))
    assert items["10293847"]["inventory"] == []


def test_without_materials_permission_is_forbidden(engines, kit):
    permissions = permissions_for(("ROLE_SOLICITANTE",)) - {"materials:read"}
    response = client(engines, kit, permissions=permissions).get("/api/v1/materials")
    assert response.status_code == 403


def test_invalid_query_parameters(engines, kit):
    test_client = client(engines, kit)
    assert test_client.get("/api/v1/materials", params={"limit": 101}).status_code == 422
    assert test_client.get("/api/v1/materials", params={"status": "ATIVOS"}).status_code == 422
    assert test_client.get("/api/v1/materials", params={"q": "a b c d e f g h i"}).status_code == 422


def test_search_terms_are_normalized():
    assert search_terms(' válvula  "esfera" ') == ["VALVULA", "ESFERA"]
    assert search_terms(None) == []
