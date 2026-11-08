"""Bedrock simulado no transporte; validação e ferramentas do cadastro continuam reais."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy

import botocore.session
import pytest
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters
from fastapi.testclient import TestClient
from test_conversation_flow import BOLT, PDM, SECRET, run, token
from test_search_identity_safety import search as search_index

from domain.pdm_loader import load_pdm
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.app import create_app
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.chatbot.bedrock import BedrockError, BedrockPlanner
from vx_materials_mcp.chatbot.session_manager import build_turn_context
from vx_materials_mcp.schemas.agent import AgentRunRequest, AgentRunResponse, HistoryMessage
from vx_materials_mcp.security import caller_to_environment

MODEL = "us.anthropic.claude-sonnet-5"


class FakeBedrock:
    def __init__(self, interpretation=None, error=None):
        self.calls = []
        self.interpretation = interpretation or {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [],
        }
        self.error = error

    def converse(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if self.error:
            raise self.error
        if "toolConfig" in kwargs:
            return {
                "stopReason": "tool_use",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "interpretation-1",
                                    "name": "interpret_material_request",
                                    "input": self.interpretation,
                                }
                            }
                        ],
                    }
                },
            }
        return {
            "stopReason": "end_turn",
            "output": {
                "message": {"role": "assistant", "content": [{"text": "Qual é a classe de resistência do parafuso?"}]}
            },
        }


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(PDM)


def request(message=BOLT):
    return AgentRunRequest.model_validate(
        {
            "turn_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000002",
            "session_version": 0,
            "message": message,
            "context": {
                "pdm_version": "pdm-kit-v1",
                "ncm_version": "ncm-demo-v1",
                "center_code": "1200",
                "history": [],
                "confirmed_attributes": {},
            },
        }
    )


def interpret(catalog, sdk, payload):
    context = build_turn_context(
        payload, catalog.classes, get_classification_repository(catalog), get_extraction_repository()
    )
    return asyncio.run(BedrockPlanner(MODEL, sdk).interpret(payload, context, catalog))


def test_interprets_literal_value_and_uses_versioned_system_prompt(catalog):
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [{"name": "CLASSE RESISTENCIA", "value": "8.8", "source": "resistência é 8.8"}],
        }
    )
    context = interpret(catalog, sdk, request(BOLT + " A classe de resistência é 8.8."))
    assert context.attributes["CLASSE RESISTENCIA"] == "8.8"
    assert sdk.calls[0]["modelId"] == MODEL
    assert "material_registration_system_v2" in sdk.calls[0]["system"][0]["text"]
    assert "Governança" in sdk.calls[0]["system"][0]["text"]


@pytest.mark.parametrize(
    "patch",
    [
        {"pdm_class_id": "PDM999"},
        {"item_name": "VALVULA INVENTADA"},
        {"can_submit": True},
        {"attributes": [{"name": "CLASSE RESISTENCIA", "value": "12.9", "source": "zincado branco"}]},
        {"attributes": [{"name": "CLASSE RESISTENCIA", "value": "8.8", "source": "resistência 8.8"}]},
        {"attributes": [{"name": "INVENTADO", "value": "M12", "source": "M12"}]},
    ],
)
def test_rejects_unknown_or_unsupported_model_claims(catalog, patch):
    data = {"pdm_class_id": "PDM001", "item_name": "PARAFUSO SEXTAVADO", "attributes": []}
    with pytest.raises(BedrockError):
        interpret(catalog, FakeBedrock(data | patch), request())


def test_uses_history_and_preserves_confirmed_values(catalog):
    payload = request("O acabamento é zincado branco.")
    payload.context.history = [
        HistoryMessage.model_validate(
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "author": "user",
                "content": BOLT,
                "created_at": "2026-11-07T12:00:00Z",
            }
        )
    ]
    payload.context.confirmed_attributes = {"CLASSE RESISTENCIA": "8.8"}
    payload.context.pdm_class_id = "PDM001"
    payload.context.item_name = "PARAFUSO SEXTAVADO"
    sdk = FakeBedrock()
    context = interpret(catalog, sdk, payload)
    assert context.attributes["CLASSE RESISTENCIA"] == "8.8"
    assert BOLT in json.dumps(sdk.calls[0], ensure_ascii=False)


def test_switching_class_drops_previous_attributes(catalog):
    payload = request("Agora preciso de uma porca sextavada M12.")
    payload.context.confirmed_attributes = {"COMPRIMENTO": "50"}
    target = catalog.classes["PDM003"]
    context = interpret(
        catalog, FakeBedrock({"pdm_class_id": target.id, "item_name": "PORCA", "attributes": []}), payload
    )
    assert context.pdm_class.id == target.id
    assert "COMPRIMENTO" not in context.attributes


def client_for(catalog, sdk):
    @asynccontextmanager
    async def connect(caller):
        async with mcp_client.connect(PDM, caller=caller_to_environment(caller)) as client:
            yield client

    return TestClient(create_app(catalog, SECRET, connect, bedrock_client=sdk))


def test_endpoint_calls_sonnet_twice_and_preserves_real_mcp_validation(catalog, monkeypatch):
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", MODEL)
    sdk = FakeBedrock()
    response = run(client_for(catalog, sdk), BOLT)
    assert response.status_code == 200
    data = response.json()
    assert len(sdk.calls) == 2
    assert data["assistant_message"] == "Qual é a classe de resistência do parafuso?"
    assert data["material_card"]["can_submit"] is False
    assert "CLASSE RESISTENCIA" in data["material_card"]["missing_attributes"]
    assert any(c["name"] == "validate_and_format_pdm" for c in data["tool_calls"])
    assert data["context_patch"]["planner"] == "bedrock_sonnet_5_v1"
    assert "material_card" in sdk.calls[1]["messages"][-1]["content"][0]["text"]
    schema = botocore.session.get_session().get_service_model("bedrock-runtime").operation_model("Converse")
    for call in sdk.calls:
        validate_parameters(call, schema.input_shape)


def test_bedrock_failure_returns_sanitized_error_without_fallback(catalog, monkeypatch):
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", MODEL)
    sdk = FakeBedrock(
        error=ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "secret internal details"}}, "Converse"
        )
    )
    response = run(client_for(catalog, sdk), BOLT)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BEDROCK_UNAVAILABLE"
    assert "secret" not in response.text
    assert len(sdk.calls) == 1


def test_without_configuration_keeps_local_rules(catalog, monkeypatch):
    monkeypatch.delenv("BEDROCK_CHAT_MODEL_ID", raising=False)
    sdk = FakeBedrock()
    response = run(client_for(catalog, sdk), BOLT)
    assert response.status_code == 200
    assert response.json()["context_patch"]["planner"] == "rule_based_v1"
    assert not sdk.calls


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"stopReason": "max_tokens"},
        {"stopReason": "tool_use", "output": {"message": {"content": []}}},
        {
            "stopReason": "tool_use",
            "output": {"message": {"content": [{"toolUse": {"name": "delete_material", "input": {}}}]}},
        },
    ],
)
def test_rejects_malformed_or_truncated_interpretation(catalog, response):
    sdk = FakeBedrock()
    sdk.converse = lambda **kwargs: response
    with pytest.raises(BedrockError):
        interpret(catalog, sdk, request())


def test_assistant_history_is_not_attribute_evidence(catalog):
    payload = request()
    payload.context.history = [
        HistoryMessage.model_validate(
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "author": "assistant",
                "content": "Exemplo: classe de resistência 8.8.",
                "created_at": "2026-11-07T12:00:00Z",
            }
        )
    ]
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [{"name": "CLASSE RESISTENCIA", "value": "8.8", "source": "resistência 8.8"}],
        }
    )
    with pytest.raises(BedrockError):
        interpret(catalog, sdk, payload)


def test_explicit_correction_replaces_previous_value(catalog):
    payload = request(BOLT + " Corrigindo, classe de resistência 10.9.")
    payload.context.confirmed_attributes = {"CLASSE RESISTENCIA": "8.8"}
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [{"name": "CLASSE RESISTENCIA", "value": "10.9", "source": "resistência 10.9"}],
        }
    )
    assert interpret(catalog, sdk, payload).attributes["CLASSE RESISTENCIA"] == "10.9"


def test_buttons_preserve_llm_only_classification(catalog, monkeypatch):
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", MODEL)
    sdk = FakeBedrock()
    description = "Preciso de um fixador com cabeça de seis lados M12x50."
    response = run(
        client_for(catalog, sdk),
        "Nenhum desses é o meu item",
        history=[("user", description)],
        action={"type": "DISMISS_CANDIDATES"},
    )
    assert response.status_code == 200
    assert response.json()["material_card"]["pdm_class_id"] == "PDM001"
    assert len(sdk.calls) == 2
    assert "Nenhum desses é o meu item" not in sdk.calls[0]["messages"][0]["content"][0]["text"]


def test_followup_accepts_historical_value_already_normalized_by_rules(catalog):
    payload = request("A classe de resistência é 8.8.")
    payload.context.history = [
        HistoryMessage.model_validate(
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "author": "user",
                "content": BOLT,
                "created_at": "2026-11-07T12:00:00Z",
            }
        )
    ]
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [
                {"name": "ACABAMENTO", "value": "zincado branco", "source": "zincado branco"},
                {"name": "CLASSE RESISTENCIA", "value": "8.8", "source": "resistência é 8.8"},
            ],
        }
    )
    context = interpret(catalog, sdk, payload)
    assert context.attributes["ACABAMENTO"] == "zincado branco"
    assert context.attributes["CLASSE RESISTENCIA"] == "8.8"


@pytest.mark.parametrize(
    "final",
    [
        {},
        {"stopReason": "max_tokens", "output": {"message": {"content": [{"text": "Ficha"}]}}},
        {"stopReason": "end_turn", "output": {"message": {"content": [{"text": " "}]}}},
        {"stopReason": "guardrail_intervened", "output": {"message": {"content": []}}},
    ],
)
def test_invalid_final_answer_does_not_return_partial_success(catalog, monkeypatch, final):
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", MODEL)
    sdk = FakeBedrock()
    original = sdk.converse
    sdk.converse = lambda **kwargs: original(**kwargs) if "toolConfig" in kwargs else final
    response = run(client_for(catalog, sdk), BOLT)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BEDROCK_INVALID_RESPONSE"
    assert "material_card" not in response.json()


def test_sdk_uses_region_bounded_timeouts_and_closes_client(catalog, monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setenv("AWS_REGION", "us-east-1")
    sdk = FakeBedrock()
    sdk.close = Mock()
    factory = Mock(return_value=sdk)
    monkeypatch.setattr("vx_materials_mcp.chatbot.bedrock.boto3.session.Session", lambda: Mock(client=factory))
    payload = request()
    context = build_turn_context(
        payload, catalog.classes, get_classification_repository(catalog), get_extraction_repository()
    )
    asyncio.run(BedrockPlanner(MODEL).interpret(payload, context, catalog))
    assert factory.call_args.args == ("bedrock-runtime",)
    assert factory.call_args.kwargs["region_name"] == "us-east-1"
    config = factory.call_args.kwargs["config"]
    assert (config.connect_timeout, config.read_timeout) == (2, 8)
    assert config.retries == {"total_max_attempts": 1}
    sdk.close.assert_called_once()


def previous_state(payload, message=BOLT, class_id="PDM001", item_name="PARAFUSO SEXTAVADO", attributes=None):
    payload.context.history = [
        HistoryMessage.model_validate(
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "author": "user",
                "content": message,
                "created_at": "2026-11-07T12:00:00Z",
            }
        )
    ]
    payload.context = payload.context.model_copy(
        update={
            "pdm_class_id": class_id,
            "item_name": item_name,
            "confirmed_attributes": attributes or {},
        }
    )
    return payload


def test_class_change_drops_shared_attributes_of_previous_material(catalog):
    payload = previous_state(
        request("Agora preciso de uma porca sextavada M16."),
        attributes={
            "BITOLA": "M12",
            "MATERIAL": "ACO CARBONO",
            "ACABAMENTO": "ZINCADO BRANCO",
            "NORMA": "DIN 933",
        },
    )
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM003",
            "item_name": "PORCA",
            "attributes": [
                {"name": "BITOLA", "value": "M16", "source": "M16"},
            ],
        }
    )
    context = interpret(catalog, sdk, payload)
    assert context.pdm_class.id == "PDM003"
    assert context.attributes["BITOLA"] == "M16"
    assert not {"MATERIAL", "ACABAMENTO", "NORMA"} & context.attributes.keys()


def test_item_change_in_same_class_does_not_reuse_manufacturer(catalog):
    payload = previous_state(
        request("Agora preciso de um filtro combustível."),
        message="Preciso de um filtro ar Donaldson.",
        class_id="PDM100",
        item_name="FILTRO AR",
        attributes={"FABRICANTE": "DONALDSON"},
    )
    sdk = FakeBedrock({"pdm_class_id": "PDM100", "item_name": "FILTRO COMBUSTIVEL", "attributes": []})
    assert "FABRICANTE" not in interpret(catalog, sdk, payload).attributes


def test_same_material_keeps_confirmed_attributes_and_explicit_clears(catalog):
    payload = previous_state(
        request("A classe de resistência é 8.8."),
        attributes={
            "BITOLA": "M12",
            "MATERIAL": "ACO CARBONO",
            "ACABAMENTO": None,
        },
    )
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [
                {"name": "CLASSE RESISTENCIA", "value": "8.8", "source": "resistência é 8.8"},
            ],
        }
    )
    attributes = interpret(catalog, sdk, payload).attributes
    assert attributes["BITOLA"] == "M12"
    assert attributes["MATERIAL"] == "ACO CARBONO"
    assert attributes["ACABAMENTO"] is None
    assert attributes["CLASSE RESISTENCIA"] == "8.8"


def test_withdrawal_stays_cleared_on_next_http_turn(catalog, monkeypatch):
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", MODEL)
    withdrawal = "Não sei o acabamento, apague zincado branco."
    payload = previous_state(request(withdrawal), attributes={"ACABAMENTO": "ZINCADO BRANCO"})
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [
                {"name": "ACABAMENTO", "value": None, "source": withdrawal},
            ],
        }
    )
    headers = {"X-Request-ID": "withdrawal-test", "Authorization": f"Bearer {token()}"}
    first = client_for(catalog, sdk).post(
        "/internal/v1/chat/run", json=payload.model_dump(mode="json"), headers=headers
    )
    assert first.status_code == 200
    patch = first.json()["context_patch"]
    assert patch["confirmed_attributes"]["ACABAMENTO"] is None
    next_payload = previous_state(request("A classe de resistência é 8.8."), attributes=patch["confirmed_attributes"])
    next_payload.context.history.extend(
        [
            HistoryMessage.model_validate(
                {
                    "id": "00000000-0000-0000-0000-000000000004",
                    "author": "user",
                    "content": withdrawal,
                    "created_at": "2026-11-07T12:01:00Z",
                }
            )
        ]
    )
    sdk.interpretation["attributes"] = [{"name": "CLASSE RESISTENCIA", "value": "8.8", "source": "resistência é 8.8"}]
    second = client_for(catalog, sdk).post(
        "/internal/v1/chat/run", json=next_payload.model_dump(mode="json"), headers=headers
    )
    assert second.status_code == 200
    assert second.json()["material_card"]["attributes"]["ACABAMENTO"] is None
    assert second.json()["context_patch"]["confirmed_attributes"]["ACABAMENTO"] is None
    assert second.json()["material_card"]["can_submit"] is False
    search = next(call for call in second.json()["tool_calls"] if call["name"] == "search_similar_materials")
    assert "zincado branco" not in search["input"]["query"].lower()


def test_new_material_search_excludes_previous_material_facts(catalog, monkeypatch):
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", MODEL)
    payload = previous_state(
        request("Agora preciso de uma porca sextavada M16."),
        attributes={
            "BITOLA": "M12",
            "MATERIAL": "ACO CARBONO",
            "ACABAMENTO": "ZINCADO BRANCO",
            "NORMA": "DIN 933",
        },
    )
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM003",
            "item_name": "PORCA",
            "attributes": [
                {"name": "BITOLA", "value": "M16", "source": "M16"},
            ],
        }
    )
    response = client_for(catalog, sdk).post(
        "/internal/v1/chat/run",
        json=payload.model_dump(mode="json"),
        headers={"X-Request-ID": "new-material", "Authorization": f"Bearer {token()}"},
    )
    assert response.status_code == 200
    search = next(call for call in response.json()["tool_calls"] if call["name"] == "search_similar_materials")
    assert search["input"]["pdm_class_id"] == "PDM003"
    assert "M16" in search["input"]["query"]
    assert "parafuso" not in search["input"]["query"].lower()
    assert "DIN 933" not in search["input"]["query"]


def test_old_material_evidence_cannot_fill_new_material(catalog):
    payload = previous_state(request("Agora preciso de uma porca sextavada M16."))
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM003",
            "item_name": "PORCA",
            "attributes": [
                {"name": "ACABAMENTO", "value": "zincado branco", "source": "zincado branco"},
            ],
        }
    )
    with pytest.raises(BedrockError):
        interpret(catalog, sdk, payload)


def test_old_evidence_cannot_restore_explicitly_cleared_attribute(catalog):
    payload = previous_state(request("A classe de resistência é 8.8."), attributes={"ACABAMENTO": None})
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [
                {"name": "ACABAMENTO", "value": "zincado branco", "source": "zincado branco"},
            ],
        }
    )
    with pytest.raises(BedrockError):
        interpret(catalog, sdk, payload)


def test_current_confirmation_can_replace_explicit_clear(catalog):
    payload = previous_state(request("Confirmei o acabamento: zincado branco."), attributes={"ACABAMENTO": None})
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM001",
            "item_name": "PARAFUSO SEXTAVADO",
            "attributes": [
                {"name": "ACABAMENTO", "value": "zincado branco", "source": "zincado branco"},
            ],
        }
    )
    assert interpret(catalog, sdk, payload).attributes["ACABAMENTO"] == "zincado branco"


def test_uncertain_class_cannot_erase_accepted_state(catalog, monkeypatch):
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", MODEL)
    payload = previous_state(request("Não sei informar mais detalhes."), attributes={"ACABAMENTO": None})
    sdk = FakeBedrock({"pdm_class_id": None, "item_name": None, "attributes": []})
    headers = {"X-Request-ID": "uncertain-class", "Authorization": f"Bearer {token()}"}
    response = client_for(catalog, sdk).post(
        "/internal/v1/chat/run", json=payload.model_dump(mode="json"), headers=headers
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BEDROCK_INVALID_RESPONSE"
    assert "context_patch" not in response.json()
    # Um erro não completa o turno; a próxima chamada recebe o mesmo estado da API.
    payload.message = "A classe de resistência é 8.8."
    sdk.interpretation = {
        "pdm_class_id": "PDM001",
        "item_name": "PARAFUSO SEXTAVADO",
        "attributes": [
            {"name": "CLASSE RESISTENCIA", "value": "8.8", "source": "resistência é 8.8"},
        ],
    }
    next_turn = client_for(catalog, sdk).post(
        "/internal/v1/chat/run", json=payload.model_dump(mode="json"), headers=headers
    )
    assert next_turn.status_code == 200
    assert next_turn.json()["context_patch"]["confirmed_attributes"]["ACABAMENTO"] is None


@pytest.mark.parametrize("revision", ["REV A", "revisão B", "REVISION 2"])
def test_curated_bedrock_search_preserves_revision_review(catalog, revision):
    payload = request(f"MANTO METSO N1234567 {revision}")
    sdk = FakeBedrock(
        {
            "pdm_class_id": "PDM110",
            "item_name": "MANTO",
            "attributes": [
                {"name": "FABRICANTE", "value": "METSO", "source": "METSO"},
                {"name": "REFERENCIA FABRICANTE", "value": "N1234567", "source": "N1234567"},
            ],
        }
    )
    context = interpret(catalog, sdk, payload)
    result = search_index(
        catalog,
        "PDM110",
        context.search_text,
        context.attributes,
        manufacturer="METSO",
        reference="N1234567",
        description="MANTO METSO N1234567",
    )
    assert result["match_status"] == "REVIEW_REQUIRED"
    assert result["candidates"][0]["identity_verified"] is False
    assert "REVISAO_DE_PECA_NAO_CONFIRMADA" in result["candidates"][0]["pending_checks"]


def test_existing_stock_summary_is_preserved_with_bedrock(catalog, monkeypatch):
    from test_inventory_message import match

    monkeypatch.delenv("BEDROCK_CHAT_MODEL_ID", raising=False)
    data = run(client_for(catalog, FakeBedrock()), BOLT).json()
    data["material_card"]["existing"] = match(
        [
            dict(center_code="2100", center_name="Centro Industrial", quantity="10", unit="PC"),
            dict(center_code="2200", quantity="1", unit="PC"),
        ]
    ).model_dump()
    result = AgentRunResponse.model_validate(data)
    response = asyncio.run(BedrockPlanner(MODEL, FakeBedrock()).respond(request(), result))
    assert "10 peças no centro Centro Industrial, 1 peça no centro 2200." in response.assistant_message
    # O destino da conversa (1200) não tem saldo: a resposta aponta os outros centros autorizados.
    assert response.assistant_message.endswith(
        "O centro de destino 1200 não tem saldo; há saldo em outros centros autorizados a você: "
        "Centro Industrial, 2200. É só uma informação: nada é reservado nem transferido."
    )
    assert response.material_card == result.material_card
