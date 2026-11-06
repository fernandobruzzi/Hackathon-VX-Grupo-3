"""Valores técnicos não ganham qualificações que o texto não informou (#133)."""

from dataclasses import replace
from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from pipelines.import_orders import OrderRow, analyze_order
from pipelines.ncm_corrections import propose_ncm_corrections
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository

KIT = Path(__file__).parents[2] / "data" / "desafio01"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


def test_real_cast_iron_body_stays_pending_without_nodular_evidence(catalog):
    record = next(record for record in read_csv_records(KIT / "01_base_materiais.csv") if record.code == "22825019")
    extractor = get_extraction_repository()
    result = extractor.extract(catalog.classes["PDM044"], record.description)

    assert "MATERIAL CORPO" not in result.attributes
    assert any("FERRO FUNDIDO" in piece for piece in result.unresolved)
    analyzed = analyze_material(record, catalog, get_classification_repository(catalog), extractor)
    assert analyzed.identity_key is None
    validation = validate_pdm(catalog, "PDM044", analyzed.attributes, item_name=analyzed.item_name)
    assert "MATERIAL CORPO" in {missing.name for missing in validation.missing_attributes}


@pytest.mark.parametrize(
    ("class_id", "text", "attribute"),
    [
        ("PDM044", "MATERIAL CORPO: FERRO FUNDIDO", "MATERIAL CORPO"),
        ("PDM044", "MATERIAL CORPO: FUNDIDO NODULAR", "MATERIAL CORPO"),
        ("PDM044", "MATERIAL DISCO: ACO FUNDIDO", "MATERIAL DISCO"),
        ("PDM050", "MATERIAL: FERRO GALVANIZADO", "MATERIAL"),
        ("PDM051", "MATERIAL: ACO CARBONO A106", "MATERIAL"),
        ("PDM011", "TERMINAL A: FEMEA BSP", "TERMINAL A"),
    ],
)
def test_missing_technical_terms_are_not_completed_from_a_single_pdm_option(catalog, class_id, text, attribute):
    result = get_extraction_repository().extract(catalog.classes[class_id], text)
    assert attribute not in result.attributes
    assert result.unresolved


@pytest.mark.parametrize(
    ("class_id", "text", "attribute", "expected"),
    [
        ("PDM044", "MATERIAL CORPO: FERRO FUNDIDO NODULAR", "MATERIAL CORPO", "FERRO FUNDIDO NODULAR"),
        ("PDM044", "MATERIAL CORPO: NODULAR FERRO FUNDIDO", "MATERIAL CORPO", "FERRO FUNDIDO NODULAR"),
        ("PDM044", "MATERIAL DISCO: CF8M", "MATERIAL DISCO", "ACO INOX FUNDIDO A351 CF8M"),
        ("PDM050", "MATERIAL: A403 WP316", "MATERIAL", "ACO INOX A403 WP316"),
        ("PDM050", "MATERIAL: ACO INOX WP316", "MATERIAL", "ACO INOX A403 WP316"),
        ("PDM050", "MATERIAL: A105", "MATERIAL", "ACO CARBONO FORJADO A105"),
        ("PDM051", "MATERIAL: ACO CARBONO A106 GR B", "MATERIAL", "ACO CARBONO A106 GR B"),
        ("PDM011", "TERMINAL A: JIC RETA FEM", "TERMINAL A", "FEMEA RETA JIC"),
    ],
)
def test_complete_values_and_explicit_aliases_remain_recognized(catalog, class_id, text, attribute, expected):
    result = get_extraction_repository().extract(catalog.classes[class_id], text)
    assert result.attributes[attribute].value == expected


def test_registration_order_does_not_become_ready_with_an_invented_body_material(catalog):
    text = (
        "VALVULA BORBOLETA; DIAM:DN 50; TIPO CORPO:WAFER; MATERIAL CORPO:FERRO FUNDIDO; "
        "MATERIAL DISCO:CF8M; PTFE; MANOPLA"
    )
    result = analyze_order(
        OrderRow("regression-133", text, None, None, None),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    assert result.status == "INCOMPLETE"
    assert "MATERIAL CORPO" in result.missing_attributes
    assert "MATERIAL CORPO" not in result.attributes


def test_real_incomplete_fittings_cannot_generate_a_fiscal_correction(catalog):
    # O 11264434 informa MACHO NPT e FEMEA 45 JIC, sem os termos RETO e CURVA/GRAUS.
    record = next(record for record in read_csv_records(KIT / "01_base_materiais.csv") if record.code == "11264434")
    material = analyze_material(record, catalog, get_classification_repository(catalog), get_extraction_repository())

    assert "TERMINAL A" not in material.attributes
    assert "TERMINAL B" not in material.attributes
    assert propose_ncm_corrections([material], catalog) == []


def test_explicit_fittings_preserve_the_required_fiscal_review(catalog):
    record = next(record for record in read_csv_records(KIT / "01_base_materiais.csv") if record.code == "11264434")
    description = record.description.replace("TERM A:MACHO NPT", "TERM A:MACHO RETO NPT").replace(
        "LADO B:FEMEA 45 JIC", "LADO B:FEMEA CURVA 45 GRAUS JIC"
    )
    material = analyze_material(
        replace(record, description=description),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )

    proposals = propose_ncm_corrections([material], catalog)
    assert len(proposals) == 1
    assert proposals[0].proposal_type == "NCM_CORRECTION"
    assert proposals[0].fiscal_review_required
    assert proposals[0].members[0]["ncm"] == "4009.2210"
    assert proposals[0].changeset["after"]["ncm"] == "4009.22.10"
