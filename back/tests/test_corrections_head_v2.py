"""Correções no padrão aliases_v2 + head_noun_v2, com linhas reais da base conferidas à mão.

A pilha literal (aliases_v1 + head_noun_v1) continua coberta em test_corrections.py e
test_review_lanes.py, como fallback de auditoria.
"""

from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import DEFAULT_REPOSITORY as DEFAULT_CLASSIFIER
from repositories.classification import get_classification_repository
from repositories.corrections import DEFAULT_REPOSITORY as DEFAULT_CORRECTOR
from repositories.corrections import REPOSITORIES, get_correction_repository
from repositories.corrections.head_noun_v2 import head_confirmed
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository

KIT = Path(__file__).parents[2] / "data/desafio01"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def records():
    return {record.code: record for record in read_csv_records(KIT / "01_base_materiais.csv")}


@pytest.fixture(scope="module")
def analyze(catalog, records):
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    return lambda code: analyze_material(records[code], catalog, classifier, extractor)


def correct(catalog, material):
    return get_correction_repository().correct(material, catalog, get_normalization_repository())


def test_defaults_and_literal_fallback_stay_selectable():
    assert (DEFAULT_CLASSIFIER, DEFAULT_CORRECTOR) == ("aliases_v2", "head_noun_v2")
    assert "head_noun_v1" in REPOSITORIES


def test_abbreviated_name_gets_pdm_description_and_trusted_unit(analyze, catalog):
    # 24477027: ALLEN e CAB SEXTAVADA são o sextavado interno; antes ficava sem classe.
    material = analyze("24477027")
    assert (material.pdm_class_id, material.item_name) == ("PDM002", "PARAFUSO SEXTAVADO INTERNO")
    assert head_confirmed(material)

    result = correct(catalog, material)
    changes = {(c.proposal_type, c.field): c for c in result.corrections}
    assert changes[("PDM_CORRECTION", "description")].after.startswith("PARAFUSO SEXTAVADO INTERNO; TIPO CABECA")
    unit = changes[("UNIT_CORRECTION", "unit")]
    assert (unit.before, unit.after, unit.rule) == ("PÇ", "PC", "rule_based_v1/unit.alias")
    assert result.pending == ()


def test_abbreviated_qualifier_resolves_the_more_specific_item(analyze):
    # 19812163: TAMPA PRES é TAMPA PRESSAO, não a TAMPA genérica.
    material = analyze("19812163")
    assert (material.pdm_class_id, material.item_name) == ("PDM110", "TAMPA PRESSAO")
    assert head_confirmed(material)


def test_class_found_mid_text_is_still_not_trusted(analyze, catalog):
    # 18081854: CAIXA MANCAL PEDESTAL; MANCAL aparece depois de outra palavra.
    material = analyze("18081854")
    assert material.pdm_class_id == "PDM023" and not head_confirmed(material)

    result = correct(catalog, material)
    assert all(c.proposal_type == "UNIT_CORRECTION" for c in result.corrections)
    assert result.pending == ("CLASSE_NAO_CONFIRMADA: o nome do item nao abre a descricao",)


def test_ambiguous_prefix_keeps_only_the_unit_alias_without_class(analyze, catalog):
    # 28280948: MANG SUCCAO pode ser MANGOTE ou MANGUEIRA; só a grafia da unidade muda.
    material = analyze("28280948")
    assert material.pdm_class_id is None

    result = correct(catalog, material)
    assert [c.rule for c in result.corrections] == ["head_noun_v2/unit.alias_without_class (rule_based_v1/unit.alias)"]


@pytest.mark.parametrize("code", ["16111456", "13431463"])
def test_separator_filter_is_not_an_air_filter(analyze, code):
    # A barra faz parte do nome: FILTRO SEPARADOR AR/OLEO não é FILTRO AR (outro NCM).
    material = analyze(code)
    assert (material.pdm_class_id, material.item_name) == ("PDM100", "FILTRO SEPARADOR AR/OLEO")


@pytest.mark.parametrize("code", ["16410135", "23762418"])
def test_hose_with_terminals_is_the_assembled_hose(analyze, code):
    # O PDM separa a mangueira sem acessórios (4009.21.10) da montada, com terminais (4009.22.10).
    material = analyze(code)
    assert material.pdm_class_id == "PDM011"
