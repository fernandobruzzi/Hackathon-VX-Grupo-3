"""Assinatura de reuso inclui o substantivo, mesmo com classe e dimensões iguais."""

import json

from vx_materials_api.schemas.chat import AgentRunResponse, MaterialCard
from vx_materials_api.services.chat_service import card_signature, effective_candidates


def card(name):
    return MaterialCard.model_validate(
        {
            "pdm_class_id": "PDM050",
            "pdm_class_name": name,
            "attributes": {"DIAMETRO NOMINAL": "1/2POL", "CLASSE PRESSAO": "6000#"},
            "pdm_description": None,
            "validation_status": "VALID",
            "missing_attributes": [],
            "ncm": {"suggested": None, "status": "PENDING_VALIDATION"},
            "duplicate_check_status": "NO_MATCH",
            "can_submit": False,
        }
    )


def result(material_card):
    return AgentRunResponse.model_validate(
        {
            "assistant_message": "Ficha",
            "material_card": material_card.model_dump(),
            "context_patch": {},
            "tool_calls": [],
        }
    )


def test_changed_noun_cannot_reuse_a_check_with_equal_class_and_attributes():
    previous, changed = card("NIPLE"), card("COTOVELO 90 GRAUS")
    saved = {"signature": card_signature(previous), "candidates": []}
    assert effective_candidates(result(changed), saved) == (None, False)


def test_legacy_signature_without_noun_requires_new_search():
    material_card = card("NIPLE")
    legacy = json.dumps(
        {"pdm_class_id": material_card.pdm_class_id, "attributes": material_card.attributes},
        sort_keys=True,
        ensure_ascii=False,
    )
    assert effective_candidates(result(material_card), {"signature": legacy, "candidates": []}) == (None, False)


def test_same_noun_and_attributes_can_reuse_a_current_check():
    material_card = card("NIPLE")
    assert effective_candidates(
        result(material_card), {"signature": card_signature(material_card), "candidates": []}
    ) == ([], True)


def test_changed_context_noun_cannot_hide_behind_an_unchanged_display_label():
    previous = card("NIPLE")
    current = result(previous)
    current.context_patch["item_name"] = "COTOVELO 90 GRAUS"
    assert effective_candidates(current, {"signature": card_signature(previous), "candidates": []}) == (None, False)
