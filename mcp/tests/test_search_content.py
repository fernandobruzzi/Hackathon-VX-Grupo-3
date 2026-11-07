"""Publicação/aplicação reais e índice batch com credenciais separadas."""

import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from pathlib import Path

import httpx
import psycopg
import pytest
from alembic import command
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from pipelines.search_index import run_index
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.cli import alembic_config
from vx_materials_api.db.models import RegistrationOrder, SanitizationProposal
from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_api.main import create_app
from vx_materials_api.schemas.proposals import proposal_hash
from vx_materials_api.services.agent_client import AgentClient
from vx_materials_mcp.app import create_app as create_agent_app
from vx_materials_mcp.chatbot.mcp_client import connect
from vx_materials_mcp.security import caller_from_environment, caller_to_environment
from vx_materials_mcp.tools.search_similar_materials import SimilarMaterialsSearch

sys.path.insert(0, str(Path(__file__).parents[2] / "api/tests"))
from approval_fixtures import seed_case  # noqa: E402


@pytest.fixture(scope="module")
def content_database_url():
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("Defina TEST_DATABASE_URL para os testes integrados de conteúdo")
    url = make_url(base)
    if not url.database.endswith("_test"):
        pytest.fail("O banco base precisa terminar em _test")
    url = url.set(database=url.database.removesuffix("_test") + "_content_test")
    with psycopg.connect(
        url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False), autocommit=True
    ) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{url.database}"')
    migration = url.render_as_string(hide_password=False)
    command.upgrade(alembic_config(migration), "head")
    return migration


PDM = str(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
ORIGIN = "http://localhost:8000"


@pytest.fixture
def searchable(content_database_url, monkeypatch):
    migrated_url = content_database_url
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    monkeypatch.setenv(
        "VX_CALLER",
        json.dumps(
            {
                "user_id": "reviewer",
                "tenant_id": str(TENANT_ID),
                "permissions": ["inventory:read"],
                "center_codes": ["1100", "1200"],
            }
        ),
    )
    engine = create_engine(migrated_url)
    with Session(engine, expire_on_commit=False) as db:
        catalog, dataset, materials, _, original, principals = seed_case(db, TENANT_ID)
        app = create_app(session_factory=lambda: Session(engine))
        app.state.pdm_catalog = catalog
        try:
            with (
                temporary_login(migrated_url, "api_user") as api,
                temporary_login(migrated_url, "batch_user") as batch,
                temporary_login(migrated_url, "mcp_reader") as reader,
            ):
                api_engine = create_engine(api)
                app.state.session_factory = lambda: Session(api_engine)
                try:
                    with TestClient(app, base_url=ORIGIN) as client:
                        yield {
                            "db": db,
                            "engine": engine,
                            "catalog": catalog,
                            "dataset": dataset,
                            "materials": materials,
                            "original": original,
                            "owner": principals[2].user_id,
                            "client": client,
                            "app": app,
                            "batch": batch,
                            "reader": reader,
                        }
                finally:
                    api_engine.dispose()
        finally:
            db.rollback()
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE users_sso, datasets, materials_master CASCADE"))
    engine.dispose()


def search(case, reference, class_id="PDM100", attributes=None, item_name="FILTRO OLEO LUBRIFICANTE"):
    tool = SimilarMaterialsSearch(case["catalog"], case["reader"], caller_from_environment())
    try:
        return tool.run(
            reference,
            class_id,
            attributes
            or {
                "FABRICANTE": "FLEETGUARD",
                "REFERENCIA FABRICANTE": reference,
            },
            20,
            item_name=item_name,
        )
    finally:
        tool._engine.dispose()


@contextmanager
def automatic_index(case):
    environment = {name: os.environ[name] for name in ("PATH", "LANG", "HOME") if name in os.environ}
    environment.update(DATABASE_URL=case["batch"], APP_ENV="local")
    process = subprocess.Popen(
        [sys.executable, "-m", "cli", "index", "--watch", "--poll-seconds", "1", "--pdm-workbook", PDM],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        Path("/tmp/vx-index-ready").unlink(missing_ok=True)


def decide(case, path, persona, version, **extra):
    client = case["client"]
    me = client.post("/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": ORIGIN}).json()
    response = client.post(
        path,
        json={"expected_version": version, "decision": "APPROVE", "reason": "Conferido", **extra},
        headers={"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_publication_invalidates_until_incremental_batch_finds_current_material(searchable):
    case = searchable
    assert run_index(PDM, case["batch"])["written"] == 2
    from pipelines.import_orders import analyze_order, read_orders
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    row = next(
        row
        for row in read_orders((Path(PDM).parent / "02_pedidos_cadastro.csv").read_bytes())
        if row.source_order_id == "SC-202600001"
    )
    analysis = analyze_order(
        row, case["catalog"], get_classification_repository(case["catalog"]), get_extraction_repository()
    )
    reference = analysis.attributes["REFERENCIA FABRICANTE"]
    order = RegistrationOrder(
        tenant_id=TENANT_ID,
        requester_user_id=case["owner"],
        origin="CHAT",
        original_text="Texto original preservado",
        center_code="1100",
        status="READY_FOR_REVIEW",
        pdm_class_id=analysis.pdm_class_id,
        item_name=analysis.item_name,
        attributes=analysis.attributes,
    )
    case["db"].add(order)
    case["db"].commit()
    path = f"/api/v1/registration-orders/{order.id}/decide"
    technical = decide(case, path, "GESTOR_CADASTRO", 1)
    decide(case, path, "AUDITOR_FISCAL", technical["version"])
    with pytest.raises(ToolError, match="INDEX_UPDATING"):
        search(case, reference, analysis.pdm_class_id, analysis.attributes, item_name=analysis.item_name)
    with automatic_index(case) as process:
        deadline = time.monotonic() + 15
        while True:
            assert process.poll() is None, "O indexador automático encerrou antes de atualizar"
            try:
                found = search(
                    case, reference, analysis.pdm_class_id, analysis.attributes, item_name=analysis.item_name
                )
                break
            except ToolError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
    assert found.match_status == "EXISTING_FOUND"
    assert found.candidates[0].identity_verified
    assert run_index(PDM, case["batch"], if_stale=True)["written"] == 0
    case["db"].refresh(order)
    assert order.material_id is not None
    with case["engine"].connect() as connection:
        row = connection.execute(
            text("SELECT original_description_long, pdm_description FROM materials_master WHERE id=:id"),
            {"id": order.material_id},
        ).one()
    assert row.original_description_long == "Texto original preservado" and reference in row.pdm_description


@pytest.mark.parametrize("item_name", ["FILTRO OLEO LUBRIFICANTE", "FILTRO COMBUSTIVEL"])
def test_technical_application_uses_approved_values_instead_of_previous_interpretation(searchable, item_name):
    case = searchable
    run_index(PDM, case["batch"])
    material = case["materials"][0]
    changes = deepcopy(case["original"].changeset)
    changes["after"]["attributes"]["REFERENCIA FABRICANTE"] = "LF9999"
    changes["after"]["item_name"] = item_name
    changes["sources"] = {"attributes": "Correção aprovada"}
    members = [case["original"].members[0]]
    proposal = SanitizationProposal(
        tenant_id=TENANT_ID,
        proposal_type="PDM_CORRECTION",
        members=members,
        primary_material_id=material.id,
        changeset=changes,
        changeset_hash=proposal_hash(members, changes),
        technical_review_status="PENDING",
        fiscal_review_status="PENDING",
    )
    case["db"].add(proposal)
    case["db"].commit()
    path = f"/api/v1/sanitization/{proposal.id}/decide"
    technical = decide(case, path, "GESTOR_CADASTRO", 1, review_area="TECHNICAL")
    decide(case, path, "AUDITOR_FISCAL", technical["version"], review_area="FISCAL")
    with pytest.raises(ToolError, match="INDEX_UPDATING"):
        search(case, "LF9999")
    result = run_index(PDM, case["batch"], if_stale=True)
    assert result["written"] == 1 and result["pending"] == 0
    found = search(case, "LF9999", item_name=item_name)
    assert found.match_status == "EXISTING_FOUND"
    assert any(c.material_code == material.material_code and c.identity_verified for c in found.candidates)
    with case["engine"].connect() as connection:
        original, current = connection.execute(
            text("SELECT original_description_long, pdm_description FROM materials_master WHERE id=:id"),
            {"id": material.id},
        ).one()
    assert original == "FILTRO FLEETGUARD 100"
    assert current.startswith(item_name + ";") and "LF9999" in current
    old = search(case, "LF9009")
    assert not any(c.material_code == material.material_code and c.identity_verified for c in old.candidates)


def test_revision_changed_during_analysis_is_not_marked_current(searchable, monkeypatch):
    from pipelines import search_index

    case = searchable
    run_index(PDM, case["batch"])
    material = case["materials"][0]
    with case["engine"].begin() as connection:
        connection.execute(text("UPDATE materials_master SET version=version+1 WHERE id=:id"), {"id": material.id})
    original = search_index.analyze_source
    changed = False

    def concurrent(source, *args):
        nonlocal changed
        if not changed:
            changed = True
            with case["engine"].begin() as connection:
                connection.execute(
                    text("UPDATE materials_master SET version=version+1 WHERE id=:id"), {"id": material.id}
                )
        return original(source, *args)

    with monkeypatch.context() as patch:
        patch.setattr(search_index, "analyze_source", concurrent)
        result = run_index(PDM, case["batch"], if_stale=True)
    assert result["pending"] == 1
    with pytest.raises(ToolError, match="INDEX_UPDATING"):
        search(case, "LF9009")
    assert run_index(PDM, case["batch"], if_stale=True)["pending"] == 0
    assert search(case, "LF9009").match_status == "EXISTING_FOUND"


def test_readiness_and_queries_share_one_read_only_snapshot(searchable, monkeypatch):
    from vx_materials_mcp.repositories.catalog_repository import CatalogRepository

    case = searchable
    run_index(PDM, case["batch"])
    original = CatalogRepository.by_identity
    material = case["materials"][0]

    def after_readiness(repository, key, version):
        assert repository._engine.scalar(text("SHOW transaction_read_only")) == "on"
        assert repository._engine.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        with case["engine"].begin() as connection:
            connection.execute(text("UPDATE materials_master SET version=version+1 WHERE id=:id"), {"id": material.id})
        return original(repository, key, version)

    with monkeypatch.context() as patch:
        patch.setattr(CatalogRepository, "by_identity", after_readiness)
        assert search(case, "LF9009").match_status == "EXISTING_FOUND"
    with pytest.raises(ToolError, match="INDEX_UPDATING"):
        search(case, "LF9009")


def test_failed_index_update_leaves_a_recoverable_pending_state(searchable, monkeypatch):
    from pipelines import search_index

    case = searchable
    run_index(PDM, case["batch"])
    with case["engine"].begin() as connection:
        connection.execute(
            text("UPDATE materials_master SET version=version+1 WHERE id=:id"), {"id": case["materials"][0].id}
        )
    with monkeypatch.context() as patch:

        def fail(*args):
            raise RuntimeError("storage unavailable")

        patch.setattr(search_index, "write_search_index", fail)
        with pytest.raises(RuntimeError, match="storage unavailable"):
            run_index(PDM, case["batch"], if_stale=True)
    with pytest.raises(ToolError, match="INDEX_UPDATING"):
        search(case, "LF9009")
    assert run_index(PDM, case["batch"], if_stale=True)["pending"] == 0
    assert search(case, "LF9009").match_status == "EXISTING_FOUND"


def test_an_active_indexer_keeps_a_second_refresh_from_competing(searchable):
    from pipelines.search_index import _index_lock

    case = searchable
    with _index_lock(case["engine"], str(TENANT_ID), wait=True) as locked:
        assert locked
        result = run_index(PDM, case["batch"], if_stale=True)
        assert result["busy"] and result["written"] == 0
        with pytest.raises(ToolError, match="INDEX_UPDATING"):
            search(case, "LF9009")
    assert run_index(PDM, case["batch"], if_stale=True)["pending"] == 0
    assert search(case, "LF9009").match_status == "EXISTING_FOUND"


def test_a_late_old_payload_cannot_overwrite_a_newer_material_revision(searchable, monkeypatch):
    from pipelines import search_index
    from repositories.batch_repository import write_search_index

    case = searchable
    old_rows = []
    write = search_index.write_search_index

    def capture(engine, tenant, version, rows):
        old_rows.extend(deepcopy(rows))
        return write(engine, tenant, version, rows)

    with monkeypatch.context() as patch:
        patch.setattr(search_index, "write_search_index", capture)
        initial = run_index(PDM, case["batch"])
    material = case["materials"][0]
    with case["engine"].begin() as connection:
        connection.execute(text("UPDATE materials_master SET version=version+1 WHERE id=:id"), {"id": material.id})
    run_index(PDM, case["batch"], if_stale=True)
    write_search_index(case["engine"], str(TENANT_ID), initial["index_version"], old_rows)
    with case["engine"].connect() as connection:
        version = connection.scalar(
            text("SELECT source_version FROM material_search_index WHERE material_id=:id"), {"id": material.id}
        )
    assert version == 2
    assert search(case, "LF9009").match_status == "EXISTING_FOUND"


@contextmanager
def real_chat(case, monkeypatch):
    secret = "test-content-proof-secret-with-at-least-32-bytes"
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", secret)

    @asynccontextmanager
    async def mcp(caller):
        async with connect(PDM, case["reader"], caller_to_environment(caller)) as client:
            yield client

    with TestClient(create_agent_app(case["catalog"], secret, mcp)) as agent:

        def transport(request):
            response = agent.post(request.url.path, content=request.content, headers=dict(request.headers))
            return httpx.Response(response.status_code, json=response.json())

        case["app"].state.agent_client = AgentClient("http://agent", httpx.MockTransport(transport))
        yield


def chat_turn(case, message, previous=None, action=None):
    client = case["client"]
    # Os testes conferem se a busca rodou pelas chamadas MCP, que só a role Dev/TI recebe (#232).
    me = client.post("/api/v1/auth/local-session", json={"persona": "DEV_TI"}, headers={"Origin": ORIGIN}).json()
    response = client.post(
        "/api/v1/chat/message",
        json={
            "session_id": previous["session_id"] if previous else None,
            "expected_session_version": previous["session_version"] if previous else 0,
            "client_message_id": str(uuid.uuid4()),
            "message": message,
            "center_code": "1200",
            "action": action,
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("indexed", [True, False])
def test_cached_no_match_is_revalidated_after_real_publication(searchable, monkeypatch, indexed):
    case = searchable
    run_index(PDM, case["batch"])
    with real_chat(case, monkeypatch):
        first = chat_turn(case, "Parafuso sextavado M36x333, classe A4-70, aço inox 316, oxidado preto, DIN 931")
        assert first["status"] == "READY_TO_SUBMIT"
        card = first["material_card"]
        order = RegistrationOrder(
            tenant_id=TENANT_ID,
            requester_user_id=case["owner"],
            origin="CHAT",
            original_text="Pedido de outra conversa",
            center_code="1200",
            pdm_class_id=card["pdm_class_id"],
            item_name="PARAFUSO SEXTAVADO",
            attributes={k: v for k, v in card["attributes"].items() if v},
            status="READY_FOR_REVIEW",
        )
        case["db"].add(order)
        case["db"].commit()
        path = f"/api/v1/registration-orders/{order.id}/decide"
        technical = decide(case, path, "GESTOR_CADASTRO", 1)
        published = decide(case, path, "AUDITOR_FISCAL", technical["version"])
        assert published["status"] == "REGISTERED"
        if indexed:
            assert run_index(PDM, case["batch"], if_stale=True)["pending"] == 0
        second = chat_turn(case, "preciso de 20 unidades", first)
        assert any(call["name"] == "search_similar_materials" for call in second["tool_calls"])
        assert second["status"] == ("EXISTING" if indexed else "NEEDS_INPUT")
        assert second["material_card"]["can_submit"] is False
        if indexed:
            assert second["material_card"]["existing"]["material_code"] == published["material_code"]


@pytest.mark.parametrize("choice", ["PICK_CANDIDATE", "DISMISS_CANDIDATES"])
def test_unchanged_catalog_preserves_real_choices_without_searching_again(searchable, monkeypatch, choice):
    case = searchable
    for index, material in enumerate(case["materials"]):
        material.material_code = str(10000 + index)
    case["db"].commit()
    run_index(PDM, case["batch"])
    with real_chat(case, monkeypatch):
        first = chat_turn(case, "Filtro oleo lubrificante Fleetguard LF9998")
        assert first["status"] == "NEEDS_INPUT" and first["material_card"]["similar_candidates"]
        action = {"type": choice}
        if choice == "PICK_CANDIDATE":
            action["material_code"] = first["material_card"]["similar_candidates"][0]["material_code"]
        reply = f"É o item {action['material_code']}" if choice == "PICK_CANDIDATE" else "Nenhum desses é o meu item"
        second = chat_turn(case, reply, first, action=action)
        expected = "EXISTING" if choice == "PICK_CANDIDATE" else "READY_TO_SUBMIT"
        assert second["status"] == expected
        third = chat_turn(case, "obrigado", second)
        assert third["status"] == expected
        assert not any(call["name"] == "search_similar_materials" for call in third["tool_calls"])
        if choice == "PICK_CANDIDATE":
            assert third["material_card"]["existing"]["material_code"] == action["material_code"]


def test_freshness_counts_only_the_authenticated_tenant(searchable):
    from vx_materials_mcp.repositories.catalog_repository import CatalogRepository

    case = searchable
    version = run_index(PDM, case["batch"])["index_version"]
    other = uuid.uuid4()
    with case["engine"].begin() as connection:
        connection.execute(
            text(
                "INSERT INTO materials_master (tenant_id, source_system, material_code, status) "
                "VALUES (:tenant, 'TEST', 'PRIVATE', 'ATIVO')"
            ),
            {"tenant": other},
        )
    reader = create_engine(case["reader"])
    try:
        assert CatalogRepository(reader, str(TENANT_ID)).index_state(version) == (2, 2)
        assert CatalogRepository(reader, str(other)).index_state(version) == (1, 0)
        assert search(case, "LF9009").match_status == "EXISTING_FOUND"
    finally:
        reader.dispose()


def test_negative_order_check_does_not_mix_old_candidates_with_refreshed_coverage(searchable):
    from sqlalchemy import event

    from vx_materials_api.services.order_service import SearchIndexMissing, existing_materials

    case = searchable
    version = run_index(PDM, case["batch"])["index_version"]
    material = case["materials"][0]
    target = "PDM100|FLEETGUARD|LF9999"
    with case["engine"].begin() as connection:
        connection.execute(text("UPDATE materials_master SET version=2 WHERE id=:id"), {"id": material.id})
    writer = create_engine(case["engine"].url)
    changed = False

    def after_candidates(connection, cursor, statement, parameters, context, executemany):
        nonlocal changed
        if changed or not statement.lstrip().upper().startswith("SELECT") or "material_search_index" not in statement:
            return
        changed = True
        with writer.begin() as concurrent:
            concurrent.execute(
                text("UPDATE materials_master SET identity_key=:key WHERE id=:id"),
                {"key": target, "id": material.id},
            )
            concurrent.execute(
                text(
                    "UPDATE material_search_index SET candidate_identity_key=:key, source_version=2 "
                    "WHERE material_id=:id"
                ),
                {"key": target, "id": material.id},
            )

    event.listen(case["engine"], "after_cursor_execute", after_candidates)
    try:
        with pytest.raises(SearchIndexMissing):
            from pipelines.import_orders import OrderAnalysis

            analysis = OrderAnalysis(
                "READY_FOR_REVIEW",
                "PDM100",
                "FILTRO OLEO LUBRIFICANTE",
                {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9999"},
                (),
                target,
            )
            existing_materials(case["db"], TENANT_ID, case["catalog"], analysis, version)
        assert changed
    finally:
        event.remove(case["engine"], "after_cursor_execute", after_candidates)
        writer.dispose()
