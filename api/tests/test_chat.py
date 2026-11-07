"""Turno de chat pela API, com banco real e Agent simulado por transporte HTTP."""

import json
import uuid
from copy import deepcopy
from pathlib import Path

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
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
DEV_TI = frozenset({"chat:use", "materials:read", "chat:diagnostics"})
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


def _new_identity(factory, permissions=SOLICITANTE, roles=("ROLE_SOLICITANTE",)) -> Identity:
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
        roles=roles,
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


@pytest.fixture(autouse=True)
def current_rules_path(monkeypatch):
    monkeypatch.setenv(
        "PDM_WORKBOOK_PATH", str(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
    )


@pytest.fixture
def client(factory, identity, agent, monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    app = create_app(
        session_factory=factory,
        identity_provider=lambda db: identity,
        agent_client=AgentClient("http://agent", transport=httpx.MockTransport(agent)),
    )
    return TestClient(app)


def send(
    client, message="parafuso M12", session_id=None, version=0, client_message_id=None, action=None, center="1200"
):
    body = {
        "session_id": str(session_id) if session_id else None,
        "client_message_id": str(client_message_id or uuid.uuid4()),
        "expected_session_version": version,
        "message": message,
        "center_code": center,
    }
    if action is not None:
        body["action"] = action
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
    # Perfil de negócio não recebe o diagnóstico técnico, mas a chamada fica persistida.
    assert body["tool_calls"] == []
    assert body["material_card"] == {**CARD, "similar_candidates": []}
    validator({"$ref": "#/components/schemas/ChatTurnResponse"}).validate(body)
    messages = "SELECT count(*) FROM chat_messages WHERE session_id = :s"
    assert count(factory, messages, s=body["session_id"]) == 2
    saved = "SELECT tool_calls FROM chat_messages WHERE session_id = :s AND author_type = 'ASSISTANT'"
    assert count(factory, saved, s=body["session_id"]) == AGENT_RESULT["tool_calls"]


def test_agent_receives_short_internal_token_and_no_identity_fields(client, agent, identity):
    send(client)

    request = agent.requests[0]
    claims = jwt.decode(
        request.headers["Authorization"].removeprefix("Bearer "), SECRET, algorithms=["HS256"], audience="vx-agent"
    )
    assert claims["sub"] == str(identity.user_id)
    assert claims["center_codes"] == ["1100", "1200"]
    assert claims["tenant_id"] == str(identity.tenant_id)
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


def test_agent_receives_previous_card_identity_and_explicit_attribute_clear(client, agent):
    agent.result = deepcopy(AGENT_RESULT)
    agent.result["context_patch"] |= {
        "pdm_class_id": "PDM003",
        "item_name": "PORCA",
        "confirmed_attributes": {"BITOLA": "M12", "ACABAMENTO": None},
    }
    first = send(client).json()
    response = send(client, "classe 8.8", first["session_id"], version=1)
    assert response.status_code == 200
    context = agent.payload()["context"]
    assert context["pdm_class_id"] == CARD["pdm_class_id"]
    assert context["item_name"] == CARD["pdm_class_name"]
    assert "ACABAMENTO" in context["confirmed_attributes"]
    assert context["confirmed_attributes"]["ACABAMENTO"] is None
    validator({"$ref": "#/components/schemas/AgentRunRequest"}).validate(agent.payload())


def test_agent_failure_preserves_previous_identity_and_explicit_clear(client, agent, factory):
    agent.result = deepcopy(AGENT_RESULT)
    agent.result["context_patch"]["confirmed_attributes"]["ACABAMENTO"] = None
    first = send(client).json()
    sql = "SELECT context FROM chat_sessions WHERE id = :s"
    accepted = count(factory, sql, s=first["session_id"])
    agent.status = 503
    response = send(client, "Não sei informar mais detalhes.", first["session_id"], version=1)
    assert response.status_code == 503
    assert count(factory, sql, s=first["session_id"]) == accepted
    assert count(factory, "SELECT version FROM chat_sessions WHERE id = :s", s=first["session_id"]) == 1
    assert count(factory, "SELECT count(*) FROM chat_messages WHERE session_id = :s", s=first["session_id"]) == 2


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
    from vx_materials_api.routes import chat

    first = send(client).json()

    def unavailable_rules(request):
        raise AssertionError("Foreign-session authorization must precede catalog loading")

    monkeypatch.setattr(chat, "catalog", unavailable_rules)
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
    assert client.get("/api/v1/chat/sessions").status_code == 403
    assert client.get(f"/api/v1/chat/sessions/{uuid.uuid4()}").status_code == 403
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


def _offer(client, agent, code="777"):
    """Primeiro turno: a busca acha um item parecido e o Agent o oferece."""
    pending = {**VALID_CARD, "duplicate_check_status": "PENDING"}
    agent.result = agent_result(pending, search_call(similar(code)), patch={"offered_material_codes": [code]})
    return send(client).json()


@pytest.mark.parametrize(
    "action",
    [{"type": "PICK_CANDIDATE", "material_code": "999"}, {"type": "PICK_CANDIDATE"}],
)
def test_pick_action_for_code_never_offered_gets_422(client, agent, action):
    first = _offer(client, agent)
    calls = len(agent.requests)

    response = send(client, "É este", first["session_id"], version=1, action=action)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ACTION"
    assert len(agent.requests) == calls


def test_dismiss_action_without_offered_items_gets_422(client, agent):
    response = send(client, "Nenhum", action={"type": "DISMISS_CANDIDATES"})

    assert response.status_code == 422
    assert agent.requests == []


def test_dismiss_action_reuses_saved_check_without_search(client, agent):
    first = _offer(client, agent)
    # Mesma ficha, sem nova busca: vale a verificação salva do turno anterior.
    agent.result = agent_result(VALID_CARD, patch={"dismissed_material_codes": ["777"]})

    second = send(client, "texto do botão", first["session_id"], version=1, action={"type": "DISMISS_CANDIDATES"})

    sent = agent.payload()
    assert sent["action"] == {"type": "DISMISS_CANDIDATES", "material_code": None}
    assert sent["context"]["duplicate_check"]["similar_candidates"] == []
    assert "candidates" not in sent["context"]["duplicate_check"]
    assert second.json()["status"] == "READY_TO_SUBMIT"
    restored = client.get(f"/api/v1/chat/sessions/{first['session_id']}").json()
    assert restored["material_card"] == second.json()["material_card"]
    assert restored["material_card"]["similar_candidates"] == []
    assert len(agent.requests) == 2


def test_picked_item_is_kept_on_later_turns(client, agent):
    first = _offer(client, agent)
    picked = {**CARD, "duplicate_check_status": "MATCH_FOUND", "existing": {**EXISTING, "material_code": "777"}}
    agent.result = agent_result(picked, search_call(similar("777")))
    pick = {"type": "PICK_CANDIDATE", "material_code": "777"}
    assert send(client, "É este", first["session_id"], version=1, action=pick).json()["status"] == "EXISTING"

    restored = client.get(f"/api/v1/chat/sessions/{first['session_id']}").json()
    assert restored["material_card"]["existing"]["material_code"] == "777"
    assert restored["session_version"] == 2
    assert len(agent.requests) == 2

    # Turno seguinte sem busca: a escolha salva continua valendo para a mesma ficha.
    agent.result = agent_result(picked)
    third = send(client, "preciso de 20 unidades", first["session_id"], version=2).json()

    assert agent.payload()["context"]["duplicate_check"]["existing"]["material_code"] == "777"
    assert third["status"] == "EXISTING"
    assert third["material_card"]["existing"]["material_code"] == "777"


def test_saved_check_does_not_cover_a_changed_card(client, agent):
    first = _offer(client, agent)
    changed = {**VALID_CARD, "attributes": {"BITOLA": "M16", "CLASSE RESISTENCIA": "8.8"}}
    agent.result = agent_result(changed, patch={"dismissed_material_codes": ["777"]})

    second = send(client, "na verdade M16", first["session_id"], version=1)

    assert second.json()["status"] == "NEEDS_INPUT"
    assert second.json()["material_card"]["can_submit"] is False


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


def test_read_saved_conversation_and_resume_without_agent_replay(client, agent):
    first = send(client).json()
    listed = client.get("/api/v1/chat/sessions").json()
    assert listed["items"][0]["id"] == first["session_id"]
    assert listed["items"][0]["title"] == "parafuso M12"
    restored = client.get(f"/api/v1/chat/sessions/{first['session_id']}")
    assert restored.status_code == 200
    body = restored.json()
    assert body["session_version"] == 1
    assert body["material_card"] == first["material_card"]
    assert body["calls"] == []
    assert [m["content"] for m in body["messages"]] == ["parafuso M12", first["assistant_message"]]
    assert body["processing"] is False
    assert body["center_code"] == "1200"
    assert len(agent.requests) == 1
    assert send(client, "8.8", body["session_id"], body["session_version"]).status_code == 200


@pytest.mark.parametrize("other_tenant", [False, True])
def test_read_conversation_is_private(client, factory, identity, other_tenant):
    from dataclasses import replace

    other = _new_identity(factory)
    if not other_tenant:
        other = replace(other, tenant_id=identity.tenant_id)
    with factory() as db:
        reservation = chat_service.reserve_turn(
            db,
            other,
            ChatMessageRequest(
                session_id=None,
                client_message_id=uuid.uuid4(),
                expected_session_version=0,
                message="privado",
                center_code="1200",
            ),
        )
    assert client.get(f"/api/v1/chat/sessions/{reservation.session_id}").status_code == 404
    assert client.get("/api/v1/chat/sessions").json()["items"] == []


def test_list_conversations_paginates_and_processing_is_recoverable(client, factory, identity):
    for message in ["primeira", "segunda", "terceira"]:
        send(client, message)
    first = client.get("/api/v1/chat/sessions?limit=2").json()
    second = client.get("/api/v1/chat/sessions", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    assert len({item["id"] for item in first["items"] + second["items"]}) == 3
    with factory() as db:
        pending = chat_service.reserve_turn(
            db,
            identity,
            ChatMessageRequest(
                session_id=None,
                client_message_id=uuid.uuid4(),
                expected_session_version=0,
                message="pendente",
                center_code="1200",
            ),
        )
    path = f"/api/v1/chat/sessions/{pending.session_id}"
    assert client.get(path).json()["processing"] is True
    with factory() as db:
        chat_service.release_turn(db, pending)
    assert client.get(path).json()["processing"] is False


@pytest.mark.parametrize("cursor", ["9223372036854775808", "9" * 4301], ids=["offset-overflow", "int-conversion-limit"])
def test_history_rejects_unbounded_cursor(client, cursor):
    response = client.get("/api/v1/chat/sessions", params={"cursor": cursor})
    assert response.status_code == 422


@pytest.mark.parametrize("source", ["session", "inventory", "past_inventory", "legacy_past_inventory"])
def test_history_and_resume_recheck_current_center_scope(factory, identity, agent, monkeypatch, source):
    from dataclasses import replace

    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    current = identity
    client = TestClient(
        create_app(
            session_factory=factory,
            identity_provider=lambda db: current,
            agent_client=AgentClient("http://agent", transport=httpx.MockTransport(agent)),
        )
    )
    if source != "session":
        # O centro do pedido segue permitido; o estoque mostrado vinha de outro centro autorizado.
        agent.result = agent_result(
            {**CARD, "existing": EXISTING}, search_call(similar(EXISTING["material_code"], verified=True))
        )
    if source == "legacy_past_inventory":
        agent.result["assistant_message"] = (
            "Esse item já existe: use o código 16031971. Mesmo item. Estoque nos seus centros: 4 PC no centro 1200."
        )
    first = send(client, center="1200" if source == "session" else "1100").json()
    if source in {"past_inventory", "legacy_past_inventory"}:
        agent.result = AGENT_RESULT
        assert send(client, session_id=first["session_id"], version=1, center="1100").status_code == 200
    if source in {"inventory", "legacy_past_inventory"}:
        # Sessões já persistidas, antes do acumulador, ainda conferem os centros da ficha salva.
        from vx_materials_api.db.models import ChatSession

        with factory() as db:
            session = db.get(ChatSession, first["session_id"])
            session.context = {key: value for key, value in session.context.items() if key != "history_center_codes"}
            db.commit()
    current = replace(identity, center_codes=frozenset({"1100"}))
    assert client.get("/api/v1/chat/sessions").json()["items"] == []
    assert client.get(f"/api/v1/chat/sessions/{first['session_id']}").status_code == 404
    calls_before = len(agent.requests)
    response = client.post(
        "/api/v1/chat/message",
        json={
            "session_id": first["session_id"],
            "client_message_id": str(uuid.uuid4()),
            "expected_session_version": 2 if source in {"past_inventory", "legacy_past_inventory"} else 1,
            "message": "continuar",
            "center_code": "1100",
        },
        headers={"Origin": "http://localhost:8000", "X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 404
    assert len(agent.requests) == calls_before


def test_history_paginates_only_conversations_in_current_centers(factory, identity, agent, monkeypatch):
    from dataclasses import replace

    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    current = identity
    client = TestClient(
        create_app(
            session_factory=factory,
            identity_provider=lambda db: current,
            agent_client=AgentClient("http://agent", transport=httpx.MockTransport(agent)),
        )
    )
    visible = set()
    for center in ["1100", "1200", "1100", "1200"]:
        response = send(client, center=center)
        assert response.status_code == 200
        if center == "1100":
            visible.add(response.json()["session_id"])
    current = replace(identity, center_codes=frozenset({"1100"}))
    first = client.get("/api/v1/chat/sessions", params={"limit": 1}).json()
    second = client.get("/api/v1/chat/sessions", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == len(second["items"]) == 1
    assert {row["id"] for page in [first, second] for row in page["items"]} == visible
    assert second["next_cursor"] is None


@pytest.mark.parametrize(
    "author,content,status",
    [
        ("ASSISTANT", "Esse item já existe: use o código 123. Motivo. Estoque nos seus centros: sem centro.", 404),
        (
            "ASSISTANT",
            "Esse item já existe: use o código 123. Motivo. Estoque nos seus centros:4 PC no centro 9999.",
            404,
        ),
        (
            "ASSISTANT",
            (
                "Esse item já existe: use o código 123. Motivo. "
                "Estoque nos seus centros: 4 PC no centro 9999 no centro 1200."
            ),
            404,
        ),
        ("ASSISTANT", "Produto para o centro 9999; confirme os dados de uso.", 200),
        ("USER", "Esse item já existe: use o código 123. Motivo. Estoque nos seus centros: 4 PC no centro 9999.", 200),
    ],
)
def test_legacy_history_scope_uses_only_unambiguous_assistant_stock(client, factory, author, content, status):
    from sqlalchemy import select

    from vx_materials_api.db.models import ChatMessage, ChatSession

    first = send(client).json()
    with factory() as db:
        session = db.get(ChatSession, first["session_id"])
        session.context = {key: value for key, value in session.context.items() if key != "history_center_codes"}
        message = db.scalar(
            select(ChatMessage).where(ChatMessage.session_id == session.id, ChatMessage.author_type == author)
        )
        message.content = content
        db.commit()
    assert client.get(f"/api/v1/chat/sessions/{first['session_id']}").status_code == status
    visible = client.get("/api/v1/chat/sessions").json()["items"]
    assert len(visible) == (1 if status == 200 else 0)


@pytest.mark.parametrize("changed_source", ["material", "inventory"])
def test_catalog_changed_during_agent_call_does_not_stamp_or_persist_a_stale_proof(
    client, factory, identity, agent, monkeypatch, changed_source
):
    from vx_materials_api.db.models import ChatSession

    original = chat_service.complete_turn
    changed = False

    def concurrent(db, principal, request, reservation, result, request_id, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            with factory() as writer:
                statement = (
                    "INSERT INTO datasets(tenant_id) VALUES(:t)"
                    if changed_source == "inventory"
                    else "INSERT INTO materials_master (tenant_id, source_system, material_code, status) "
                    "VALUES (:t, 'TEST', 'catalog-change', 'ATIVO')"
                )
                writer.execute(text(statement), {"t": identity.tenant_id})
                writer.commit()
        return original(db, principal, request, reservation, result, request_id, **kwargs)

    monkeypatch.setattr(chat_service, "complete_turn", concurrent)
    agent.result = agent_result(VALID_CARD, search_call())
    response = send(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CATALOG_CHANGED"
    with factory() as db:
        session = db.scalar(select(ChatSession).where(ChatSession.tenant_id == identity.tenant_id))
        assert session.version == 0 and session.active_turn_id is None
        assert not session.context.get("duplicate_check")
        assert db.scalar(text("SELECT count(*) FROM chat_messages WHERE session_id=:id"), {"id": session.id}) == 0
    # A reserva foi liberada; nova tentativa inicia uma busca em vez de reutilizar o retorno recusado.
    retried = send(client, session_id=session.id, version=0)
    assert retried.status_code == 200


def test_a_foreign_tenant_change_does_not_invalidate_a_saved_proof(client, factory, agent):
    first = _offer(client, agent)
    with factory() as writer:
        writer.execute(
            text(
                "INSERT INTO materials_master (tenant_id, source_system, material_code, status) "
                "VALUES (:t, 'TEST', 'foreign-change', 'ATIVO')"
            ),
            {"t": uuid.uuid4()},
        )
        writer.commit()
    agent.result = agent_result(VALID_CARD, patch={"dismissed_material_codes": ["777"]})
    second = send(client, "Nenhum", first["session_id"], version=1, action={"type": "DISMISS_CANDIDATES"})
    assert second.status_code == 200 and second.json()["status"] == "READY_TO_SUBMIT"
    assert agent.payload()["context"]["duplicate_check"] is not None


@pytest.mark.parametrize("action_type", ["PICK_CANDIDATE", "DISMISS_CANDIDATES"])
def test_stale_action_can_retry_after_agent_failure_without_consuming_old_candidates(
    client, factory, identity, agent, action_type
):
    first = _offer(client, agent)
    with factory() as writer:
        writer.execute(
            text(
                "INSERT INTO materials_master (tenant_id, source_system, material_code, status) "
                "VALUES (:t, 'TEST', 'new-content', 'ATIVO')"
            ),
            {"t": identity.tenant_id},
        )
        writer.commit()
    action = {"type": action_type}
    if action_type == "PICK_CANDIDATE":
        action["material_code"] = "777"
    agent.status = 503
    unavailable = send(client, "Ação do botão", first["session_id"], version=1, action=action)
    assert unavailable.status_code == 503
    agent.status = 200
    agent.result = agent_result(
        VALID_CARD,
        search_call(similar("777")),
        patch={"dismissed_material_codes": ["777"], "offered_material_codes": ["777"]},
    )
    refreshed = send(client, "Ação do botão", first["session_id"], version=1, action=action)
    assert refreshed.status_code == 200 and refreshed.json()["status"] == "NEEDS_INPUT"
    assert agent.payload()["context"]["duplicate_check"] is None
    assert agent.payload()["context"]["offered_material_codes"] == []
    assert agent.payload()["context"]["dismissed_material_codes"] == []
    if action_type == "PICK_CANDIDATE":
        picked = {**CARD, "duplicate_check_status": "MATCH_FOUND", "existing": {**EXISTING, "material_code": "777"}}
        agent.result = agent_result(picked, search_call(similar("777")))
    else:
        agent.result = agent_result(VALID_CARD, patch={"dismissed_material_codes": ["777"]})
    accepted = send(client, "Confirmar oferta nova", first["session_id"], version=2, action=action)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == ("EXISTING" if action_type == "PICK_CANDIDATE" else "READY_TO_SUBMIT")


def test_legacy_saved_check_without_catalog_proof_is_revalidated_once(client, factory, agent):
    from vx_materials_api.db.models import ChatSession

    first = _offer(client, agent)
    with factory() as db:
        session = db.get(ChatSession, uuid.UUID(first["session_id"]))
        context = dict(session.context)
        context["duplicate_check"] = {
            key: value for key, value in context["duplicate_check"].items() if key != "catalog_proof"
        }
        session.context = context
        db.commit()
    agent.result = agent_result(VALID_CARD, search_call(similar("777")), patch={"offered_material_codes": ["777"]})
    second = send(client, "Nova verificação", first["session_id"], version=1)
    assert second.status_code == 200
    assert agent.payload()["context"]["duplicate_check"] is None
    agent.result = agent_result(VALID_CARD, patch={"dismissed_material_codes": ["777"]})
    third = send(client, "Nenhum", first["session_id"], version=2, action={"type": "DISMISS_CANDIDATES"})
    assert third.status_code == 200 and third.json()["status"] == "READY_TO_SUBMIT"
    assert agent.payload()["context"]["duplicate_check"] is not None
    assert "catalog_proof" not in agent.payload()["context"]["duplicate_check"]


def test_agent_cannot_renew_an_old_proof_without_search_after_catalog_change(client, factory, identity, agent):
    from vx_materials_api.db.models import ChatSession

    first = _offer(client, agent)
    with factory() as writer:
        writer.execute(
            text(
                "INSERT INTO materials_master (tenant_id, source_system, material_code, status) "
                "VALUES (:t, 'TEST', 'unverified-new', 'ATIVO')"
            ),
            {"t": identity.tenant_id},
        )
        writer.commit()
    agent.result = agent_result(VALID_CARD)
    second = send(client, "preciso de 20 unidades", first["session_id"], version=1)
    assert second.status_code == 200 and second.json()["status"] == "NEEDS_INPUT"
    assert second.json()["material_card"]["duplicate_check_status"] == "PENDING"
    with factory() as db:
        saved = db.get(ChatSession, uuid.UUID(first["session_id"])).context.get("duplicate_check")
        assert saved is None


def test_inventory_observation_invalidates_cache_without_master_change(client, factory, identity, agent):
    first = _offer(client, agent)
    with factory() as writer:
        writer.execute(text("INSERT INTO datasets(tenant_id) VALUES(:t)"), {"t": identity.tenant_id})
        writer.commit()
    agent.result = agent_result(VALID_CARD, search_call(similar("777")), patch={"offered_material_codes": ["777"]})
    refreshed = send(client, "Verificar estoque", first["session_id"], version=1)
    assert refreshed.status_code == 200
    assert agent.payload()["context"]["duplicate_check"] is None
    agent.result = agent_result(VALID_CARD, patch={"dismissed_material_codes": ["777"]})
    unchanged = send(client, "Nenhum", first["session_id"], version=2, action={"type": "DISMISS_CANDIDATES"})
    assert unchanged.status_code == 200 and unchanged.json()["status"] == "READY_TO_SUBMIT"
    assert agent.payload()["context"]["duplicate_check"] is not None


def test_inventory_proof_is_tenant_scoped_and_uses_deterministic_latest_dataset(factory, identity):
    with factory() as db:
        before = chat_service._catalog_proof(db, identity.tenant_id, "rules")
        db.execute(text("INSERT INTO datasets(tenant_id) VALUES(:t)"), {"t": uuid.uuid4()})
        assert chat_service._catalog_proof(db, identity.tenant_id, "rules") == before
        for suffix in (2, 1):
            db.execute(
                text("INSERT INTO datasets(id,tenant_id,imported_at) VALUES(:id,:t,'2099-01-01')"),
                {"id": uuid.UUID(int=suffix), "t": identity.tenant_id},
            )
        proof = chat_service._catalog_proof(db, identity.tenant_id, "rules")
        assert proof["inventory_dataset"] == str(uuid.UUID(int=2))
        db.execute(
            text("INSERT INTO datasets(tenant_id,imported_at) VALUES(:t,'2098-01-01')"), {"t": identity.tenant_id}
        )
        assert chat_service._catalog_proof(db, identity.tenant_id, "rules") == proof


def _client_for(factory, agent, monkeypatch, caller):
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", SECRET)
    app = create_app(
        session_factory=factory,
        identity_provider=lambda db: caller,
        agent_client=AgentClient("http://agent", transport=httpx.MockTransport(agent)),
    )
    return TestClient(app)


def test_dev_ti_sees_mcp_calls_in_turn_and_saved_conversation(factory, agent, monkeypatch):
    dev = _new_identity(factory, DEV_TI, ("ROLE_DEV_TI",))
    client = _client_for(factory, agent, monkeypatch, dev)

    first = send(client).json()
    assert first["tool_calls"] == AGENT_RESULT["tool_calls"]
    validator({"$ref": "#/components/schemas/ChatTurnResponse"}).validate(first)
    restored = client.get(f"/api/v1/chat/sessions/{first['session_id']}").json()
    assert restored["calls"] == [{"turn": 1, "call": call} for call in AGENT_RESULT["tool_calls"]]


@pytest.mark.parametrize(
    ("permissions", "roles"),
    [
        (SOLICITANTE, ("ROLE_SOLICITANTE",)),
        # Permissão sem a role que a concede não vale: a matriz do servidor é a autoridade.
        (DEV_TI, ("ROLE_SOLICITANTE",)),
        (SOLICITANTE, ("ROLE_DEV_TI",)),
    ],
)
def test_direct_requests_without_diagnostics_get_no_mcp_calls(factory, agent, monkeypatch, permissions, roles):
    caller = _new_identity(factory, permissions, roles)
    client = _client_for(factory, agent, monkeypatch, caller)

    turn = send(client).json()
    assert turn["tool_calls"] == []
    assert client.get(f"/api/v1/chat/sessions/{turn['session_id']}").json()["calls"] == []


def test_dev_ti_cannot_read_other_users_conversation(factory, agent, monkeypatch):
    owner = _new_identity(factory)
    turn = send(_client_for(factory, agent, monkeypatch, owner)).json()
    from dataclasses import replace

    dev = replace(_new_identity(factory, DEV_TI, ("ROLE_DEV_TI",)), tenant_id=owner.tenant_id)
    response = _client_for(factory, agent, monkeypatch, dev).get(f"/api/v1/chat/sessions/{turn['session_id']}")
    assert response.status_code == 404
    assert "tool-call-001" not in response.text
