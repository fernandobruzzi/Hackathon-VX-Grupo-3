"""Referências entregues ao modelo e citações realmente usadas são registradas separadamente."""

import asyncio
import json
from copy import deepcopy

import pytest

from vx_materials_mcp.chatbot.bedrock import BedrockError, BedrockPlanner
from vx_materials_mcp.schemas.agent import AgentRunRequest, AgentRunResponse


class Model:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def converse(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return {"stopReason": "end_turn", "output": {"message": {"content": [{"text": self.answer}]}}}


def inputs():
    packet = {
        "context_id": "a" * 64,
        "sources": [{"citation_id": "R1", "label": "PDM PDM001 (pdm-kit-v1)"}],
        "items": [{"citation_id": "R1", "content": {"attributes": ["MATERIAL"]}}],
    }
    request = AgentRunRequest.model_validate(
        {
            "turn_id": "00000000-0000-4000-8000-000000000001",
            "session_id": "00000000-0000-4000-8000-000000000002",
            "session_version": 0,
            "message": "Preciso de parafuso",
            "context": {
                "pdm_version": "pdm-kit-v1",
                "ncm_version": "ncm-demo-v1",
                "center_code": "1200",
                "history": [],
                "confirmed_attributes": {},
            },
        }
    )
    result = AgentRunResponse.model_validate(
        {
            "assistant_message": "Informe o material.",
            "context_patch": {},
            "tool_calls": [
                {
                    "id": "tool-call-001",
                    "name": "retrieve_material_context",
                    "input": {"query": "parafuso"},
                    "status": "SUCCEEDED",
                    "duration_ms": 1,
                    "result": {"context": packet, "used_citation_ids": []},
                }
            ],
            "material_card": {
                "pdm_class_id": "PDM001",
                "attributes": {},
                "pdm_description": None,
                "validation_status": "INCOMPLETE",
                "missing_attributes": ["MATERIAL"],
                "ncm": {"suggested": None, "status": "PENDING_VALIDATION"},
                "duplicate_check_status": "PENDING",
                "can_submit": False,
            },
        }
    )
    return packet, request, result


def test_model_receives_bounded_context_and_only_actual_citations_are_recorded():
    packet, request, result = inputs()
    model = Model("O PDM pede o material [R1]. Qual material você precisa?")
    response = asyncio.run(BedrockPlanner("model-test", model).respond(request, result, rag_context=packet))
    sent = json.loads(model.calls[0]["messages"][0]["content"][0]["text"])
    assert sent["reference_context"] == packet
    assert not any(call["name"] == "retrieve_material_context" for call in sent["tool_calls"])
    assert "[R1] PDM PDM001 (pdm-kit-v1)" in response.assistant_message
    assert response.context_patch["rag_citations_used"] == ["R1"]
    assert response.context_patch["system_prompt_version"] == "material_registration_system_v2"
    assert response.tool_calls[0].result["used_citation_ids"] == ["R1"]
    assert response.material_card == result.material_card and not response.material_card.can_submit


def test_unused_sources_are_not_claimed_as_used():
    packet, request, result = inputs()
    response = asyncio.run(
        BedrockPlanner("model-test", Model("Qual material você precisa?")).respond(request, result, rag_context=packet)
    )
    assert response.context_patch["rag_citations_used"] == []
    assert response.tool_calls[0].result["context"]["sources"] == packet["sources"]
    assert "Fontes:" not in response.assistant_message


@pytest.mark.parametrize("packet", [None, {"sources": [{"citation_id": "R1", "label": "PDM"}]}])
def test_unknown_citation_cannot_be_published(packet):
    _, request, result = inputs()
    with pytest.raises(BedrockError):
        asyncio.run(BedrockPlanner("model-test", Model("Afirmação [R99]")).respond(request, result, rag_context=packet))
