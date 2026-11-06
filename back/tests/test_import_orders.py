"""Análise dos pedidos do kit, com casos reais conferidos lendo o texto (#24)."""

from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm
from pipelines.import_orders import analyze_order, read_orders
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository

KIT = Path(__file__).parents[2] / "data" / "desafio01"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def orders():
    return {order.source_order_id: order for order in read_orders((KIT / "02_pedidos_cadastro.csv").read_bytes())}


def analyze(catalog, order):
    return analyze_order(order, catalog, get_classification_repository(catalog), get_extraction_repository())


def test_reads_all_orders_with_center_and_urgency(orders):
    assert len(orders) == 520
    first = orders["SC-202600001"]
    assert (first.center_code, first.urgency, first.attachment_text) == ("1300", "NORMAL", None)


def test_complete_reference_order_is_ready_with_identity(catalog, orders):
    # "bucha excentrico britador conico RAPTOR 450 flsmidth 1626003064 bronze tm23"
    result = analyze(catalog, orders["SC-202600001"])
    assert result.status == "READY_FOR_REVIEW"
    assert result.pdm_class_id == "PDM110"
    assert result.identity_key == "PDM110|FLSMIDTH|1626003064"
    assert result.missing_attributes == ()


def test_order_without_a_required_attribute_lists_it(catalog, orders):
    # "parafuso sextavado metrica fina 180 mm 8.8 aco carbono": falta a bitola (M..).
    result = analyze(catalog, orders["SC-202600011"])
    assert result.status == "INCOMPLETE"
    assert result.missing_attributes == ("BITOLA",)
    assert result.identity_key is None


def test_order_outside_the_pdm_is_out_of_scope(catalog, orders):
    # "Cadeira de escritório giratória com braço"
    result = analyze(catalog, orders["SC-202600021"])
    assert result.status == "OUT_OF_SCOPE" and result.pdm_class_id is None


def test_attachment_text_is_part_of_the_order(catalog, orders):
    # O texto só diz "Segue ficha técnica em anexo."; a classe vem da ficha.
    order = orders["SC-202600002"]
    assert order.attachment_text
    assert analyze(catalog, order).pdm_class_id == "PDM032"
