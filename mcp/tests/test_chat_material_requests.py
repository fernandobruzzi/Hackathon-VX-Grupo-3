"""Jornada da solicitação com API, Agent, tools MCP stdio e índice do batch reais."""

import os
import uuid
from contextlib import asynccontextmanager

import httpx
import psycopg
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from test_conversation_flow import PDM, SECRET, SpyClient

from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from pipelines.search_index import run_index
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.cli import alembic_config
from vx_materials_api.db.models import (
    Dataset,
    MaterialInventorySnapshot,
    MaterialMaster,
    MaterialRequest,
    RegistrationOrder,
)
from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_api.main import create_app as create_api
from vx_materials_api.services.agent_client import AgentClient
from vx_materials_mcp.app import create_app as create_agent
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.security import caller_to_environment

ORIGIN = "http://localhost:8000"
ATTRS = {
    "FABRICANTE": "FLSMIDTH",
    "REFERENCIA FABRICANTE": "VX238REAL",
    "APLICACAO": "BRITADOR CONICO",
    "MODELO EQUIPAMENTO": "RAPTOR 450",
}


@pytest.fixture(scope="module")
def flow(monkeypatch_module, tmp_path_factory):
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("Defina TEST_DATABASE_URL para API e MCP reais")
    monkeypatch_module.setenv("APP_ENV", "local")
    monkeypatch_module.setenv("LOCAL_TEST_SESSION", "true")
    monkeypatch_module.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    monkeypatch_module.delenv("BEDROCK_CHAT_MODEL_ID", raising=False)
    catalog = load_pdm(PDM)
    url = make_url(base)
    url = url.set(database=url.database.removesuffix("_test") + "_chat_need_test")
    admin_url = url.render_as_string(hide_password=False)
    conninfo = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(conninfo, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{url.database}"')
    command.upgrade(alembic_config(admin_url), "head")
    admin = create_engine(admin_url)
    validation = validate_pdm(catalog, "PDM110", ATTRS, item_name="BUCHA", unit="PC")
    assert validation.can_submit
    active, blocked = uuid.uuid4(), uuid.uuid4()
    with Session(admin) as db:
        dataset = Dataset(tenant_id=TENANT_ID)
        db.add(dataset)
        db.flush()
        for identifier, code, status, target in [
            (active, "23800001", "ATIVO", None),
            (blocked, "23800002", "BLOQUEADO", active),
        ]:
            db.add(
                MaterialMaster(
                    id=identifier,
                    tenant_id=TENANT_ID,
                    source_system="TEST-238",
                    material_code=code,
                    status=status,
                    active_code_target=target,
                    pdm_class_id="PDM110",
                    attributes=ATTRS,
                    unit="PC",
                    identity_key=validation.identity_key,
                    pdm_description=validation.formatted_description,
                    original_description_long=validation.formatted_description,
                    manufacturer="FLSMIDTH",
                    manufacturer_reference="VX238REAL",
                )
            )
            db.flush()
        db.add(
            MaterialInventorySnapshot(
                tenant_id=TENANT_ID,
                dataset_id=dataset.id,
                material_id=active,
                center_code="1200",
                quantity=10,
                unit="PC",
                unit_price=1,
                total_value=10,
                source_line=1,
                raw_record={},
            )
        )
        db.commit()
    with (
        temporary_login(admin_url, "api_user") as api_url,
        temporary_login(admin_url, "batch_user") as batch_url,
        temporary_login(admin_url, "mcp_reader") as reader,
    ):
        run_index(PDM, database_url=batch_url)
        executed = []

        @asynccontextmanager
        async def connect(caller):
            async with mcp_client.connect(PDM, reader, caller_to_environment(caller)) as real:
                yield SpyClient(real, executed)

        agent = create_agent(catalog, SECRET, connect)
        engine = create_engine(api_url)
        api = create_api(
            session_factory=sessionmaker(engine),
            agent_client=AgentClient("http://agent", transport=httpx.ASGITransport(app=agent)),
        )
        api.state.pdm_catalog = catalog
        with TestClient(api, base_url=ORIGIN) as client:
            yield client, admin, active, executed
        engine.dispose()
    admin.dispose()


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as patch:
        yield patch


def login(client):
    response = client.post(
        "/api/v1/auth/local-session", json={"persona": "SOLICITANTE_OPERACAO"}, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200, response.text
    return response.json()


def headers(me, key=None):
    return {"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": key or str(uuid.uuid4())}


def turn(client, me, message):
    response = client.post(
        "/api/v1/chat/message",
        headers=headers(me),
        json={
            "session_id": None,
            "expected_session_version": 0,
            "client_message_id": str(uuid.uuid4()),
            "message": message,
            "center_code": "1200",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, me, chat):
    response = client.post(
        f"/api/v1/chat/{chat['session_id']}/request-material",
        headers=headers(me),
        json={"expected_session_version": chat["session_version"], "quantity": "3", "unit": "PC"},
    )
    assert response.status_code == 200, response.text
    return response.json()["material_request"]


def test_code_redirect_creates_need_with_active_material_and_no_registration(flow):
    client, admin, active, executed = flow
    me = login(client)
    chat = turn(client, me, "Preciso do código 23800002")
    assert chat["status"] == "EXISTING", chat
    assert chat["material_card"]["existing"]["material_code"] == "23800001"
    assert any(
        name == "search_similar_materials" and arguments["query"] == "código: 23800002" for name, arguments in executed
    )
    row = submit(client, me, chat)
    assert (
        row["material_id"] == str(active) and row["status"] == "EM_ATENDIMENTO" and row["registration_order_id"] is None
    )
    blocked_turn = client.post(
        "/api/v1/chat/message",
        headers=headers(me),
        json={
            "session_id": chat["session_id"],
            "expected_session_version": chat["session_version"] + 1,
            "client_message_id": str(uuid.uuid4()),
            "message": "Mais um item",
            "center_code": "1200",
        },
    )
    assert blocked_turn.status_code == 409
    with Session(admin) as db:
        assert list(db.scalars(select(RegistrationOrder))) == []
        assert db.scalar(select(MaterialInventorySnapshot.quantity)) == 10


def test_nonexistent_complete_item_creates_need_and_linked_registration(flow):
    client, admin, _, _ = flow
    me = login(client)
    chat = turn(
        client,
        me,
        "MANDIBULA MOVEL; APLICACAO: BRITADOR CONICO; MODELO EQUIPAMENTO: RAPTOR 450; "
        "FABRICANTE: FLSMIDTH; REFERENCIA FABRICANTE: VX238NOVA",
    )
    # Resultados apenas semelhantes precisam ser descartados explicitamente antes do cadastro.
    if chat["material_card"]["similar_candidates"]:
        response = client.post(
            "/api/v1/chat/message",
            headers=headers(me),
            json={
                "session_id": chat["session_id"],
                "expected_session_version": chat["session_version"],
                "client_message_id": str(uuid.uuid4()),
                "message": "Nenhum desses é o meu item",
                "center_code": "1200",
                "action": {"type": "DISMISS_CANDIDATES"},
            },
        )
        assert response.status_code == 200, response.text
        chat = response.json()
    assert chat["status"] == "READY_TO_SUBMIT", chat
    row = submit(client, me, chat)
    assert row["status"] == "AGUARDANDO_CADASTRO" and row["registration_order_id"] and row["material_id"] is None
    with Session(admin) as db:
        order = db.get(RegistrationOrder, uuid.UUID(row["registration_order_id"]))
        assert order.status == "READY_FOR_REVIEW" and order.requester_user_id == uuid.UUID(row["requester_user_id"])
        assert len(list(db.scalars(select(MaterialMaster)))) == 2


def test_unknown_item_creates_identification_review_without_registration(flow):
    client, admin, _, _ = flow
    me = login(client)
    with Session(admin) as db:
        before = len(list(db.scalars(select(RegistrationOrder))))
        requests_before = len(list(db.scalars(select(MaterialRequest))))
    chat = turn(client, me, "Preciso de um item que não sei identificar, peça misteriosa")
    row = submit(client, me, chat)
    assert row["status"] == "EM_IDENTIFICACAO" and row["material_id"] is None and row["registration_order_id"] is None
    assert row["protocol"].startswith("SM-")
    with Session(admin) as db:
        assert len(list(db.scalars(select(RegistrationOrder)))) == before
        assert len(list(db.scalars(select(MaterialRequest)))) == requests_before + 1
