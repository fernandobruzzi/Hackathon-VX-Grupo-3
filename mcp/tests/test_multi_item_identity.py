"""O substantivo distingue identidades técnicas dentro da mesma classe PDM."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.chatbot.agent import ToolRecorder, run_turn
from vx_materials_mcp.chatbot.candidates import card_signature, needs_search
from vx_materials_mcp.chatbot.session_manager import build_turn_context
from vx_materials_mcp.repositories.search import get_search_repository
from vx_materials_mcp.repositories.search.hybrid_v1 import SearchQuery
from vx_materials_mcp.schemas.agent import AgentRunRequest, DuplicateCheckState
from vx_materials_mcp.tools import get_pdm_template, validate_and_format_pdm

ATTRIBUTES = {
    "DIAMETRO NOMINAL": "2POL",
    "CLASSE PRESSAO": "150#",
    "MATERIAL": "ACO CARBONO A234 WPB",
    "CONEXAO": "ROSCA NPT",
}
DESCRIPTION = "NIPLE 2POL 150# ACO CARBONO A234 WPB ROSCA NPT"


@pytest.fixture(scope="module")
def setup():
    pdm = load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
    key = validate_pdm(pdm, "PDM050", ATTRIBUTES, item_name="NIPLE").identity_key
    assert key
    row = {
        "id": "1",
        "material_code": "10001",
        "status": "ATIVO",
        "target_code": None,
        "target_status": None,
        "target_id": None,
        "original_description_long": DESCRIPTION,
        "pdm_description": None,
        "proposed_class_id": "PDM050",
        "extracted_attributes": ATTRIBUTES,
        "candidate_identity_key": key,
        "rank": 1.0,
    }
    catalog = SimpleNamespace(
        by_identity=lambda query, version: [row] if query == key else [], full_text=lambda *args: [row]
    )
    classifier, extractor = get_classification_repository(pdm), get_extraction_repository()
    search = get_search_repository(
        catalog=catalog, pdm_catalog=pdm, classifier=classifier, extractor=extractor, index_version="test", caller=None
    )
    return pdm, search, classifier, extractor


@pytest.mark.parametrize("explicit_class", [None, "PDM050"])
def test_identical_niple_is_verified_with_or_without_explicit_class(setup, explicit_class):
    result = setup[1].search(SearchQuery(DESCRIPTION, explicit_class, ATTRIBUTES))
    assert result["match_status"] == "EXISTING_FOUND"
    assert result["candidates"][0]["identity_verified"]


def test_different_noun_invalidates_the_saved_check():
    first = card_signature("PDM050", ATTRIBUTES, "NIPLE")
    changed = card_signature("PDM050", ATTRIBUTES, "COTOVELO 90 GRAUS")
    saved = DuplicateCheckState(signature=first, status="NO_MATCH")
    assert not needs_search(saved, first, None, "ok")
    assert needs_search(saved, changed, None, "COTOVELO 90 GRAUS")


class Tools:
    def __init__(self, pdm, search):
        self.pdm, self.search = pdm, search

    async def call_tool(self, name, arguments):
        if name == "get_pdm_template":
            return get_pdm_template.run(self.pdm, **arguments).model_dump()
        if name == "validate_and_format_pdm":
            return validate_and_format_pdm.run(self.pdm, **arguments).model_dump()
        return self.search.search(SearchQuery(**arguments))


def test_agent_cannot_dismiss_identical_niple_and_changes_noun_invalidate_cache(setup):
    pdm, search, classifier, extractor = setup

    def turn(message, history=(), previous=None):
        request = AgentRunRequest.model_validate(
            {
                "turn_id": uuid4(),
                "session_version": 0,
                "session_id": uuid4(),
                "message": message,
                "context": {
                    "pdm_version": pdm.version,
                    "ncm_version": "ncm-demo-v1",
                    "center_code": "1200",
                    "history": history,
                    "confirmed_attributes": ATTRIBUTES,
                    "duplicate_check": previous,
                },
            }
        )
        context = build_turn_context(request, pdm.classes, classifier, extractor)
        recorder = ToolRecorder(Tools(pdm, search))
        return asyncio.run(run_turn(request, context, recorder))

    first = turn(DESCRIPTION)
    assert first.material_card.duplicate_check_status == "MATCH_FOUND"
    assert not first.material_card.can_submit
    assert next(c for c in first.tool_calls if c.name == "search_similar_materials").input["item_name"] == "NIPLE"
    history = [{"id": uuid4(), "author": "user", "content": DESCRIPTION, "created_at": "2026-11-06T00:00:00Z"}]
    dismissed = turn("Nenhum desses é o meu item", history)
    assert dismissed.material_card.duplicate_check_status == "MATCH_FOUND"
    assert not dismissed.material_card.can_submit
    saved = {
        "signature": card_signature("PDM050", ATTRIBUTES, "NIPLE"),
        "status": "MATCH_FOUND",
        "existing": first.material_card.existing.model_dump(),
    }
    same = turn("preciso de 20 unidades", history, saved)
    assert not any(c.name == "search_similar_materials" for c in same.tool_calls)
    assert same.material_card.existing.material_code == "10001"
    previous = {"signature": card_signature("PDM050", ATTRIBUTES, "NIPLE"), "status": "NO_MATCH"}
    changed = turn("COTOVELO 90 GRAUS", history, previous)
    assert any(c.name == "search_similar_materials" for c in changed.tool_calls)
    assert changed.material_card.duplicate_check_status != "MATCH_FOUND"


def test_api_and_agent_sign_the_same_complete_identity():
    from vx_materials_api.services.chat_service import card_signature as api_signature

    card = SimpleNamespace(pdm_class_id="PDM050", attributes=ATTRIBUTES)
    assert api_signature(card, "NIPLE") == card_signature("PDM050", ATTRIBUTES, "NIPLE")
    assert api_signature(card, "NIPLE") != api_signature(card, "COTOVELO 90 GRAUS")
