"""Pontuação de fim de frase e uma informação por linha, como chegam pedidos e mensagens (#121).

Os pedidos vêm do kit (02_pedidos_cadastro.csv), com os valores conferidos à mão no texto.
"""

from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm
from pipelines.import_orders import read_orders
from repositories.extraction.rule_based_v1 import RuleBasedV1ExtractionRepository

KIT = Path(__file__).parents[2] / "data" / "desafio01"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def orders():
    rows = read_orders((KIT / "02_pedidos_cadastro.csv").read_bytes())
    return {row.source_order_id: row for row in rows}


def values(catalog, class_id, text):
    result = RuleBasedV1ExtractionRepository().extract(catalog.classes[class_id], text)
    return {name: attribute.value for name, attribute in result.attributes.items()}


def order_text(order):
    return " ".join(part for part in (order.original_text, order.attachment_text) if part)


# Mesma frase do roteiro da demo, com a pontuação que um solicitante usaria.
BOLT = "parafuso sextavado M12 x 50 aco carbono zincado amarelo DIN 933"
BOLT_VALUES = {"MATERIAL": "ACO CARBONO", "ACABAMENTO": "ZINCADO AMARELO", "NORMA": "DIN 933"}


@pytest.mark.parametrize("ending", ["", ".", "!", "?", "...", ", urgente", ".\n\nObrigado"])
def test_value_at_the_end_of_a_sentence_is_recognized(catalog, ending):
    found = values(catalog, "PDM001", BOLT + ending)
    assert {name: found.get(name) for name in BOLT_VALUES} == BOLT_VALUES


def test_value_between_sentences_and_in_parentheses(catalog):
    found = values(catalog, "PDM001", "aco carbono. zincado amarelo. (DIN 933).")
    assert {name: found.get(name) for name in BOLT_VALUES} == BOLT_VALUES


def test_labeled_items_in_one_line_split_at_the_period(catalog):
    found = values(catalog, "PDM001", "Norma: DIN 933. Material: aco carbono. Classe: 8.8.")
    assert found == {"NORMA": "DIN 933", "MATERIAL": "ACO CARBONO", "CLASSE RESISTENCIA": "8.8"}


def test_retentor_request_written_as_sentences(catalog):
    text = "Diametro eixo: 120 mm. Diametro alojamento: 142 mm. Largura: 12mm. Tipo: basl. Material: fkm (viton)."
    assert values(catalog, "PDM032", text) == {
        "DIAMETRO EIXO": "120MM",
        "DIAMETRO ALOJAMENTO": "142MM",
        "LARGURA": "12MM",
        "TIPO": "BASL",
        "MATERIAL": "FKM (VITON)",
    }


def test_punctuation_left_over_is_not_unresolved_text(catalog):
    result = RuleBasedV1ExtractionRepository().extract(catalog.classes["PDM001"], "(DIN 933).")
    assert result.unresolved == ()


def test_labeled_value_keeps_what_was_written(catalog):
    result = RuleBasedV1ExtractionRepository().extract(catalog.classes["PDM001"], "Norma: DIN 933.")
    assert result.attributes["NORMA"].value == "DIN 933"
    assert result.attributes["NORMA"].original == "NORMA: DIN 933."


# Negativos: ponto seguido de letra ou número faz parte do valor.
@pytest.mark.parametrize(
    ("class_id", "text", "attribute", "expected"),
    [
        ("PDM001", "parafuso sextavado M12 x 50 classe 8.8", "CLASSE RESISTENCIA", "8.8"),
        ("PDM001", "parafuso sextavado norma ASME B18.2.1.", "NORMA", "ASME B18.2.1"),
        ("PDM001", "parafuso sextavado aco carbono DIN 931.1", "NORMA", None),
        ("PDM001", 'parafuso sextavado UNC 3/4" comprimento 1.1/2"', "COMPRIMENTO", "1.1/2POL"),
    ],
)
def test_period_inside_a_value_is_kept(catalog, class_id, text, attribute, expected):
    assert values(catalog, class_id, text).get(attribute) == expected


# Pedidos reais do kit: e-mail com marcadores e ficha técnica com um item por linha.
@pytest.mark.parametrize(
    ("order_id", "class_id", "expected"),
    [
        (
            "SC-202600298",
            "PDM071",
            {"TIPO": "BOTINA CADARCO", "TAMANHO": "44", "CA": "10759"},
        ),
        (
            "SC-202600002",
            "PDM032",
            {"DIAMETRO EIXO": "60MM", "DIAMETRO ALOJAMENTO": "80MM", "LARGURA": "15MM", "TIPO": "BA"},
        ),
        (
            "SC-202600333",
            "PDM021",
            {"DIAMETRO INTERNO": "35MM", "DIAMETRO EXTERNO": "72MM", "LARGURA": "23MM"},
        ),
        (
            "SC-202600352",
            "PDM062",
            {"POLOS": "3P", "CURVA": "B"},
        ),
    ],
)
def test_real_orders_with_one_item_per_line(catalog, orders, order_id, class_id, expected):
    found = values(catalog, class_id, order_text(orders[order_id]))
    assert {name: found.get(name) for name in expected} == expected


def test_length_is_not_taken_from_the_gauge_in_parentheses(catalog, orders):
    # SC-202600235: "Bitola: 5/16" (7,9 mm)" e "Comprimento: 1 1/4"". O comprimento é o escrito no rótulo.
    found = values(catalog, "PDM001", order_text(orders["SC-202600235"]))
    assert found["COMPRIMENTO"] == "1.1/4POL"
    # A bitola com o milímetro entre parênteses fica vazia: melhor vazio do que um palpite.
    assert found.get("BITOLA") in (None, "5/16POL")
