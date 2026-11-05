"""Turno de chat pela API, com banco real e Agent simulado por transporte HTTP."""

import json
import uuid

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from test_contracts import validator

from vx_materials_api import settings
from vx_materials_api.main import create_app
from vx_materials_api.schemas.chat import ChatMessageRequest
from vx_materials_api.security.identity import Identity
from vx_materials_api.services import chat_service
from vx_materials_api.services.agent_client import AgentClient

SECRET = "test-only-internal-secret-with-32-bytes"
SOLICITANTE = frozenset({"chat:use", "materials:read"})
CARD = {
    "pdm_class_id": "PDM001",
    "pdm_class_name": "PARAFUSO SEXTAVADO",
    "attributes": {"BITOLA": "M12", "CLASSE RESISTENCIA": None},
    "pdm_description": None,
    "validation_status": "INCOMPLETE",
    "missing_attributes": ["CLASSE RESISTENCIA"],
    "ncm": {"suggested": None, "status": "PENDING_VALIDATION"},
    "duplicate_check_status": "PENDING",
    "can_submit": False,
}
AGENT_RESULT = {
    "assistant_message": "Qual é a classe de resistência?",
    "tool_calls": [
        {
            "id": "tool-call-001",
            "name": "validate_and_format_pdm",
            "transport": "MCP_STDIO",
            "input": {"pdm_class_id": "PDM001"},
            "status": "SUCCEEDED",
            "duration_ms": 3.2,
            "result": {"validation_status": "INCOMPLETE"},
        }
    ],
    "context_patch": {"confirmed_attributes": {"BITOLA": "M12"}, "actor_id": "forjado"},
    "material_card": CARD,
}


class FakeAgent:
    """Responde como o Agent e guarda o que recebeu."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"code": "AGENT_TIMEOUT"}})
        return httpx.Response(200, json=AGENT_RESULT)

    def payload(self, index=-1):
        return json.loads(self.requests[index].content)


@pytest.fixture
def factory(migrated_url):
    engine = create_engine(migrated_url)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _new_identity(factory, permissions=SOLICITANTE) -> Identity:
    tenant = uuid.uuid4()
    with factory() as db:
        user_id = db.execute(
            text("INSERT INTO users_sso (tenant_id, issuer, subject) VALUES (:t, 'test', :s) RETURNING id"),
            {"t": tenant, "s": str(uuid.uuid4())},
        ).scalar_one()
        db.commit()
    return Identity(user_id=user_id, tenant_id=tenant, roles=("ROLE_SOLICITANTE",), permissions=permissions)


@pytest.fixture
def identity(factory):
    return _new_identity(factory)


@pytest.fixture
def agent():
    return FakeAgent()


@pytest.fixture
def client(factory, identity, agent, monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    app = create_app(
        session_factory=factory,
        identity_provider=lambda db: identity,
        agent_client=AgentClient("http://agent", transport=httpx.MockTransport(agent)),
    )
    return TestClient(app)


def send(client, message="parafuso M12", session_id=None, version=0, client_message_id=None):
    body = {
        "session_id": str(session_id) if session_id else None,
        "client_message_id": str(client_message_id or uuid.uuid4()),
        "expected_session_version": version,
        "message": message,
        "center_code": "1200",
    }
    return client.post("/api/v1/chat/message", json=body, headers={"Idempotency-Key": str(uuid.uuid4())})


def count(factory, sql, **params):
    with factory() as db:
        return db.execute(text(sql), params).scalar_one()


def test_first_turn_creates_session_and_returns_agent_result(client, agent, factory):
    response = send(client)

    assert response.status_code == 200
    body = response.json()
    assert body["session_version"] == 1
    assert body["status"] == "NEEDS_INPUT"
    assert body["order_id"] is None
    assert body["tool_calls"] == AGENT_RESULT["tool_calls"]
    assert body["material_card"] == CARD
    validator({"$ref": "#/components/schemas/ChatTurnResponse"}).validate(body)
    messages = "SELECT count(*) FROM chat_messages WHERE session_id = :s"
    assert count(factory, messages, s=body["session_id"]) == 2


def test_agent_receives_short_internal_token_and_no_identity_fields(client, agent, identity):
    send(client)

    request = agent.requests[0]
    claims = jwt.decode(
        request.headers["Authorization"].removeprefix("Bearer "), SECRET, algorithms=["HS256"], audience="vx-agent"
    )
    assert claims["sub"] == str(identity.user_id)
    assert claims["exp"] - claims["iat"] <= 60
    assert request.headers["X-Request-ID"].startswith("req-")
    assert not {"role", "roles", "actor_id", "user_id", "tenant_id"} & set(agent.payload())


def test_next_turn_sends_history_and_only_allowed_context(client, agent, factory):
    first = send(client, "parafuso M12").json()

    second = send(client, "classe 8.8", first["session_id"], version=1)

    assert second.status_code == 200 and second.json()["session_version"] == 2
    context = agent.payload()["context"]
    assert [m["author"] for m in context["history"]] == ["user", "assistant"]
    assert context["confirmed_attributes"] == {"BITOLA": "M12"}
    stored = count(factory, "SELECT context FROM chat_sessions WHERE id = :s", s=first["session_id"])
    assert "actor_id" not in stored


def test_stale_version_gets_409(client):
    first = send(client).json()
    send(client, session_id=first["session_id"], version=1)

    response = send(client, session_id=first["session_id"], version=1)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_CONFLICT"


def test_concurrent_turn_gets_409(client, factory, identity):
    first = send(client).json()
    with factory() as db:
        request = ChatMessageRequest(
            session_id=first["session_id"],
            client_message_id=uuid.uuid4(),
            expected_session_version=1,
            message="outra aba",
            center_code="1200",
        )
        chat_service.reserve_turn(db, identity, request)

    response = send(client, session_id=first["session_id"], version=1)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TURN_IN_PROGRESS"


def test_agent_failure_releases_turn_without_saving(client, agent, factory):
    first = send(client).json()
    agent.status = 503

    failed = send(client, session_id=first["session_id"], version=1)

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "AGENT_TIMEOUT"
    assert count(factory, "SELECT count(*) FROM chat_messages WHERE session_id = :s", s=first["session_id"]) == 2
    agent.status = 200
    assert send(client, session_id=first["session_id"], version=1).status_code == 200


def test_other_users_session_is_not_found(client, factory, agent, monkeypatch):
    first = send(client).json()
    stranger = _new_identity(factory)
    other = TestClient(
        create_app(
            session_factory=factory,
            identity_provider=lambda db: stranger,
            agent_client=AgentClient("http://agent", transport=httpx.MockTransport(agent)),
        )
    )

    assert send(other, session_id=first["session_id"], version=1).status_code == 404


def test_without_chat_permission_gets_403(factory, agent, monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    nobody = _new_identity(factory, permissions=frozenset())
    client = TestClient(create_app(session_factory=factory, identity_provider=lambda db: nobody))

    assert send(client).status_code == 403
    assert agent.requests == []


def test_validating_in_chat_publishes_nothing(client, factory, identity):
    def totals():
        return (
            count(factory, "SELECT count(*) FROM materials_master WHERE tenant_id = :t", t=identity.tenant_id),
            count(factory, "SELECT count(*) FROM registration_orders WHERE tenant_id = :t", t=identity.tenant_id),
        )

    before = totals()
    AGENT_RESULT["material_card"] = {**CARD, "validation_status": "VALID", "missing_attributes": []}
    try:
        response = send(client)
    finally:
        AGENT_RESULT["material_card"] = CARD

    assert response.json()["status"] == "READY_TO_SUBMIT"
    assert totals() == before


def test_without_session_gets_401(factory, monkeypatch):
    monkeypatch.delenv("LOCAL_TEST_SESSION", raising=False)
    client = TestClient(create_app(session_factory=factory))

    response = send(client)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("env", [None, "production", "staging"])
def test_test_session_refuses_to_start_outside_local(monkeypatch, env):
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    if env is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", env)

    with pytest.raises(RuntimeError, match="APP_ENV=local"):
        create_app()


def test_test_session_starts_in_local(monkeypatch):
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    monkeypatch.setenv("APP_ENV", settings.LOCAL_ENV)

    assert create_app().state.identity_provider is not None
