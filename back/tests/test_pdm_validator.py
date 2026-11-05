import csv
from pathlib import Path

import pytest

from domain.contracts import ValidationStatus
from domain.pdm_loader import load_pdm
from domain.pdm_validator import _FORMATS, validate_pdm

DATA = Path(__file__).parents[2] / "data" / "desafio01"
KIT = DATA / "03_padrao_cadastro_PDM.xlsx"

BOLT = {
    "ROSCA": "METRICA GROSSA",
    "BITOLA": "M12",
    "COMPRIMENTO": "50MM",
    "CLASSE RESISTENCIA": "8.8",
    "MATERIAL": "ACO CARBONO",
    "ACABAMENTO": "ZINCADO BRANCO",
    "NORMA": "DIN 933",
}
FLANGE = {
    "TIPO": "PESCOCO WN",
    "DIAMETRO NOMINAL": "2POL",
    "CLASSE PRESSAO": "150#",
    "FACE": "RF",
}


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT)


def material(catalog, class_id, name):
    allowed = next(a for a in catalog.classes[class_id].attributes if a.name == name).allowed_values
    return allowed[0]


def names(items):
    return [item.name for item in items]


def test_briefing_bolt_without_strength_class_is_incomplete(catalog):
    attributes = {k: v for k, v in BOLT.items() if k != "CLASSE RESISTENCIA"}
    result = validate_pdm(catalog, "PDM001", attributes)
    assert result.status is ValidationStatus.INCOMPLETE
    assert names(result.missing_attributes) == ["CLASSE RESISTENCIA"]
    assert result.missing_attributes[0].reason_code == "REQUIRED_ATTRIBUTE_MISSING"
    assert result.missing_attributes[0].question
    assert result.formatted_description is None
    assert result.identity_key is None
    assert result.can_submit is False


def test_valid_bolt_matches_pdm_description_example(catalog):
    result = validate_pdm(catalog, "PDM001", BOLT)
    assert result.status is ValidationStatus.VALID
    assert result.can_submit is True
    assert result.formatted_description == (
        "PARAFUSO SEXTAVADO; ROSCA: METRICA GROSSA; BITOLA: M12; COMPRIMENTO: 50MM; CLASSE RESISTENCIA: 8.8; "
        "MATERIAL: ACO CARBONO; ACABAMENTO: ZINCADO BRANCO; NORMA: DIN 933"
    )


def test_description_keeps_pdm_order_regardless_of_input_order(catalog):
    shuffled = dict(reversed(list(BOLT.items())))
    assert validate_pdm(catalog, "PDM001", shuffled) == validate_pdm(catalog, "PDM001", BOLT)


def test_bearing_description_includes_known_optional_attributes(catalog):
    attributes = {
        "FOLGA": "C3",
        "REFERENCIA": "6205-2RS/C3",
        "VEDACAO": "BORRACHA AMBOS LADOS",
        "DIAMETRO INTERNO": "25MM",
        "DIAMETRO EXTERNO": "52MM",
        "LARGURA": "15MM",
    }
    assert validate_pdm(catalog, "PDM020", attributes).formatted_description == (
        "ROLAMENTO RIGIDO ESFERAS; REFERENCIA: 6205-2RS/C3; DIAMETRO INTERNO: 25MM; DIAMETRO EXTERNO: 52MM; "
        "LARGURA: 15MM; VEDACAO: BORRACHA AMBOS LADOS; FOLGA: C3"
    )


@pytest.mark.parametrize("class_id", [None, "PDM999"])
def test_unknown_class_is_out_of_scope(catalog, class_id):
    result = validate_pdm(catalog, class_id, BOLT)
    assert result.status is ValidationStatus.OUT_OF_SCOPE
    assert result.can_submit is False


@pytest.mark.parametrize("empty", [None, "", "  "])
def test_empty_value_counts_as_missing(catalog, empty):
    result = validate_pdm(catalog, "PDM001", {**BOLT, "NORMA": empty})
    assert names(result.missing_attributes) == ["NORMA"]


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("CLASSE RESISTENCIA", "9.9", "VALUE_NOT_ALLOWED"),
        ("MATERIAL", "aco carbono", "VALUE_NOT_ALLOWED"),
        ("COMPRIMENTO", "50 MM", "INVALID_FORMAT"),
        ("COMPRIMENTO", "16.5MM", "INVALID_FORMAT"),
        ("COR", "AZUL", "UNKNOWN_ATTRIBUTE"),
    ],
)
def test_invalid_values_are_reported_and_block_submission(catalog, name, value, reason):
    result = validate_pdm(catalog, "PDM001", {**BOLT, name: value})
    assert result.status is ValidationStatus.INVALID
    assert (result.invalid_attributes[0].name, result.invalid_attributes[0].reason_code) == (name, reason)
    assert result.formatted_description is None
    assert result.can_submit is False


def test_invalid_wins_over_incomplete_and_both_are_listed(catalog):
    attributes = {k: v for k, v in BOLT.items() if k != "NORMA"}
    result = validate_pdm(catalog, "PDM001", {**attributes, "MATERIAL": "PLASTICO"})
    assert result.status is ValidationStatus.INVALID
    assert names(result.missing_attributes) == ["NORMA"]
    assert names(result.invalid_attributes) == ["MATERIAL"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("16,25MM", True), ("50MM", True), ("2.1/4POL", True), ("1/2POL", True), ("1POL", True), ("50", False)],
)
def test_length_formats(catalog, value, expected):
    result = validate_pdm(catalog, "PDM001", {**BOLT, "COMPRIMENTO": value})
    assert result.can_submit is expected


def test_flange_without_connection_still_requires_pressure_class(catalog):
    attributes = {k: v for k, v in FLANGE.items() if k != "CLASSE PRESSAO"}
    result = validate_pdm(catalog, "PDM050", attributes, item_name="FLANGE")
    assert "CLASSE PRESSAO" in names(result.missing_attributes)
    assert "CONEXAO" not in names(result.missing_attributes)
    assert "SCHEDULE" not in names(result.missing_attributes)


def test_butt_weld_fitting_requires_schedule_instead_of_pressure_class(catalog):
    base = {"DIAMETRO NOMINAL": "2POL", "CONEXAO": "SOLDA TOPO BW"}
    result = validate_pdm(catalog, "PDM050", base, item_name="TE")
    required = names(result.missing_attributes)
    assert "SCHEDULE" in required
    assert "CLASSE PRESSAO" not in required


def test_reduction_fitting_requires_reduced_diameter(catalog):
    base = {"DIAMETRO NOMINAL": "2POL", "CONEXAO": "ROSCA NPT"}
    assert "DIAMETRO REDUZIDO" in names(
        validate_pdm(catalog, "PDM050", base, item_name="TE REDUCAO").missing_attributes
    )
    assert "DIAMETRO REDUZIDO" not in names(validate_pdm(catalog, "PDM050", base, item_name="TE").missing_attributes)


@pytest.mark.parametrize(
    ("class_id", "subject", "value", "attribute", "applies"),
    [
        ("PDM060", "NUMERO CONDUTORES", "1", "COR", True),
        ("PDM060", "NUMERO CONDUTORES", "3", "COR", False),
        ("PDM061", "TIPO", "PRE-ISOLADO OLHAL", "FURO", True),
        ("PDM061", "TIPO", "PRE-ISOLADO PINO", "FURO", False),
        ("PDM062", "TIPO", "MOTOR", "FAIXA AJUSTE", True),
        ("PDM062", "TIPO", "MOTOR", "CORRENTE NOMINAL", False),
        ("PDM062", "TIPO", "MINIDISJUNTOR DIN", "CURVA", True),
        ("PDM062", "TIPO", "CAIXA MOLDADA", "CURVA", False),
        ("PDM081", "TIPO", "CORTE", "ESPESSURA", True),
        ("PDM081", "TIPO", "FLAP", "ESPESSURA", False),
        ("PDM081", "TIPO", "FLAP", "GRAO", True),
    ],
)
def test_conditional_required_attributes(catalog, class_id, subject, value, attribute, applies):
    result = validate_pdm(catalog, class_id, {subject: value})
    assert (attribute in names(result.missing_attributes)) is applies


def test_conditional_attribute_is_not_requested_before_its_subject_is_known(catalog):
    result = validate_pdm(catalog, "PDM062", {})
    required = names(result.missing_attributes)
    assert "TIPO" in required
    assert "CURVA" not in required
    assert "FAIXA AJUSTE" not in required


def test_value_for_non_applicable_attribute_is_reported_and_left_out(catalog):
    gloves = {"MATERIAL": "NITRILICA", "TAMANHO": "G", "CA": "12345", "CANO": "CURTO"}
    result = validate_pdm(catalog, "PDM070", gloves)
    assert result.status is ValidationStatus.VALID
    assert result.not_applicable_attributes == ("CANO",)
    assert "CANO" not in result.formatted_description


def test_class_with_several_items_requires_item_name(catalog):
    result = validate_pdm(catalog, "PDM050", FLANGE)
    assert result.status is ValidationStatus.INCOMPLETE
    assert result.missing_attributes[0].reason_code == "ITEM_NAME_MISSING"


def test_unknown_item_name_is_invalid(catalog):
    result = validate_pdm(catalog, "PDM050", FLANGE, item_name="PARAFUSO")
    assert result.status is ValidationStatus.INVALID
    assert result.invalid_attributes[0].reason_code == "UNKNOWN_ITEM_NAME"


def test_unit_must_be_class_default_when_given(catalog):
    assert validate_pdm(catalog, "PDM001", BOLT, unit="PC").can_submit is True
    result = validate_pdm(catalog, "PDM001", BOLT, unit="CX")
    assert result.status is ValidationStatus.INVALID
    issue = result.invalid_attributes[0]
    assert (issue.name, issue.reason_code, issue.expected) == ("UNIDADE", "UNIT_NOT_CLASS_DEFAULT", "PC")


def test_technical_identity_ignores_optional_attributes_and_order(catalog):
    base = {"REFERENCIA": "6205-2RS/C3", "VEDACAO": "BORRACHA AMBOS LADOS", "FOLGA": "C3"}
    plain = validate_pdm(catalog, "PDM020", base).identity_key
    assert plain == validate_pdm(catalog, "PDM020", {**base, "LARGURA": "15MM"}).identity_key
    other = {**base, "FOLGA": "NORMAL"}
    assert plain != validate_pdm(catalog, "PDM020", other).identity_key


def test_fitting_identity_depends_on_item_name(catalog):
    fitting = {
        "DIAMETRO NOMINAL": "2POL",
        "CLASSE PRESSAO": "150#",
        "MATERIAL": material(catalog, "PDM050", "MATERIAL"),
        "CONEXAO": "ROSCA NPT",
    }
    tee = validate_pdm(catalog, "PDM050", fitting, item_name="TE")
    elbow = validate_pdm(catalog, "PDM050", fitting, item_name="COTOVELO 90 GRAUS")
    assert tee.can_submit and elbow.can_submit
    assert tee.identity_key != elbow.identity_key


def test_manufacturer_identity_uses_only_manufacturer_and_reference(catalog):
    base = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009"}
    first = validate_pdm(catalog, "PDM100", base, item_name="FILTRO OLEO LUBRIFICANTE")
    second = validate_pdm(catalog, "PDM100", {**base, "ALTURA": "100MM"}, item_name="FILTRO OLEO LUBRIFICANTE")
    assert first.identity_key == second.identity_key == "PDM100|FLEETGUARD|LF9009"


def test_interchangeable_products_from_other_manufacturers_stay_distinct(catalog):
    fleetguard = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009"}
    donaldson = {"FABRICANTE": "DONALDSON", "REFERENCIA FABRICANTE": "LF9009"}
    item = "FILTRO OLEO LUBRIFICANTE"
    assert (
        validate_pdm(catalog, "PDM100", fleetguard, item_name=item).identity_key
        != validate_pdm(catalog, "PDM100", donaldson, item_name=item).identity_key
    )


def test_every_free_format_in_kit_has_a_rule(catalog):
    formats = {a.format for c in catalog.classes.values() for a in c.attributes if a.allowed_values is None}
    assert formats - _FORMATS.keys() == set()


@pytest.mark.parametrize(
    "reference, profile, expected",
    [
        ("B54", "B", True),
        ("AX41", "A DENTADA", True),
        ("BX35", "B DENTADA", True),
        ("5V860", "5V", True),
        ("SPB 2000", "SPB", True),
        ("SPB2000", "SPB", False),
    ],
)
def test_belt_references_cover_every_profile_in_pdm(catalog, reference, profile, expected):
    result = validate_pdm(catalog, "PDM030", {"PERFIL": profile, "REFERENCIA": reference})
    assert result.can_submit is expected


def test_canonical_rows_in_base_round_trip_exactly(catalog):
    item_classes = {name: c.id for c in catalog.classes.values() for name in c.item_names}
    valid = 0
    with open(DATA / "01_base_materiais.csv", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            head, *parts = row["DESCRICAO_LONGA"].split("; ")
            if head not in item_classes or not parts or not all(": " in part for part in parts):
                continue
            attributes = dict(part.split(": ", 1) for part in parts)
            result = validate_pdm(catalog, item_classes[head], attributes, item_name=head)
            if result.status is ValidationStatus.VALID:
                valid += 1
                assert result.formatted_description == row["DESCRICAO_LONGA"]
    assert valid > 2500
