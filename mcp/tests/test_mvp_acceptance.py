"""Aceitação local da #26: API e Agent reais, MCP stdio, batch e PostgreSQL.

O HTTP interno usa ASGITransport; não há simulação de respostas do Agent ou das tools.
Não homologa Cognito, rede, containers nem serviços AWS.
"""

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from test_conversation_flow import PDM, SECRET, SpyClient

from domain.pdm_loader import load_pdm
from pipelines.full_run import run_sanitize
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import (
    AuditLog,
    ChatMessage,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialMaster,
    SanitizationProposal,
)
from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_api.main import create_app as create_api
from vx_materials_api.services.agent_client import AgentClient
from vx_materials_mcp.app import create_app as create_agent
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.security import caller_to_environment

ORIGIN = "http://localhost:8000"


def login(client, persona):
    response = client.post("/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return client.get("/api/v1/auth/me").json()


def headers(me, key=None):
    return {"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": key or str(uuid.uuid4())}


def chat(client, me, message, session_id=None, version=0):
    return client.post(
        "/api/v1/chat/message",
        json={
            "session_id": session_id,
            "client_message_id": str(uuid.uuid4()),
            "expected_session_version": version,
            "message": message,
            "center_code": "1200",
        },
        headers=headers(me),
    )


@pytest.fixture
def flow(database, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    catalog = load_pdm(PDM)
    run_sanitize(PDM, database_url=database["batch"])
    executed = []

    @asynccontextmanager
    async def connect(caller):
        async with mcp_client.connect(PDM, database["reader"], caller_to_environment(caller)) as real:
            yield SpyClient(real, executed)

    agent = create_agent(catalog, SECRET, connect)
    admin_url = database["admin"].url.render_as_string(hide_password=False)
    with temporary_login(admin_url, "api_user") as api_url:
        engine = create_engine(api_url)
        try:
            with engine.connect() as connection, connection.begin():

                def factory():
                    return Session(bind=connection, join_transaction_mode="create_savepoint")

                api = create_api(
                    session_factory=factory,
                    agent_client=AgentClient("http://agent", transport=httpx.ASGITransport(app=agent)),
                )
                api.state.pdm_catalog = catalog
                # Todas as escritas da API são desfeitas; o catálogo compartilhado fica intacto.
                transaction = connection.get_transaction()
                with TestClient(api, base_url=ORIGIN) as client:
                    yield SimpleNamespace(client=client, factory=factory, executed=executed)
                transaction.rollback()
        finally:
            engine.dispose()


def test_login_chat_mcp_batch_approval_audit_and_metrics(flow):
    client = flow.client
    assert client.get("/api/v1/auth/me").status_code == 401
    requester = login(client, "SOLICITANTE_OPERACAO")
    response = chat(client, requester, "Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933")
    assert response.status_code == 200, response.text
    turn = response.json()
    assert turn["status"] == "NEEDS_INPUT" and turn["order_id"] is None
    assert turn["material_card"]["missing_attributes"] == ["CLASSE RESISTENCIA"]
    assert turn["material_card"]["can_submit"] is False
    assert [(call["name"], call["input"]) for call in turn["tool_calls"]] == flow.executed
    assert {call["name"] for call in turn["tool_calls"]} == {
        "get_pdm_template",
        "validate_and_format_pdm",
        "search_similar_materials",
    }
    assert all(call["status"] == "SUCCEEDED" and call["transport"] == "MCP_STDIO" for call in turn["tool_calls"])
    with flow.factory() as db:
        saved = db.scalar(
            select(ChatMessage).where(
                ChatMessage.session_id == uuid.UUID(turn["session_id"]), ChatMessage.author_type == "ASSISTANT"
            )
        )
        assert saved.content == turn["assistant_message"]
        assert saved.tool_calls == turn["tool_calls"]
        # Proposta do produtor batch, não uma proposta fabricada pelo teste/chat.
        proposal_id = db.execute(
            text("""
            SELECT id FROM sanitization_proposals WHERE tenant_id = :tenant_id
            AND status = 'PENDING' AND changeset->>'schema_version' = 'proposal-v1'
            AND proposal_type = 'MERGE'
            AND changeset->'after'->'attributes'->>'REFERENCIA FABRICANTE' = 'WK 569/7'
            AND changeset->'conflicts' = '[]'::jsonb ORDER BY id LIMIT 1
        """),
            {"tenant_id": TENANT_ID},
        ).scalar_one()
        proposal = db.get(SanitizationProposal, proposal_id)
        member_versions = {uuid.UUID(member["material_id"]): member["expected_version"] for member in proposal.members}
        originals = db.execute(
            select(
                MaterialInventorySnapshot.id,
                MaterialInventorySnapshot.quantity,
                MaterialInventorySnapshot.total_value,
                MaterialInventorySnapshot.center_code,
            )
            .where(MaterialInventorySnapshot.material_id.in_(member_versions))
            .order_by(MaterialInventorySnapshot.id)
        ).all()
    path = f"/api/v1/sanitization/{proposal_id}"
    payload = {"expected_version": 1, "review_area": "TECHNICAL", "decision": "APPROVE", "reason": "Aceitação #26."}
    assert client.post(path + "/decide", json=payload, headers=headers(requester)).status_code == 403
    governance = login(client, "GESTOR_CADASTRO")
    calls_before = len(flow.executed)
    forbidden = chat(client, governance, "continuar", turn["session_id"], turn["session_version"])
    assert forbidden.status_code == 404, forbidden.text
    assert len(flow.executed) == calls_before
    assert (
        client.post(path + "/decide", json=payload | {"review_area": "FISCAL"}, headers=headers(governance)).status_code
        == 403
    )
    detail = client.get(path).json()
    before = client.get("/api/v1/dashboard/metrics").json()
    key = str(uuid.uuid4())
    first = client.post(path + "/decide", json=payload, headers=headers(governance, key))
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    assert client.post(path + "/decide", json=payload, headers=headers(governance, key)).json() == first.json()
    with flow.factory() as db:
        assert all(
            db.get(MaterialMaster, material_id).version == version for material_id, version in member_versions.items()
        )
    fiscal = login(client, "AUDITOR_FISCAL")
    assert fiscal["user"]["id"] != governance["user"]["id"]
    assert fiscal["csrf_token"] != governance["csrf_token"]
    assert client.post(path + "/decide", json=payload, headers=headers(fiscal)).status_code == 403
    payload = payload | {"review_area": "FISCAL", "expected_version": first.json()["version"]}
    key = str(uuid.uuid4())
    result = client.post(path + "/decide", json=payload, headers=headers(fiscal, key))
    assert result.status_code == 200, result.text
    assert client.post(path + "/decide", json=payload, headers=headers(fiscal, key)).json() == result.json()
    assert result.json()["status"] == "APPLIED"
    events = []
    cursor = None
    seen_cursors = set()
    while True:
        response = client.get("/api/v1/audit", params={"limit": 1, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200, response.text
        page = response.json()
        events.extend(event for event in page["items"] if event["entity"] == f"proposta {proposal_id}")
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert cursor not in seen_cursors
        seen_cursors.add(cursor)
    assert seen_cursors  # As duas decisões exigem páginas distintas.
    assert len(events) == 2
    assert all(event["before"] and event["after"] and event["reason"] for event in events)
    applied = client.get(path).json()
    assert [(row["center_code"], row["unit"], row["quantity"]) for row in applied["consolidated_inventory"]] == [
        (row["center_code"], row["unit"], row["quantity"]) for row in detail["consolidated_inventory"]
    ]
    with flow.factory() as db:
        primary = db.scalar(
            select(MaterialMaster).where(
                MaterialMaster.material_code == result.json()["result"]["primary_material_code"]
            )
        )
        assert primary.status == "ATIVO" and primary.is_canonical
        assert primary.version == member_versions[primary.id] + 1
        assert primary.ncm == detail["after"]["ncm"] and primary.ncm_review_status == "APPROVED"
        for material_id, version in member_versions.items():
            if material_id != primary.id:
                blocked = db.get(MaterialMaster, material_id)
                assert blocked.status == "BLOQUEADO" and blocked.active_code_target == primary.id
                assert blocked.version == version + 1 and not blocked.is_canonical
        links = db.scalars(
            select(InventoryConsolidation).where(InventoryConsolidation.proposal_id == proposal_id)
        ).all()
        assert len(links) == len(originals)
        assert {link.source_snapshot_id for link in links} == {row.id for row in originals}
        assert all(link.primary_material_id == primary.id and link.factor == 1 and link.unit == "PC" for link in links)
        recorded = db.scalars(select(AuditLog).where(AuditLog.entity_id == str(proposal_id))).all()
        assert len(recorded) == 2
        assert {str(event.actor_user_id) for event in recorded} == {governance["user"]["id"], fiscal["user"]["id"]}
        applied_event = next(event for event in recorded if event.after_json["status"] == "APPLIED")
        assert sum(Decimal(row["total_value"]) for row in applied_event.after_json["inventory"]) == sum(
            row.total_value for row in originals
        )
        assert {row["center_code"] for row in applied_event.after_json["inventory"]} == {
            row.center_code for row in originals
        }
        assert (
            db.execute(
                select(
                    MaterialInventorySnapshot.id,
                    MaterialInventorySnapshot.quantity,
                    MaterialInventorySnapshot.total_value,
                    MaterialInventorySnapshot.center_code,
                )
                .where(MaterialInventorySnapshot.material_id.in_(member_versions))
                .order_by(MaterialInventorySnapshot.id)
            ).all()
            == originals
        )
    after = client.get("/api/v1/dashboard/metrics?view=executive").json()
    assert after["pipeline"]["applied"] == before["pipeline"]["applied"] + 1
    assert after["pipeline"]["pending"] == before["pipeline"]["pending"] - 1
    assert after["before"] == before["before"] and after["after"] is None
    assert after["financial"]["realized_savings"] is None
    assert after["financial"]["data_origin"] == "SYNTHETIC_CHALLENGE_DATA"
    assert client.post("/api/v1/auth/logout", json={}, headers=headers(fiscal)).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
