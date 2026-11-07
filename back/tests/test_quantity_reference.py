"""Quantidades solicitadas não são códigos de peça, inclusive em classes de referência."""

from pathlib import Path

import pytest

from domain.identity import build_identity_key
from domain.pdm_loader import load_pdm
from repositories.extraction.rule_based_v1 import RuleBasedV1ExtractionRepository

KIT = Path(__file__).parents[2] / "data/desafio01"


@pytest.fixture(scope="module")
def pdm_class():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx").classes["PDM110"]


@pytest.mark.parametrize(
    "text",
    [
        "preciso de 20 unidades",
        "Caterpillar preciso de 20 unidades",
        "quero 2000 peças",
        "solicito 2000",
        "quantidade: 2000",
        "QTD 2000 UN",
        "2000 unidades",
        "20UN",
        "preciso de 2.000 unidades",
    ],
)
def test_quantity_never_supplies_a_manufacturer_reference(pdm_class, text):
    result = RuleBasedV1ExtractionRepository().extract(pdm_class, text)
    assert "REFERENCIA FABRICANTE" not in result.attributes


@pytest.mark.parametrize(
    "text,reference",
    [
        ("Caterpillar REF 123-4567", "123-4567"),
        ("Caterpillar preciso de 20 unidades REF 123-4567", "123-4567"),
        ("Caterpillar REF: 000020", "000020"),
        ("Caterpillar PN 2000", "2000"),
        ("Caterpillar 123456", "123456"),
        ("Caterpillar DE20", "DE20"),
    ],
)
def test_legitimate_references_keep_their_value_and_evidence(pdm_class, text, reference):
    result = RuleBasedV1ExtractionRepository().extract(pdm_class, text)
    found = result.attributes["REFERENCIA FABRICANTE"]
    assert found.value == reference
    assert found.original and found.rule


def test_structured_reference_is_preserved_despite_a_quantity_in_the_description(pdm_class):
    result = RuleBasedV1ExtractionRepository().extract(
        pdm_class,
        "Caterpillar preciso de 20 unidades",
        manufacturer_reference="000020",
    )
    assert result.attributes["REFERENCIA FABRICANTE"].value == "000020"
    assert result.attributes["REFERENCIA FABRICANTE"].rule == "field.manufacturer_reference"


def test_quantity_filter_never_selects_between_other_ambiguous_codes(pdm_class):
    result = RuleBasedV1ExtractionRepository().extract(
        pdm_class,
        "Caterpillar AB123 CD456 preciso de 20 unidades",
    )
    assert "REFERENCIA FABRICANTE" not in result.attributes


def test_discarding_quantity_does_not_authorize_another_unlabeled_code(pdm_class):
    result = RuleBasedV1ExtractionRepository().extract(pdm_class, "Caterpillar AB123 preciso de 20 unidades")
    assert "REFERENCIA FABRICANTE" not in result.attributes


def test_quantity_cannot_complete_the_manufacturer_reference_identity(pdm_class):
    result = RuleBasedV1ExtractionRepository().extract(pdm_class, "Caterpillar preciso de 20 unidades")
    attributes = {
        "APLICACAO": "CAMINHAO FORA DE ESTRADA",
        "MODELO EQUIPAMENTO": "793F",
        **{name: value.value for name, value in result.attributes.items()},
    }
    assert build_identity_key(pdm_class, "CARCACA", attributes) is None
    assert build_identity_key(pdm_class, "CARCACA", {**attributes, "REFERENCIA FABRICANTE": "123-4567"}) is not None


def test_equipment_model_is_not_a_reference_after_asking_for_quantity(pdm_class):
    result = RuleBasedV1ExtractionRepository().extract(
        pdm_class,
        "Caterpillar MODELO EQUIPAMENTO: 793F; preciso de 20 unidades",
    )
    assert result.attributes["MODELO EQUIPAMENTO"].value == "793F"
    assert "REFERENCIA FABRICANTE" not in result.attributes
