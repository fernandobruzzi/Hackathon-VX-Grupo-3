"""Turnos do agente pelo endpoint interno, com o servidor MCP real como subprocesso."""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from domain.pdm_loader import load_pdm
from vx_materials_mcp.app import create_app
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.chatbot.agent import ToolLimitExceeded, ToolRecorder

PDM = str(Path(__file__).parents[2] / "data" / "desafio01" / "03_padrao_cadastro_PDM.xlsx")
SECRET = "test-only-internal-secret-with-32-bytes"
BOLT = "Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933."


class SpyClient:
    """Repassa ao cliente MCP real e anota o que foi de fato executado."""

    def __init__(self, client, executed):
        self._client, self._executed = client, executed

    async def call_tool(self, name, arguments):
        self._executed.append((name, arguments))
        return await self._client.call_tool(name, arguments)


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(PDM)


@pytest.fixture
def executed():
    return []


@pytest.fixture
def client(catalog, executed):
    @asynccontextmanager
    async def connect():
        async with mcp_client.connect(PDM) as real:
            yield SpyClient(real, executed)

    return TestClient(create_app(catalog, SECRET, connect))


def token(**overrides):
    now = int(time.time())
    claims = {"iss": "vx-api", "aud": "vx-agent", "sub": "user-1", "iat": now, "exp": now + 60, "permissions": []}
    return jwt.encode({**claims, **overrides}, SECRET, algorithm="HS256")


def run(client, message, history=(), confirmed=None, bearer=None):
    body = {
        "turn_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "session_version": len(history) // 2,
        "message": message,
        "context": {
            "pdm_version": "pdm-kit-v1",
            "ncm_version": "ncm-demo-v1",
            "center_code": "1200",
            "history": [
                {"id": str(uuid.uuid4()), "author": author, "content": text, "created_at": "2026-11-07T12:00:00Z"}
                for author, text in history
            ],
            "confirmed_attributes": confirmed or {},
        },
    }
    headers = {"X-Request-ID": "req-test", "Authorization": f"Bearer {bearer or token()}"}
    return client.post("/internal/v1/chat/run", json=body, headers=headers)


def test_incomplete_request_lists_missing_fields(client):
    response = run(client, BOLT)

    assert response.status_code == 200
    card = response.json()["material_card"]
    assert card["pdm_class_id"] == "PDM001"
    assert card["validation_status"] == "INCOMPLETE"
    assert "CLASSE RESISTENCIA" in card["missing_attributes"]
    assert card["attributes"]["CLASSE RESISTENCIA"] is None
    assert card["can_submit"] is False


def test_panel_calls_are_the_executed_mcp_calls(client, executed):
    calls = run(client, BOLT).json()["tool_calls"]

    assert [(call["name"], call["input"]) for call in calls] == executed
    assert all(call["transport"] == "MCP_STDIO" and call["status"] == "SUCCEEDED" for call in calls)
    assert calls[1]["result"]["validation_status"] == "INCOMPLETE"


def test_follow_up_answer_completes_the_card(client):
    first = run(client, BOLT).json()
    history = [("user", BOLT), ("assistant", first["assistant_message"])]
    confirmed = first["context_patch"]["confirmed_attributes"]

    second = run(client, "classe 8.8, norma DIN 933", history, confirmed).json()

    card = second["material_card"]
    assert card["attributes"]["CLASSE RESISTENCIA"] == "8.8"
    assert card["validation_status"] == "VALID"
    assert card["pdm_description"]
    # Sem verificação de duplicidade, o chat não libera o envio.
    assert card["duplicate_check_status"] == "PENDING" and card["can_submit"] is False


def test_unknown_material_is_a_business_result(client, executed):
    response = run(client, "quero uma cadeira de escritório")

    assert response.status_code == 200
    assert response.json()["material_card"]["validation_status"] == "OUT_OF_SCOPE"
    assert executed == []


@pytest.mark.parametrize(
    "bearer",
    [
        "not-a-jwt",
        token(aud="vx-api"),
        token(exp=int(time.time()) - 10),
        jwt.encode({"sub": "u", "aud": "vx-agent", "iss": "vx-api"}, "other-secret-with-at-least-32-bytes!", "HS256"),
    ],
)
def test_rejects_invalid_internal_token(client, bearer):
    response = run(client, BOLT, bearer=bearer)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_rejects_identity_fields_in_payload(client):
    response = client.post(
        "/internal/v1/chat/run",
        json={"turn_id": str(uuid.uuid4()), "message": "x", "role": "ROLE_GOVERNANCA"},
        headers={"X-Request-ID": "r", "Authorization": f"Bearer {token()}"},
    )
    assert response.status_code == 422


def test_turn_deadline_returns_503(catalog):
    @asynccontextmanager
    async def slow():
        await asyncio.sleep(1)
        yield None

    client = TestClient(create_app(catalog, SECRET, slow, timeout_seconds=0.05))

    response = run(client, BOLT)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_TIMEOUT"


def test_recorder_stops_after_five_calls():
    class Echo:
        async def call_tool(self, name, arguments):
            return {}

    recorder = ToolRecorder(Echo())

    async def call():
        return await recorder.call("get_pdm_template", {}, lambda result: result)

    for _ in range(5):
        asyncio.run(call())

    with pytest.raises(ToolLimitExceeded):
        asyncio.run(call())
    assert len(recorder.calls) == 5
