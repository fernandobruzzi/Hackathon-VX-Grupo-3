"""Leitura independente dos campos: recuperar evidência sem ocultar contradições."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from domain.contracts import MaterialRecord
from domain.enrichment_rules import original_attributes, original_hash, original_item_name
from domain.pdm_loader import load_pdm
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.extraction.material_fields import extract_material_fields


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


def test_short_text_recovers_only_additional_supported_attributes(catalog):
    result = extract_material_fields(
        catalog.classes["PDM110"],
        "PLACA TRASEIRA METSO PN MM4504436",
        "APLICACAO: BOMBA POLPA; MODELO: MM400",
    )
    assert result.attributes["APLICACAO"].value == "BOMBA POLPA"
    assert result.attributes["MODELO EQUIPAMENTO"].value == "MM400"
    assert result.origins["APLICACAO"] == "short_description"
    assert result.origins["REFERENCIA FABRICANTE"] == "description"
    assert result.conflicts == {}


def test_structured_field_cannot_hide_a_different_document_reference(catalog):
    result = extract_material_fields(
        catalog.classes["PDM110"], "PLACA TRASEIRA METSO PN MM4504436", reference="MM4504437"
    )
    assert result.conflicts == {"REFERENCIA FABRICANTE": ["MM4504436", "MM4504437"]}
    assert "REFERENCIA FABRICANTE" not in result.attributes


def test_short_long_and_repeated_labeled_disagreements_remain_conflicts(catalog):
    result = extract_material_fields(
        catalog.classes["PDM001"],
        "PARAFUSO SEXTAVADO; BITOLA: M12; BITOLA: M16; MATERIAL: ACO CARBONO",
        "MATERIAL: ACO INOX 304",
    )
    assert result.conflicts["BITOLA"] == ["M12", "M16"]
    assert result.conflicts["MATERIAL"] == ["ACO CARBONO", "ACO INOX 304"]
    assert not {"BITOLA", "MATERIAL"} & result.attributes.keys()


def test_reference_spelling_and_manufacturer_punctuation_are_equivalent(catalog):
    result = extract_material_fields(
        catalog.classes["PDM110"],
        "PLACA TRASEIRA; FABRICANTE: METSO; PN: MM4504436",
        manufacturer="METSO",
        reference="MM-4504436",
    )
    assert result.conflicts == {}
    assert result.attributes["REFERENCIA FABRICANTE"].value == "MM4504436"


@pytest.mark.parametrize(
    "short",
    [
        "PLACA TRASEIRA MODELO MM400 PN MM450443612",
        "PLACA TRASEIRA PN MM4504436 MODELO MM400XX",
        "PLACA TRASEIRA PN 123 45678901234567890123",
    ],
)
def test_truncated_short_reference_is_not_evidence(catalog, short):
    short = short[:40].ljust(40)
    result = extract_material_fields(catalog.classes["PDM110"], "PLACA TRASEIRA", short)
    assert "REFERENCIA FABRICANTE" not in result.attributes
    assert "MODELO EQUIPAMENTO" not in result.attributes or result.attributes["MODELO EQUIPAMENTO"].value == "MM400"


def test_complete_measure_before_a_truncated_tail_survives(catalog):
    short = "PARAFUSO SEXTAVADO M12X50 MATERIAL: ACO CA"[:40]
    result = extract_material_fields(catalog.classes["PDM001"], "PARAFUSO SEXTAVADO", short)
    assert result.attributes["BITOLA"].value == "M12"
    assert result.attributes["COMPRIMENTO"].value == "50MM"
    assert "MATERIAL" not in result.attributes


def test_conflicting_observations_do_not_confirm_identity(catalog):
    record = MaterialRecord("1", "ATIVO", "PLACA TRASEIRA METSO PN MM4504436", short_description="PN MM4504437")
    found = analyze_material(record, catalog, get_classification_repository(catalog), get_extraction_repository())
    assert found.identity_key is None
    assert "OBSERVATION_CONFLICT:REFERENCIA FABRICANTE" in found.review_reasons


def test_original_validation_uses_the_same_short_evidence_and_hash(catalog):
    data = {
        "id": "test",
        "material_code": "1",
        "original_description_long": "PLACA TRASEIRA METSO PN MM4504436",
        "original_description_short": "APLICACAO: BOMBA POLPA",
        "attributes": {},
    }
    record = MaterialRecord("1", "ATIVO", data["original_description_long"], data["original_description_short"])
    analyzed = analyze_material(record, catalog, get_classification_repository(catalog), get_extraction_repository())
    assert original_attributes(catalog, "PDM110", data) == analyzed.attributes
    assert original_hash(data) != original_hash(data | {"original_description_short": "APLICACAO: BRITADOR CONICO"})
    assert original_item_name(catalog, "PDM110", data) == "PLACA TRASEIRA"
    assert original_hash(SimpleNamespace(id="test", material_code="1"))
    assert (
        original_item_name(
            catalog,
            "PDM110",
            data | {"original_description_long": "METSO PN MM4504436", "original_description_short": "PLACA TRASEIRA"},
        )
        == "PLACA TRASEIRA"
    )


def test_no_speculative_pilot_material_connection_or_finish(catalog):
    fitting = extract_material_fields(catalog.classes["PDM050"], "UNIAO 1POL MAT ACO CARBONO ROSCA")
    bolt = extract_material_fields(catalog.classes["PDM001"], "PARAFUSO SEXTAVADO M12X50 OXID")
    assert not {"MATERIAL", "CONEXAO"} & fitting.attributes.keys()
    assert "ACABAMENTO" not in bolt.attributes


def test_complete_manufacturer_before_truncated_tail_is_supported(catalog):
    result = extract_material_fields(
        catalog.classes["PDM110"], "PLACA TRASEIRA", "PLACA TRASEIRA METSO APLICACAO: BOMBA POLPA"[:40]
    )
    assert result.attributes["FABRICANTE"].value == "METSO"
    assert result.origins["FABRICANTE"] == "short_description"
