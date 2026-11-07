"""Resources e prompts pelo protocolo MCP real, com credencial SQL restrita."""

import asyncio
import json
import uuid
from decimal import Decimal

import pytest
from conftest import PDM
from sqlalchemy import create_engine, text

from vx_materials_mcp.chatbot.mcp_client import McpToolError, connect
from vx_materials_mcp.repositories.resource_repository import ResourceRepository
from vx_materials_mcp.security import Caller


def protocol(action, database_url=None, caller=None):
    async def run():
        async with connect(PDM, database_url, json.dumps(caller) if caller else None) as client:
            return await action(client)

    return asyncio.run(run())


def test_resource_templates_and_versioned_prompts_are_discovered():
    async def action(client):
        resources = await client.list_resource_templates()
        prompts = await client.list_prompts()
        return resources, prompts

    resources, prompts = protocol(action)
    assert {r.uri_template for r in resources} == {
        "pdm://{pdm_version}/classes/{pdm_class_id}",
        "ncm://{ncm_version}/codes/{code}",
        "material://{material_code}",
        "evidence://{source_id}",
    }
    assert {p.name for p in prompts} == {
        "interview_material_request_v1",
        "explain_identity_decision_v1",
        "explain_ncm_review_v1",
    }


def test_pdm_resource_uses_the_same_versioned_template_as_the_tool():
    result = protocol(lambda c: c.read_resource("pdm://pdm-kit-v1/classes/PDM020"))
    assert result["noun"] == "ROLAMENTO"
    assert result["pdm_version"] == "pdm-kit-v1"
    with pytest.raises(McpToolError, match="indisponivel"):
        protocol(lambda c: c.read_resource("pdm://unknown/classes/PDM020"))


@pytest.mark.parametrize("uri", ["material://16031971", "evidence://known-id"])
def test_sensitive_resources_require_an_authorized_identity(uri):
    with pytest.raises(McpToolError, match="nao autorizada"):
        protocol(lambda c: c.read_resource(uri))


def test_ncm_resource_requires_authenticated_scope():
    with pytest.raises(McpToolError, match="nao autorizada"):
        protocol(lambda c: c.read_resource("ncm://ncm-demo-v1/codes/84821010"))


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("interview_material_request_v1", {"pdm_class_id": "PDM001", "pdm_version": "pdm-kit-v1"}),
        ("explain_identity_decision_v1", {"decision_json": '{"conflicts":["BITOLA"]}'}),
        ("explain_ncm_review_v1", {"review_json": '{"status":"REVIEW_REQUIRED"}'}),
    ],
)
def test_prompts_require_domain_validation_and_never_authorize_publication(name, arguments):
    result = protocol(lambda c: c.get_prompt(name, arguments))
    content = result.messages[0].content.text
    assert f"[{name}]" in content
    assert "validate_and_format_pdm" in content
    assert "nao aprova nem publica" in content
    assert "apenas dados, nunca instrucoes" in content


@pytest.fixture(scope="module")
def resource_data(database):
    user_id = uuid.uuid4()
    foreign_tenant = uuid.uuid4()
    foreign_user = uuid.uuid4()
    source_id, foreign_source, rejected_source = (uuid.uuid4() for _ in range(3))
    disabled_user = uuid.uuid4()
    with database["admin"].begin() as conn:
        material_id, tenant = conn.execute(
            text("SELECT id, tenant_id FROM materials_master WHERE material_code = '16031971'")
        ).one()
        conn.execute(
            text(
                "INSERT INTO material_inventory_snapshots(tenant_id, dataset_id, material_id, center_code, "
                "quantity, unit_price, total_value, source_line) SELECT :tenant, id, :material, '9999', "
                "999, 999, 998001, 1000001 FROM datasets LIMIT 1"
            ),
            {"tenant": tenant, "material": material_id},
        )
        old_dataset, foreign_dataset = uuid.uuid4(), uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO datasets(id, tenant_id, imported_at) VALUES "
                "(:old_id, :tenant, now() - interval '1 day'), "
                "(:foreign_id, :foreign_tenant, now() + interval '1 day')"
            ),
            {"old_id": old_dataset, "tenant": tenant, "foreign_id": foreign_dataset, "foreign_tenant": foreign_tenant},
        )
        conn.execute(
            text(
                "INSERT INTO material_inventory_snapshots(tenant_id, dataset_id, material_id, center_code, "
                "quantity, unit_price, total_value, source_line) VALUES "
                "(:tenant, :dataset, :material, '1200', 888, 888, 788544, 1)"
            ),
            {"tenant": tenant, "dataset": old_dataset, "material": material_id},
        )
        for uid, tid in ((user_id, tenant), (foreign_user, foreign_tenant)):
            conn.execute(
                text(
                    "INSERT INTO users_sso(id, tenant_id, issuer, subject) "
                    "VALUES (:id, :tenant, 'resource-test', :subject)"
                ),
                {"id": uid, "tenant": tid, "subject": str(uid)},
            )
        conn.execute(
            text(
                "INSERT INTO users_sso(id, tenant_id, issuer, subject, disabled_at) "
                "VALUES (:id, :tenant, 'resource-test', :subject, now())"
            ),
            {"id": disabled_user, "tenant": tenant, "subject": str(disabled_user)},
        )
        foreign_material = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO materials_master(id, tenant_id, source_system, status, "
                "material_code, original_description_long) "
                "VALUES (:id, :tenant, 'TEST', 'ATIVO', 'foreign-resource-code', 'Sigilo outro tenant')"
            ),
            {"id": foreign_material, "tenant": foreign_tenant},
        )
        for sid, mid, tid, status in (
            (source_id, material_id, tenant, "PENDING"),
            (foreign_source, foreign_material, foreign_tenant, "PENDING"),
            (rejected_source, material_id, tenant, "REJECTED"),
        ):
            conn.execute(
                text(
                    "INSERT INTO enrichment_sources(id, tenant_id, material_id, attribute_name, proposed_value, "
                    "source_url, source_title, source_excerpt, retrieved_at, "
                    "confidence_level, confidence_basis, status) "
                    "VALUES (:id, :tenant, :material, 'FABRICANTE', '\"TESTE\"'::jsonb, 'https://example.invalid', "
                    "'Evidencia de teste', 'Trecho de teste', now(), 'HIGH', '[\"EXACT_PART_NUMBER\"]'::jsonb, :status)"
                ),
                {"id": sid, "tenant": tid, "material": mid, "status": status},
            )
    caller = {
        "user_id": str(user_id),
        "tenant_id": str(tenant),
        "permissions": ["materials:read", "inventory:read"],
        "center_codes": ["1200"],
    }
    try:
        yield {
            **database,
            "caller": caller,
            "source": str(source_id),
            "foreign_source": str(foreign_source),
            "foreign_user": str(foreign_user),
            "foreign_tenant": str(foreign_tenant),
            "disabled_user": str(disabled_user),
        }
    finally:
        with database["admin"].begin() as conn:
            for sid in (source_id, foreign_source, rejected_source):
                conn.execute(text("DELETE FROM enrichment_sources WHERE id = :id"), {"id": sid})
            conn.execute(
                text(
                    "DELETE FROM material_inventory_snapshots WHERE dataset_id = :old_dataset "
                    "OR (material_id = :material AND source_line = 1000001 AND center_code = '9999')"
                ),
                {"old_dataset": old_dataset, "material": material_id},
            )
            conn.execute(text("DELETE FROM materials_master WHERE id = :id"), {"id": foreign_material})
            for uid in (user_id, foreign_user, disabled_user):
                conn.execute(text("DELETE FROM users_sso WHERE id = :id"), {"id": uid})
            for did in (old_dataset, foreign_dataset):
                conn.execute(text("DELETE FROM datasets WHERE id = :id"), {"id": did})


def test_material_resource_limits_centers_and_financial_fields(resource_data):
    data = resource_data
    result = protocol(lambda c: c.read_resource("material://16031971"), data["reader"], data["caller"])
    assert result["material_code"] == "16031971"
    assert len(result["inventory"]) == 1
    assert Decimal(result["inventory"][0]["quantity"]) == Decimal("4")
    assert {i["center_code"] for i in result["inventory"]} == {"1200"}
    assert all("unit_price" not in i and "total_value" not in i for i in result["inventory"])
    caller = {**data["caller"], "permissions": ["materials:read", "inventory:read", "metrics:financial"]}
    fiscal = protocol(lambda c: c.read_resource("material://16031971"), data["reader"], caller)
    assert "unit_price" in fiscal["inventory"][0]


def test_evidence_resource_preserves_origin_and_status(resource_data):
    data = resource_data
    result = protocol(lambda c: c.read_resource(f"evidence://{data['source']}"), data["reader"], data["caller"])
    assert result["source_url"] == "https://example.invalid"
    assert result["status"] == "PENDING"
    assert result["material_code"] == "16031971"


def test_known_foreign_material_and_evidence_are_hidden_even_with_same_centers(resource_data):
    data = resource_data
    for uri in ("material://foreign-resource-code", f"evidence://{data['foreign_source']}"):
        with pytest.raises(McpToolError, match="no seu escopo"):
            protocol(lambda c, uri=uri: c.read_resource(uri), data["reader"], data["caller"])
    caller = {**data["caller"], "user_id": data["foreign_user"], "tenant_id": data["foreign_tenant"]}
    with pytest.raises(McpToolError, match="no seu escopo"):
        protocol(lambda c: c.read_resource("material://16031971"), data["reader"], caller)


def test_real_manifest_controls_enrichment_and_ignores_rejected_evidence(resource_data):
    data = resource_data
    result = protocol(
        lambda c: c.call_tool(
            "enrich_from_trusted_source", {"material_code": "16031971", "attributes_requested": ["FABRICANTE"]}
        ),
        data["reader"],
        data["caller"],
    )
    assert result["status"] == "EVIDENCE_FOUND"
    assert len(result["attributes"]) == 1
    assert result["attributes"][0]["fonte"]["source_id"] == data["source"]
    with data["admin"].connect() as conn:
        synthetic = conn.execute(
            text(
                "SELECT material_code FROM materials_master WHERE material_code NOT IN "
                "(SELECT jsonb_array_elements_text(real_material_codes) FROM datasets) LIMIT 1"
            )
        ).scalar_one()
    with pytest.raises(McpToolError, match="15 produtos reais"):
        protocol(
            lambda c: c.call_tool(
                "enrich_from_trusted_source", {"material_code": synthetic, "attributes_requested": ["FABRICANTE"]}
            ),
            data["reader"],
            data["caller"],
        )


def test_unknown_or_disabled_user_and_missing_permission_fail_closed(resource_data):
    data = resource_data
    engine = create_engine(data["reader"])
    try:
        for caller in (
            Caller(str(uuid.uuid4()), data["caller"]["tenant_id"], frozenset({"materials:read"})),
            Caller(data["disabled_user"], data["caller"]["tenant_id"], frozenset({"materials:read"})),
            Caller(data["caller"]["user_id"], data["caller"]["tenant_id"], frozenset()),
        ):
            with pytest.raises(ValueError, match="nao autorizada"):
                ResourceRepository(engine, caller).material("16031971")
    finally:
        engine.dispose()


def test_manifest_allows_all_15_real_codes_and_never_borrows_another_tenant_manifest(resource_data):
    data = resource_data
    engine = create_engine(data["reader"])
    try:
        caller = Caller(data["caller"]["user_id"], data["caller"]["tenant_id"], frozenset({"materials:read"}))
        repository = ResourceRepository(engine, caller)
        with data["admin"].connect() as conn:
            codes = conn.execute(
                text("SELECT real_material_codes FROM datasets WHERE jsonb_array_length(real_material_codes) = 15")
            ).scalar_one()
        assert len(codes) == 15
        for code in codes:
            repository.require_real_material(code)
        foreign = ResourceRepository(engine, Caller(data["foreign_user"], data["foreign_tenant"], caller.permissions))
        with pytest.raises(ValueError, match="15 produtos reais"):
            foreign.require_real_material(codes[0])
    finally:
        engine.dispose()


@pytest.mark.parametrize("operation", ["material", "evidence", "evidence_for_material", "require_real_material"])
def test_resources_bind_active_user_to_the_signed_tenant(resource_data, operation):
    data = resource_data
    caller = Caller(data["foreign_user"], data["caller"]["tenant_id"], frozenset({"materials:read"}))
    arguments = {
        "material": ("foreign-resource-code",),
        "evidence": (data["foreign_source"],),
        "evidence_for_material": ("foreign-resource-code", ["FABRICANTE"]),
        "require_real_material": ("16031971",),
    }
    engine = create_engine(data["reader"])
    try:
        with pytest.raises(ValueError, match="nao autorizada"):
            getattr(ResourceRepository(engine, caller), operation)(*arguments[operation])
    finally:
        engine.dispose()


def test_enrichment_eligibility_never_borrows_an_old_dataset_manifest(resource_data):
    data = resource_data
    latest = uuid.uuid4()
    with data["admin"].begin() as connection:
        connection.execute(
            text("INSERT INTO datasets(id,tenant_id,imported_at) VALUES (:id,:tenant,now()+interval '2 days')"),
            {"id": latest, "tenant": data["caller"]["tenant_id"]},
        )
    engine = create_engine(data["reader"])
    try:
        caller = Caller(data["caller"]["user_id"], data["caller"]["tenant_id"], frozenset({"materials:read"}))
        with pytest.raises(ValueError, match="15 produtos reais"):
            ResourceRepository(engine, caller).require_real_material("16031971")
    finally:
        engine.dispose()
        with data["admin"].begin() as connection:
            connection.execute(text("DELETE FROM datasets WHERE id=:id"), {"id": latest})


def test_stale_signed_tenant_cannot_start_research_after_user_reassignment(resource_data):
    from vx_materials_mcp.tools.enrich_from_trusted_source import Enrichment

    class NeverResearch:
        def validate_request(self, *_args):
            pytest.fail("Identidade desatualizada iniciou pesquisa")

        def run(self, *_args):
            pytest.fail("Identidade desatualizada iniciou consulta externa")

    data = resource_data
    caller = Caller(data["caller"]["user_id"], data["caller"]["tenant_id"], frozenset({"materials:read"}))
    engine = create_engine(data["reader"])
    try:
        with data["admin"].begin() as connection:
            connection.execute(
                text("UPDATE users_sso SET tenant_id=:tenant WHERE id=:id"),
                {"tenant": data["foreign_tenant"], "id": caller.user_id},
            )
        with pytest.raises(ValueError, match="nao autorizada"):
            Enrichment(ResourceRepository(engine, caller), NeverResearch()).run("16031971", ["FABRICANTE"])
    finally:
        engine.dispose()
        with data["admin"].begin() as connection:
            connection.execute(
                text("UPDATE users_sso SET tenant_id=:tenant WHERE id=:id"),
                {"tenant": caller.tenant_id, "id": caller.user_id},
            )


@pytest.fixture
def configured_ncm(tmp_path, monkeypatch):
    from datetime import date
    from pathlib import Path

    from clients.ncm_snapshot_store import NcmSnapshotStore
    from clients.storage import LocalObjectStore
    from domain.ncm_snapshot import NcmSourceKind, load_ncm_snapshot

    raw = (Path(__file__).parents[2] / "back/tests/fixtures/ncm_simulated.json").read_bytes()
    snapshot = load_ncm_snapshot(raw, snapshot_date=date(2026, 11, 6), source_kind=NcmSourceKind.SIMULATED)
    NcmSnapshotStore(LocalObjectStore(tmp_path)).register(snapshot, raw)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("NCM_SNAPSHOT_VERSION", snapshot.version)
    return snapshot, raw, tmp_path


@pytest.mark.parametrize("code", ["73181500", "73181600", "84821010", "01012100", "00000000", "invalid"])
def test_ncm_resource_uses_shared_versioned_snapshot_rules(resource_data, configured_ncm, code):
    import hashlib
    from dataclasses import asdict

    from domain.ncm_snapshot import check_snapshot_ncm

    snapshot, raw, _ = configured_ncm
    expected = json.loads(json.dumps(asdict(check_snapshot_ncm(snapshot, code)), default=str))
    result = protocol(
        lambda c: c.read_resource(f"ncm://{snapshot.version}/codes/{code}"),
        resource_data["reader"],
        resource_data["caller"],
    )
    assert {name: result[name] for name in expected} == expected
    assert result["source_kind"] == "SIMULATED"
    assert result["source_url"] is None
    assert result["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["requires_fiscal_review"] is True
    assert "NCM_SOURCE_UNVERIFIED" in result["reasons"]
    record = snapshot.records.get(expected["normalized_ncm"])
    assert result["record"] == (json.loads(json.dumps(asdict(record), default=str)) if record else None)


def test_ncm_resource_rejects_other_versions(resource_data, configured_ncm):
    with pytest.raises(McpToolError, match="indisponível"):
        protocol(
            lambda c: c.read_resource("ncm://another-version/codes/73181500"),
            resource_data["reader"],
            resource_data["caller"],
        )


def test_ncm_resource_rejects_tampered_snapshot_bytes(resource_data, configured_ncm):
    snapshot, raw, root = configured_ncm
    (root / f"references/ncm/raw/{snapshot.source_sha256}.json").write_bytes(raw + b"\n")
    with pytest.raises(McpToolError, match="indisponível"):
        protocol(
            lambda c: c.read_resource(f"ncm://{snapshot.version}/codes/73181500"),
            resource_data["reader"],
            resource_data["caller"],
        )


def test_unconfigured_ncm_resource_never_falls_back_to_pdm_or_material_ncm(resource_data, monkeypatch):
    monkeypatch.delenv("NCM_SNAPSHOT_VERSION", raising=False)
    with pytest.raises(McpToolError, match="indisponível"):
        protocol(
            lambda c: c.read_resource("ncm://not-configured/codes/73181500"),
            resource_data["reader"],
            resource_data["caller"],
        )
    result = protocol(
        lambda c: c.call_tool(
            "check_ncm_consistency", {"pdm_class_id": "PDM003", "attributes": {}, "ncm": "7318.16.00"}
        ),
        resource_data["reader"],
        resource_data["caller"],
    )
    assert result["exists_in_snapshot"] is None
    assert result["valid_in_snapshot"] is None
    assert result["ncm_source_sha256"] is None
    from domain.ncm_rules import check_ncm_consistency
    from domain.pdm_loader import load_pdm

    expected = check_ncm_consistency(load_pdm(PDM), "PDM003", {}, "7318.16.00")
    assert result["requires_fiscal_review"] is expected.requires_fiscal_review


def test_ncm_resource_authenticates_signed_tenant_before_loading_snapshot(resource_data, configured_ncm):
    snapshot, _, root = configured_ncm
    (root / f"references/ncm/raw/{snapshot.source_sha256}.json").unlink()
    caller = {**resource_data["caller"], "user_id": resource_data["foreign_user"]}
    with pytest.raises(McpToolError, match="nao autorizada"):
        protocol(lambda c: c.read_resource(f"ncm://{snapshot.version}/codes/73181500"), resource_data["reader"], caller)


def test_all_15_bootstrapped_identities_use_scoped_cache_over_stdio(resource_data):
    from enrichment.catalog import REAL_PRODUCTS

    data = resource_data
    source_ids = {code: uuid.uuid4() for code in REAL_PRODUCTS}
    with data["admin"].begin() as connection:
        for code, product in REAL_PRODUCTS.items():
            material_id = connection.execute(
                text("SELECT id FROM materials_master WHERE tenant_id=:tenant AND material_code=:code"),
                {"tenant": data["caller"]["tenant_id"], "code": code},
            ).scalar_one()
            attribute = "REFERENCIA" if product.pdm_class_id == "PDM020" else "REFERENCIA FABRICANTE"
            connection.execute(
                text(
                    "INSERT INTO enrichment_sources(id,tenant_id,material_id,attribute_name,proposed_value,"
                    "source_url,source_title,source_excerpt,retrieved_at,confidence_level,confidence_basis,status) "
                    "VALUES (:id,:tenant,:material,:attribute,CAST(:value AS jsonb),"
                    "'https://example.invalid/protocol-fixture','SIMULACAO - teste de protocolo',"
                    "'SIMULACAO: cache de teste, sem consulta externa',now(),'LOW',"
                    "'[\"SIMULATED\",\"PROTOCOL_TEST_FIXTURE\"]'::jsonb,'PENDING')"
                ),
                {
                    "id": source_ids[code],
                    "tenant": data["caller"]["tenant_id"],
                    "material": material_id,
                    "attribute": attribute,
                    "value": json.dumps(product.reference),
                },
            )
    try:
        for code, product in REAL_PRODUCTS.items():
            attribute = "REFERENCIA" if product.pdm_class_id == "PDM020" else "REFERENCIA FABRICANTE"
            result = protocol(
                lambda client, code=code, attribute=attribute: client.call_tool(
                    "enrich_from_trusted_source", {"material_code": code, "attributes_requested": [attribute]}
                ),
                data["reader"],
                data["caller"],
            )
            assert result["status"] == "EVIDENCE_FOUND", code
            assert result["pending_reason"] is None, code
            assert len(result["attributes"]) == 1, code
            cached = result["attributes"][0]
            assert cached["fonte"]["source_id"] == str(source_ids[code]), code
            assert cached["persisted"] is True and cached["approval_status"] == "PENDING", code
            assert cached["confianca"]["level"] == "LOW", code
            assert "SIMULATED" in cached["confianca"]["basis"], code
    finally:
        with data["admin"].begin() as connection:
            for source_id in source_ids.values():
                connection.execute(text("DELETE FROM enrichment_sources WHERE id=:id"), {"id": source_id})
