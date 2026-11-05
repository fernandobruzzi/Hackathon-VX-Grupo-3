"""Casos conferidos contra a aba NCM_REFERENCIA do kit, sem consulta fiscal externa."""

from dataclasses import replace
from pathlib import Path

import pytest

from domain.contracts import NcmReference
from domain.ncm_rules import check_ncm_consistency
from domain.pdm_loader import load_pdm


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


def test_briefing_nut_requires_fiscal_review_and_keeps_original(catalog):
    attrs = {"TIPO": "SEXTAVADA", "BITOLA": "M16"}
    result = check_ncm_consistency(catalog, "PDM003", attrs, "7318.15.00")
    assert result.input_ncm == "7318.15.00"
    assert result.normalized_ncm == "7318.15.00"
    assert result.technical_consistency == "INCONSISTENT"
    assert result.suggested_ncm_codes == ("7318.16.00",)
    assert result.requires_fiscal_review
    assert result.fiscal_approval_status == "PENDING"
    assert result.exists_in_snapshot is result.valid_in_snapshot is None
    assert result.reference_source.endswith("#NCM_REFERENCIA")
    assert result.pdm_source_sha256 == catalog.source_sha256
    assert attrs == {"TIPO": "SEXTAVADA", "BITOLA": "M16"}


@pytest.mark.parametrize("raw", [None, "", "7318", "7318.16.000", "ABCDEFGH", "７３１８１６００"])
def test_missing_and_invalid_ncm_are_not_guessed(catalog, raw):
    result = check_ncm_consistency(catalog, "PDM003", {}, raw)
    assert not result.syntax_valid
    assert result.normalized_ncm is None
    assert result.requires_fiscal_review


def test_format_is_separate_from_technical_and_official_validation(catalog):
    result = check_ncm_consistency(catalog, "PDM003", {}, "73181600")
    assert result.syntax_valid
    assert result.normalized_ncm == "7318.16.00"
    assert result.technical_consistency == "CONSISTENT"
    assert result.requires_fiscal_review  # Persistir a formatação também é uma alteração.
    assert result.exists_in_snapshot is None
    with pytest.raises(ValueError, match="Snapshot oficial NCM indisponível"):
        check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", ncm_version="ncm-demo-v1")


def test_already_consistent_is_not_an_approval(catalog):
    result = check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00")
    assert not result.requires_fiscal_review
    assert result.fiscal_approval_status == "NOT_REQUIRED"
    assert "OFFICIAL_SNAPSHOT_UNAVAILABLE" in result.pending_checks


@pytest.mark.parametrize(
    ("class_id", "attrs", "item", "expected"),
    [
        ("PDM012", {"MATERIAL": "PVC"}, None, "3917.39.00"),
        ("PDM012", {"MATERIAL": "NBR", "REFORCO": "LONAS TEXTEIS"}, None, "4009.31.00"),
        ("PDM012", {"MATERIAL": "EPDM", "REFORCO": "ESPIRAL ACO + LONAS TEXTEIS"}, None, "4009.41.00"),
        ("PDM014", {"MATERIAL": "BORRACHA COM ESPIRAL ACO"}, None, "4009.41.00"),
        ("PDM014", {"MATERIAL": "PVC COM ESPIRAL PVC RIGIDO"}, None, "3917.39.00"),
        ("PDM030", {"COMPRIMENTO EXTERNO": "600MM"}, None, "4010.39.00"),
        ("PDM030", {"COMPRIMENTO EXTERNO": "600.1MM"}, None, "4010.32.00"),
        ("PDM030", {"COMPRIMENTO EXTERNO": "180CM"}, None, "4010.32.00"),
        ("PDM030", {"COMPRIMENTO EXTERNO": "1800.1MM"}, None, "4010.34.00"),
        ("PDM030", {"COMPRIMENTO EXTERNO": "2.4M"}, None, "4010.34.00"),
        ("PDM030", {"COMPRIMENTO EXTERNO": "2400.1MM"}, None, "4010.39.00"),
        ("PDM034", {"MATERIAL": "PTFE EXPANDIDO"}, None, "3926.90.90"),
        ("PDM034", {"MATERIAL": "NBR"}, None, "4016.93.00"),
        ("PDM050", {"MATERIAL": "ACO CARBONO FORJADO A105"}, "FLANGE", "7307.91.00"),
        ("PDM050", {"MATERIAL": "ACO INOX FORJADO A182 F316"}, "FLANGE", "7307.21.00"),
        ("PDM050", {"MATERIAL": "FERRO MALEAVEL GALVANIZADO"}, "TE", "7307.19.90"),
        ("PDM050", {"MATERIAL": "ACO INOX A403 WP316", "CONEXAO": "SOLDA TOPO BW"}, "TE", "7307.23.00"),
        ("PDM050", {"MATERIAL": "ACO CARBONO A234 WPB", "CONEXAO": "ROSCA NPT"}, "LUVA", "7307.92.00"),
        ("PDM050", {"MATERIAL": "ACO INOX FORJADO A182 F316", "CONEXAO": "ROSCA BSP"}, "TE", "7307.29.00"),
        ("PDM050", {"MATERIAL": "ACO CARBONO FORJADO A105", "CONEXAO": "SOLDA ENCAIXE SW"}, "CAP", "7307.99.00"),
        (
            "PDM051",
            {"MATERIAL": "ACO CARBONO A106 GR B", "COSTURA": "SEM COSTURA", "DIAMETRO NOMINAL": "8POL"},
            None,
            "7304.39.10",
        ),
        (
            "PDM051",
            {"MATERIAL": "ACO CARBONO A106 GR B", "COSTURA": "SEM COSTURA", "DIAMETRO NOMINAL": "10POL"},
            None,
            "7304.39.90",
        ),
        ("PDM051", {"MATERIAL": "ACO INOX A312 TP316L", "COSTURA": "COM COSTURA"}, None, "7306.40.00"),
        ("PDM051", {"MATERIAL": "ACO CARBONO API 5L GR B", "COSTURA": "SEM COSTURA"}, None, "7304.19.00"),
        ("PDM051", {"MATERIAL": "ACO GALVANIZADO NBR 5580", "COSTURA": "COM COSTURA"}, None, "7306.30.00"),
        ("PDM070", {"MATERIAL": "VAQUETA"}, None, "4203.29.00"),
        ("PDM070", {"MATERIAL": "NITRILICA"}, None, "4015.19.00"),
        ("PDM070", {"MATERIAL": "MALHA REVESTIDA PU"}, None, "6116.10.00"),
        ("PDM071", {"BIQUEIRA": "ACO"}, None, "6403.40.00"),
        ("PDM071", {"BIQUEIRA": "COMPOSITE"}, None, "6403.99.90"),
        ("PDM081", {"TIPO": "CORTE"}, None, "6804.22.11"),
        ("PDM081", {"TIPO": "FLAP"}, None, "6805.10.00"),
        ("PDM100", {}, "FILTRO AR", "8421.31.00"),
        ("PDM100", {}, "FILTRO HIDRAULICO", "8421.29.90"),
        ("PDM100", {}, "FILTRO SEPARADOR AR/OLEO", "8421.39.90"),
        ("PDM110", {"APLICACAO": "BOMBA POLPA"}, "ROTOR", "8413.91.90"),
        ("PDM110", {"APLICACAO": "BRITADOR CONICO"}, "PASTILHA FREIO", "8708.30.11"),
        ("PDM110", {}, "DISCO FREIO", "8708.30.90"),
    ],
)
def test_conditional_rules_from_pdm(catalog, class_id, attrs, item, expected):
    result = check_ncm_consistency(catalog, class_id, attrs, expected, item_name=item)
    assert result.suggested_ncm_codes == (expected,)
    assert result.technical_consistency == "CONSISTENT"


@pytest.mark.parametrize(
    ("class_id", "attrs", "item"),
    [
        ("PDM012", {"MATERIAL": "NBR"}, None),
        ("PDM030", {"COMPRIMENTO EXTERNO": "A42"}, None),
        ("PDM030", {"COMPRIMENTO EXTERNO": "0MM"}, None),
        ("PDM050", {"MATERIAL": "INOX 316", "CONEXAO": "ROSCA NPT"}, "TE"),
        ("PDM050", {"MATERIAL": "ACO CARBONO A234 WPB"}, "TE"),
        ("PDM051", {"MATERIAL": "ACO CARBONO A106 GR B", "COSTURA": "COM COSTURA"}, None),
        ("PDM051", {"MATERIAL": "ACO CARBONO A106 GR B", "COSTURA": "SEM COSTURA", "DIAMETRO NOMINAL": "16POL"}, None),
        ("PDM070", {"MATERIAL": "ANTICORTE"}, None),
        ("PDM100", {}, None),
        ("PDM110", {"APLICACAO": "BOMBA POLPA"}, "NOME INVENTADO"),
    ],
)
def test_ambiguous_conditions_never_confirm_a_code(catalog, class_id, attrs, item):
    result = check_ncm_consistency(catalog, class_id, attrs, "7318.16.00", item_name=item)
    assert result.technical_consistency == "UNDETERMINED"
    assert result.requires_fiscal_review
    assert "PDM_CONDITION_UNRESOLVED" in result.pending_checks


def test_missing_controlling_attribute_is_reported(catalog):
    result = check_ncm_consistency(catalog, "PDM071", {}, "6403.40.00")
    assert result.missing_attributes == ("BIQUEIRA",)


def test_changed_attributes_and_versions_invalidate_the_evaluation(catalog):
    first = check_ncm_consistency(catalog, "PDM071", {"BIQUEIRA": "ACO"}, "6403.40.00")
    changed = check_ncm_consistency(catalog, "PDM071", {"BIQUEIRA": "COMPOSITE"}, "6403.40.00")
    assert changed.evaluation_hash != first.evaluation_hash
    assert changed.suggested_ncm_codes == ("6403.99.90",)
    assert changed.requires_fiscal_review
    assert (
        check_ncm_consistency(
            replace(catalog, version="v2"), "PDM071", {"BIQUEIRA": "ACO"}, "6403.40.00"
        ).evaluation_hash
        != first.evaluation_hash
    )


def test_unknown_conditional_text_is_not_silently_interpreted(catalog):
    cls = catalog.classes["PDM071"]
    changed = replace(cls, ncm_references=(NcmReference(cls.ncm_references[0].codes, "nova regra"),))
    result = check_ncm_consistency(
        replace(catalog, classes={**catalog.classes, cls.id: changed}), cls.id, {"BIQUEIRA": "ACO"}, "6403.40.00"
    )
    assert result.technical_consistency == "UNDETERMINED"


def test_unknown_class_is_explicit(catalog):
    assert check_ncm_consistency(catalog, "PDM999", {}, "7318.16.00").technical_consistency == "OUT_OF_SCOPE"
