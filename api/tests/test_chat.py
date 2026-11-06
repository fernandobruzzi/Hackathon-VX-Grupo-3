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
        self.result: dict | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"code": "AGENT_TIMEOUT"}})
        return httpx.Response(200, json=self.result or AGENT_RESULT)

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
    return Identity(
        user_id=user_id,
        tenant_id=tenant,
        roles=("ROLE_SOLICITANTE",),
        permissions=permissions,
        center_codes=frozenset({"1100", "1200"}),
        csrf_token="test-csrf",
    )


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
    return client.post(
        "/api/v1/chat/message",
        json=body,
        headers={"Idempotency-Key": str(uuid.uuid4()), "Origin": "http://localhost:8000", "X-CSRF-Token": "test-csrf"},
    )


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
    assert body["material_card"] == {**CARD, "similar_candidates": []}
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
    assert claims["center_codes"] == ["1100", "1200"]
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


def test_center_outside_scope_gets_403(client, agent):
    body = {
        "session_id": None,
        "client_message_id": str(uuid.uuid4()),
        "expected_session_version": 0,
        "message": "parafuso",
        "center_code": "9000",
    }

    response = client.post("/api/v1/chat/message", json=body)

    assert response.status_code == 403
    assert agent.requests == []


EXISTING = {
    "material_code": "16031971",
    "status": "ATIVO",
    "pdm_description": "FILTRO OLEO LUBRIFICANTE",
    "match_type": "EXACT_MANUFACTURER_REFERENCE",
    "reason": "Mesmo item pela regra de identidade do PDM.",
    "inventory": [{"center_code": "1200", "quantity": "4", "unit": "PC"}],
}


def search_call(*candidates, status="SUCCEEDED"):
    return {
        "id": "tool-call-003",
        "name": "search_similar_materials",
        "transport": "MCP_STDIO",
        "input": {"query": "parafuso"},
        "status": status,
        "duration_ms": 9.0,
        "result": {"candidates": list(candidates)} if status == "SUCCEEDED" else {"error": "indisponivel"},
    }


def similar(code, status="ATIVO", verified=False, target=None):
    return {
        "material_code": code,
        "status": status,
        "active_code_target": target,
        "identity_verified": verified,
        "match_type": "TEXT_SIMILARITY",
    }


VALID_CARD = {**CARD, "validation_status": "VALID", "missing_attributes": [], "duplicate_check_status": "NO_MATCH"}


def agent_result(card, *calls, patch=None):
    return {**AGENT_RESULT, "tool_calls": list(calls), "material_card": card, "context_patch": patch or {}}


@pytest.mark.parametrize(
    ("card", "calls", "status", "can_submit"),
    [
        (VALID_CARD, [search_call()], "READY_TO_SUBMIT", True),
        # Busca falhou ou não rodou: a ficha completa continua aguardando.
        (VALID_CARD, [search_call(status="FAILED")], "NEEDS_INPUT", False),
        (VALID_CARD, [], "NEEDS_INPUT", False),
        # Item parecido ainda não descartado pelo solicitante.
        (VALID_CARD, [search_call(similar("777"))], "NEEDS_INPUT", False),
        # Obsoleto nunca precisa ser descartado: não é oferecido.
        (VALID_CARD, [search_call(similar("778", status="OBSOLETO"))], "READY_TO_SUBMIT", True),
        # Mesma identidade encontrada: o Agent não pode dizer que não há item igual.
        (VALID_CARD, [search_call(similar("16031971", verified=True))], "NEEDS_INPUT", False),
        (
            {**CARD, "duplicate_check_status": "MATCH_FOUND", "existing": EXISTING},
            [search_call(similar("16031971", verified=True))],
            "EXISTING",
            False,
        ),
        # Item existente que a busca deste turno não confirma.
        (
            {**CARD, "duplicate_check_status": "MATCH_FOUND", "existing": EXISTING},
            [search_call()],
            "NEEDS_INPUT",
            False,
        ),
        # O Agent não libera o envio sozinho.
        ({**CARD, "duplicate_check_status": "NO_MATCH", "can_submit": True}, [search_call()], "NEEDS_INPUT", False),
    ],
)
def test_api_derives_status_and_submission(client, agent, card, calls, status, can_submit):
    agent.result = agent_result(card, *calls)

    body = send(client).json()

    assert body["status"] == status
    assert body["material_card"]["can_submit"] is can_submit
    validator({"$ref": "#/components/schemas/ChatTurnResponse"}).validate(body)


def test_dismissal_counts_only_for_codes_offered_before(client, agent, factory):
    # O Agent afirma um descarte sem nunca ter oferecido o código: a API não aceita.
    agent.result = agent_result(VALID_CARD, search_call(similar("777")), patch={"dismissed_material_codes": ["777"]})

    first = send(client).json()

    assert first["status"] == "NEEDS_INPUT"
    stored = count(factory, "SELECT context FROM chat_sessions WHERE id = :s", s=first["session_id"])
    assert stored["dismissed_material_codes"] == []


def test_dismissing_offered_codes_releases_submission(client, agent, factory):
    pending = {**VALID_CARD, "duplicate_check_status": "PENDING"}
    agent.result = agent_result(pending, search_call(similar("777")), patch={"offered_material_codes": ["777"]})
    first = send(client).json()
    assert first["status"] == "NEEDS_INPUT"

    agent.result = agent_result(
        VALID_CARD,
        search_call(similar("777")),
        patch={"offered_material_codes": [], "dismissed_material_codes": ["777"]},
    )
    second = send(client, "Nenhum desses é o meu item", first["session_id"], version=1).json()

    assert agent.payload()["context"]["offered_material_codes"] == ["777"]
    assert second["status"] == "READY_TO_SUBMIT"
    assert second["material_card"]["can_submit"] is True


def test_picked_code_must_have_been_offered(client, agent):
    picked = {**CARD, "duplicate_check_status": "MATCH_FOUND", "existing": {**EXISTING, "material_code": "777"}}
    agent.result = agent_result(picked, search_call(similar("777")))
    assert send(client).json()["status"] == "NEEDS_INPUT"

    agent.result = agent_result(
        {**VALID_CARD, "duplicate_check_status": "PENDING"},
        search_call(similar("777")),
        patch={"offered_material_codes": ["777"]},
    )
    first = send(client).json()
    agent.result = agent_result(picked, search_call(similar("777")))

    assert send(client, "É o item 777", first["session_id"], version=1).json()["status"] == "EXISTING"


def test_validating_in_chat_publishes_nothing(client, agent, factory, identity):
    def totals():
        return (
            count(factory, "SELECT count(*) FROM materials_master WHERE tenant_id = :t", t=identity.tenant_id),
            count(factory, "SELECT count(*) FROM registration_orders WHERE tenant_id = :t", t=identity.tenant_id),
        )

    before = totals()
    agent.result = agent_result(VALID_CARD, search_call())

    response = send(client)

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

    assert create_app().state.request_identity_provider is not None
