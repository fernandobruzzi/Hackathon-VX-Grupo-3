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
from vx_materials_mcp.chatbot.candidates import (
    DISMISS_MESSAGE,
    decide,
    is_dismissal,
    picked_code,
    verified_existing,
)
from vx_materials_mcp.security import caller_to_environment

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
def callers():
    return []


@pytest.fixture
def client(catalog, executed, callers):
    """Sem banco: a busca de duplicidade falha, como numa queda do catálogo."""

    @asynccontextmanager
    async def connect(caller):
        callers.append(caller)
        async with mcp_client.connect(PDM, caller=caller_to_environment(caller)) as real:
            yield SpyClient(real, executed)

    return TestClient(create_app(catalog, SECRET, connect))


@pytest.fixture
def db_client(catalog, executed, database):
    @asynccontextmanager
    async def connect(caller):
        async with mcp_client.connect(PDM, database["reader"], caller_to_environment(caller)) as real:
            yield SpyClient(real, executed)

    return TestClient(create_app(catalog, SECRET, connect))


def token(**overrides):
    now = int(time.time())
    claims = {
        "iss": "vx-api",
        "aud": "vx-agent",
        "sub": "user-1",
        "iat": now,
        "exp": now + 60,
        "permissions": ["chat:use", "inventory:read"],
        "center_codes": ["1100", "1200"],
    }
    return jwt.encode({**claims, **overrides}, SECRET, algorithm="HS256")


def run(client, message, history=(), confirmed=None, bearer=None, offered=(), dismissed=()):
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
            "offered_material_codes": list(offered),
            "dismissed_material_codes": list(dismissed),
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
    assert all(call["transport"] == "MCP_STDIO" for call in calls)
    # Sem banco, a busca falha e aparece como falha no painel, não some.
    assert [call["status"] for call in calls] == ["SUCCEEDED", "SUCCEEDED", "FAILED"]
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
    # A busca falhou (sem banco): a ficha completa não libera o envio.
    assert card["duplicate_check_status"] == "PENDING" and card["can_submit"] is False
    assert "Não consegui verificar" in second["assistant_message"]


def test_unknown_material_is_a_business_result(client, executed):
    response = run(client, "quero uma cadeira de escritório")

    assert response.status_code == 200
    assert response.json()["material_card"]["validation_status"] == "OUT_OF_SCOPE"
    assert [name for name, _ in executed] == ["search_similar_materials"]


def test_validated_identity_reaches_the_server_not_the_tools(client, callers, executed):
    run(client, BOLT)

    assert callers[0].user_id == "user-1"
    assert callers[0].center_codes == frozenset({"1100", "1200"})
    forbidden = {"user", "user_id", "role", "permissions", "center_codes", "tenant", "actor_id"}
    assert all(not forbidden & set(arguments) for _, arguments in executed)


def test_existing_item_is_shown_with_authorized_stock(db_client):
    body = run(db_client, "filtro Fleetguard LF 9009").json()

    card = body["material_card"]
    assert card["duplicate_check_status"] == "MATCH_FOUND"
    assert card["existing"]["material_code"] == "16031971"
    assert card["can_submit"] is False
    assert {row["center_code"] for row in card["existing"]["inventory"]} <= {"1100", "1200"}
    assert all(set(row) == {"center_code", "quantity", "unit"} for row in card["existing"]["inventory"])
    assert "16031971" in body["assistant_message"]


NEW_BOLT = "Parafuso sextavado M36x333, classe A4-70, aço inox 316, oxidado preto, DIN 931"


def _next(client, history, body, message):
    """Turno seguinte, com o contexto que a API persistiria."""
    patch = body["context_patch"]
    history = [*history, ("assistant", body["assistant_message"])]
    return run(
        client,
        message,
        history,
        patch.get("confirmed_attributes"),
        offered=patch["offered_material_codes"],
        dismissed=patch["dismissed_material_codes"],
    ).json()


def test_only_similar_items_ask_the_requester(db_client):
    body = run(db_client, NEW_BOLT).json()

    card = body["material_card"]
    assert card["validation_status"] == "VALID"
    assert card["duplicate_check_status"] == "PENDING" and card["can_submit"] is False
    assert card["similar_candidates"]
    assert all(item["status"] != "OBSOLETO" for item in card["similar_candidates"])
    offered = body["context_patch"]["offered_material_codes"]
    assert offered == [item["material_code"] for item in card["similar_candidates"]]
    assert all(code in body["assistant_message"] for code in offered)


def test_dismissing_the_similar_items_releases_submission(db_client):
    first = run(db_client, NEW_BOLT).json()

    second = _next(db_client, [("user", NEW_BOLT)], first, DISMISS_MESSAGE)

    card = second["material_card"]
    assert card["duplicate_check_status"] == "NO_MATCH" and card["can_submit"] is True
    assert card["similar_candidates"] == []
    assert set(second["context_patch"]["dismissed_material_codes"]) == set(
        first["context_patch"]["offered_material_codes"]
    )


def test_picking_a_similar_item_shows_it_as_existing(db_client):
    first = run(db_client, NEW_BOLT).json()
    chosen = first["material_card"]["similar_candidates"][0]

    second = _next(db_client, [("user", NEW_BOLT)], first, f"É o item {chosen['material_code']}")

    existing = second["material_card"]["existing"]
    assert existing["material_code"] == (chosen["active_code_target"] or chosen["material_code"])
    assert second["material_card"]["duplicate_check_status"] == "MATCH_FOUND"
    assert "Confirmado pelo solicitante" in existing["reason"]


def test_code_never_offered_is_not_accepted_as_a_pick(db_client):
    first = run(db_client, NEW_BOLT).json()

    second = _next(
        db_client,
        [("user", NEW_BOLT)],
        {**first, "context_patch": {**first["context_patch"], "offered_material_codes": []}},
        "É o item 99999999",
    )

    assert "existing" not in second["material_card"]
    assert second["material_card"]["duplicate_check_status"] == "PENDING"


@pytest.mark.parametrize(
    "text", [DISMISS_MESSAGE, "nenhum desses", "Não é nenhum desses.", "É outro item", "item diferente"]
)
def test_dismissal_variants(text):
    assert is_dismissal(text)


@pytest.mark.parametrize("text", ["nenhum desses tem rosca fina", "parafuso diferente", "8.8"])
def test_descriptions_are_not_dismissals(text):
    assert not is_dismissal(text)


@pytest.mark.parametrize(
    ("text", "code"), [("É o item 16031971", "16031971"), ("16031971", "16031971"), ("código 16031971.", "16031971")]
)
def test_pick_variants(text, code):
    assert picked_code(text) == code


def test_new_candidates_after_a_dismissal_are_asked_again():
    search = {"candidates": [_candidate("1", "ATIVO", verified=False), _candidate("2", "ATIVO", verified=False)]}

    decision = decide(search, "classe 10.9", offered_before=["1"], dismissed_before=["1"])

    assert decision.status == "PENDING"
    assert decision.offered == ["2"]


def _candidate(code, status, verified=True, target=None):
    return {
        "material_code": code,
        "status": status,
        "active_code_target": target,
        "description": f"ITEM {code}",
        "match_type": "EXACT_IDENTITY",
        "identity_verified": verified,
        "inventory": [{"center_code": "1200", "quantity": "3", "unit": "PC"}],
    }


@pytest.mark.parametrize(
    ("candidates", "code"),
    [
        ([_candidate("1", "ATIVO")], "1"),
        ([_candidate("2", "BLOQUEADO", target="9")], "9"),
        ([_candidate("3", "OBSOLETO"), _candidate("4", "ATIVO")], "4"),
        ([_candidate("5", "BLOQUEADO")], None),
        ([_candidate("6", "ATIVO", verified=False)], None),
    ],
)
def test_only_reusable_identity_matches_are_offered(candidates, code):
    existing = verified_existing({"candidates": candidates})

    assert (existing.material_code if existing else None) == code
    if existing:
        assert existing.status == "ATIVO"


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
    async def slow(caller):
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
