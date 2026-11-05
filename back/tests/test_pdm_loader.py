from pathlib import Path

import openpyxl
import pytest

from domain.contracts import ITEM_NAME_SUBJECT, Condition, ConditionOperator, IdentityMode
from domain.pdm_loader import PdmLoadError, load_pdm

KIT = Path(__file__).parents[2] / "data" / "desafio01" / "03_padrao_cadastro_PDM.xlsx"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT)


def attribute(catalog, class_id, name):
    return next(a for a in catalog.classes[class_id].attributes if a.name == name)


def test_kit_totals_match_architecture(catalog):
    classes = catalog.classes.values()
    attributes = [a for c in classes for a in c.attributes]
    assert len(catalog.classes) == 44
    assert len(attributes) == 229
    conditional_required = [
        a for a in attributes if a.required and a.applies_when.operator is not ConditionOperator.ALWAYS
    ]
    assert len(conditional_required) == 14
    assert catalog.version == "pdm-kit-v1"
    assert len(catalog.source_sha256) == 64


def test_technical_class_keeps_attribute_order(catalog):
    parafuso = catalog.classes["PDM001"]
    assert parafuso.noun == "PARAFUSO"
    assert parafuso.item_names == ("PARAFUSO SEXTAVADO",)
    assert parafuso.identity_mode is IdentityMode.TECHNICAL_ATTRIBUTES
    assert parafuso.default_unit == "PC"
    assert [a.name for a in parafuso.attributes] == [
        "ROSCA", "BITOLA", "COMPRIMENTO", "CLASSE RESISTENCIA", "MATERIAL", "ACABAMENTO", "NORMA",
    ]
    assert attribute(catalog, "PDM001", "CLASSE RESISTENCIA").allowed_values == (
        "10.9", "5.8", "8.8", "A2-70", "A4-70", "SAE GRAU 2", "SAE GRAU 5", "SAE GRAU 8",
    )
    assert attribute(catalog, "PDM001", "COMPRIMENTO").allowed_values is None


def test_class_without_qualifier_uses_noun_as_item_name(catalog):
    assert catalog.classes["PDM003"].item_names == ("PORCA",)
    assert catalog.classes["PDM003"].qualifiers == ()


def test_class_with_multiple_qualifiers_lists_each_item(catalog):
    filtro = catalog.classes["PDM100"]
    assert filtro.identity_mode is IdentityMode.MANUFACTURER_REFERENCE
    assert "FILTRO OLEO LUBRIFICANTE" in filtro.item_names
    assert len(filtro.item_names) == 5


@pytest.mark.parametrize(("class_id", "count", "example"), [("PDM050", 11, "TE REDUCAO"), ("PDM110", 62, "VIGA")])
def test_noun_sheets_are_resolved(catalog, class_id, count, example):
    pdm_class = catalog.classes[class_id]
    assert pdm_class.noun is None
    assert len(pdm_class.item_names) == count
    assert example in pdm_class.item_names


@pytest.mark.parametrize(
    ("class_id", "name", "expected"),
    [
        ("PDM050", "FACE", Condition(ConditionOperator.EQUALS, ITEM_NAME_SUBJECT, ("FLANGE",))),
        ("PDM050", "CONEXAO", Condition(ConditionOperator.NOT_IN, ITEM_NAME_SUBJECT, ("FLANGE",))),
        ("PDM050", "SCHEDULE", Condition(ConditionOperator.EQUALS, "CONEXAO", ("SOLDA TOPO BW",))),
        ("PDM050", "CLASSE PRESSAO", Condition(ConditionOperator.NOT_IN, "CONEXAO", ("SOLDA TOPO BW",))),
        ("PDM060", "COR", Condition(ConditionOperator.EQUALS, "NUMERO CONDUTORES", ("1",))),
        ("PDM062", "CURVA", Condition(ConditionOperator.EQUALS, "TIPO", ("MINIDISJUNTOR DIN",))),
        ("PDM081", "GRAO", Condition(ConditionOperator.EQUALS, "TIPO", ("FLAP",))),
        ("PDM100", "ALTURA", Condition()),
    ],
)
def test_conditions_become_controlled_operators(catalog, class_id, name, expected):
    assert attribute(catalog, class_id, name).applies_when == expected


def test_ncm_references_keep_codes_and_rules(catalog):
    assert catalog.classes["PDM003"].ncm_references[0].codes == ("7318.16.00",)
    assert len(catalog.classes["PDM100"].ncm_references[0].codes) == 4
    pdm110 = catalog.classes["PDM110"].ncm_references
    assert len(pdm110) == 16
    assert any(r.codes == ("8708.30.11",) and "PASTILHA FREIO" in r.rule for r in pdm110)
    assert sum(len(c.ncm_references) for c in catalog.classes.values()) == 59


def edited_kit(tmp_path, edit) -> Path:
    workbook = openpyxl.load_workbook(KIT)
    edit(workbook)
    target = tmp_path / "pdm.xlsx"
    workbook.save(target)
    return target


def set_cell(sheet, class_id, attribute_name, column, value):
    header = [cell.value for cell in sheet[1]]
    for row in sheet.iter_rows(min_row=2):
        if row[0].value == class_id and row[2].value == attribute_name:
            row[header.index(column)].value = value
            return
    raise AssertionError("linha nao encontrada")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda w: set_cell(w["ATRIBUTOS"], "PDM081", "GRAO", "QUANDO_SE_APLICA", "__import__('os')"), "nao mapeada"),
        (lambda w: set_cell(w["ATRIBUTOS"], "PDM081", "GRAO", "OBRIGATORIO", "TALVEZ"), "OBRIGATORIO"),
        (lambda w: set_cell(w["ATRIBUTOS"], "PDM081", "TIPO", "VALORES_PERMITIDOS", "CORTE | DESBASTE"), "inexistentes"),
        (lambda w: set_cell(w["ATRIBUTOS"], "PDM081", "TIPO", "ATRIBUTO", "CATEGORIA"), "inexistente"),
        (lambda w: w["CLASSES"].cell(2, 5, "XX"), "unidade desconhecida"),
        (lambda w: w["CLASSES"].cell(2, 7, "OUTRO"), "identidade"),
        (lambda w: w["NCM_REFERENCIA"].cell(2, 2, "7318"), "NCM invalido"),
        (lambda w: w["ATRIBUTOS"].cell(1, 5, "CONDICAO"), "colunas"),
        (lambda w: w.remove(w["UNIDADES"]), "Aba ausente"),
    ],
)
def test_unexpected_content_fails_loudly(tmp_path, edit, message):
    with pytest.raises(PdmLoadError, match=message):
        load_pdm(edited_kit(tmp_path, edit))
