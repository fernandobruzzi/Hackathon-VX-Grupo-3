"""Resumo legível sem alterar os saldos e identificadores estruturados."""

from copy import deepcopy

import pytest

from vx_materials_mcp.chatbot.candidates import existing_message
from vx_materials_mcp.schemas.agent import ExistingMatch


def match(inventory):
    return ExistingMatch(
        material_code="16031971",
        status="ATIVO",
        pdm_description="FILTRO",
        match_type="EXACT_IDENTITY",
        reason="Identidade confirmada.",
        inventory=inventory,
    )


@pytest.mark.parametrize(
    ("quantity", "unit", "name", "expected"),
    [
        ("1", "PC", "Centro Industrial", "1 peça no centro Centro Industrial"),
        ("10", "PC", "Centro Industrial", "10 peças no centro Centro Industrial"),
        ("0", "PC", "Outro Centro", "0 peças no centro Outro Centro"),
        ("1.000000", "PC", None, "1.000000 peça no centro 2100"),
        ("1.0000000000000000001", "PC", "", "1.0000000000000000001 peças no centro 2100"),
        ("2.50", "KG", "  ", "2.50 KG no centro 2100"),
        ("5", "CX", "Depósito", "5 CX no centro Depósito"),
        ("inválido", "PC", None, "inválido peças no centro 2100"),
    ],
)
def test_inventory_summary_preserves_original_data(quantity, unit, name, expected):
    existing = match([dict(center_code="2100", center_name=name, quantity=quantity, unit=unit)])
    original = deepcopy(existing.model_dump())
    assert existing_message(existing) == (
        "Esse item já existe: use o código 16031971. Identidade confirmada. Estoque nos seus centros: " + expected + "."
    )
    assert existing.model_dump() == original


def test_each_stock_balance_keeps_its_center_and_unit():
    existing = match(
        [
            dict(center_code="2100", center_name="Fábrica", quantity="1", unit="PC"),
            dict(center_code="2200", quantity="10", unit="PC"),
            dict(center_code="2300", center_name="Depósito", quantity="2.50", unit="KG"),
        ]
    )
    assert "1 peça no centro Fábrica, 10 peças no centro 2200, 2.50 KG no centro Depósito." in existing_message(
        existing
    )


def test_no_stock_keeps_explicit_empty_message():
    assert existing_message(match([])).endswith("Sem estoque nos seus centros.")
