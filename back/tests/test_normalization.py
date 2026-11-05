import csv
import json

import pytest

import cli
from domain.contracts import FieldStatus
from repositories import normalization
from repositories.normalization import REPOSITORIES, get_normalization_repository
from repositories.normalization.rule_based_v1 import RuleBasedV1NormalizationRepository


@pytest.fixture
def v1():
    return RuleBasedV1NormalizationRepository()


# Contrato: todo repositorio registrado precisa cumprir, inclusive os futuros.
@pytest.mark.parametrize("name", sorted(REPOSITORIES))
@pytest.mark.parametrize("method", ["normalize_ncm", "normalize_unit", "normalize_text"])
@pytest.mark.parametrize("empty", [None, "", "   "])
def test_contract_empty_input_is_missing(name, method, empty):
    result = getattr(REPOSITORIES[name](), method)(empty)
    assert result.status is FieldStatus.MISSING
    assert result.value is None
    assert result.rule.startswith(f"{name}/")


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
@pytest.mark.parametrize(
    ("method", "raw"),
    [("normalize_ncm", "84749000"), ("normalize_unit", "PÇ"), ("normalize_text", "válvula  esfera")],
)
def test_contract_preserves_original_and_is_idempotent(name, method, raw):
    normalize = getattr(REPOSITORIES[name](), method)
    first = normalize(raw)
    assert first.original == raw
    second = normalize(first.value)
    assert second.value == first.value
    assert second.status is FieldStatus.CANONICAL


@pytest.mark.parametrize("raw", ["84749000", "8474.9000", "8474.90.00", " 8474.90.00 "])
def test_ncm_kit_formats_converge(v1, raw):
    assert v1.normalize_ncm(raw).value == "8474.90.00"


def test_ncm_canonical_input_is_not_reported_as_changed(v1):
    assert v1.normalize_ncm("8474.90.00").status is FieldStatus.CANONICAL
    assert v1.normalize_ncm("84749000").status is FieldStatus.NORMALIZED


@pytest.mark.parametrize("raw", ["8474", "847490001", "ABCD.EF.GH"])
def test_ncm_invalid_format_needs_review_and_is_never_guessed(v1, raw):
    result = v1.normalize_ncm(raw)
    assert result.status is FieldStatus.UNRESOLVED
    assert result.value is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("PÇ", "PC"), ("PCA", "PC"), ("UN", "PC"), ("MT", "M"), ("MTS", "M"), ("PAR", "PR"), ("LT", "L"), ("pc", "PC")],
)
def test_unit_aliases(v1, raw, expected):
    result = v1.normalize_unit(raw)
    assert result.value == expected
    assert result.status is FieldStatus.NORMALIZED


@pytest.mark.parametrize("raw", ["CX", "CT", "JG", "BR", "RL", "GL", "BD"])
def test_packaging_unit_is_not_converted_without_factor(v1, raw):
    result = v1.normalize_unit(raw)
    assert result.status is FieldStatus.UNRESOLVED
    assert result.value is None
    assert result.rule.endswith("unit.packaging_without_factor")


def test_unknown_unit_needs_review(v1):
    assert v1.normalize_unit("XYZ").rule.endswith("unit.unknown")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Válvula  de   esfera", "VALVULA DE ESFERA"),
        ("CONEXÃO FORJAÇÃO", "CONEXAO FORJACAO"),
        ("CABO 10 MM²", "CABO 10 MM2"),
        ("PARAFUSO M12", "PARAFUSO M12"),
    ],
)
def test_text_follows_pdm_rule_3(v1, raw, expected):
    assert v1.normalize_text(raw).value == expected


def test_unknown_repository_lists_available_options():
    with pytest.raises(ValueError, match="rule_based_v1"):
        get_normalization_repository("nao_existe")


class _AlternativeRepository(RuleBasedV1NormalizationRepository):
    name = "alternative"


def test_new_repository_replaces_active_one_while_previous_stays_registered(monkeypatch):
    monkeypatch.setitem(normalization.REPOSITORIES, "alternative", _AlternativeRepository)
    assert get_normalization_repository().name == "rule_based_v1"
    monkeypatch.setenv("NORMALIZATION_REPOSITORY", "alternative")
    assert get_normalization_repository().name == "alternative"
    assert get_normalization_repository("rule_based_v1").name == "rule_based_v1"


def test_cli_report_counts_without_changing_source(tmp_path, capsys):
    source = tmp_path / "base.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, ["NCM", "UNIDADE_MEDIDA", "DESCRICAO_LONGA"])
        writer.writeheader()
        writer.writerow({"NCM": "84749000", "UNIDADE_MEDIDA": "CX", "DESCRICAO_LONGA": "PORCA"})
        writer.writerow({"NCM": "", "UNIDADE_MEDIDA": "PC", "DESCRICAO_LONGA": "PORCA  M16"})
    before = source.read_bytes()

    assert cli.main(["normalization-report", str(source)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["repository"] == "rule_based_v1"
    assert report["rows"] == 2
    assert report["fields"]["ncm"] == {
        "MISSING rule_based_v1/ncm.missing": 1,
        "NORMALIZED rule_based_v1/ncm.format": 1,
    }
    assert report["fields"]["unit"]["UNRESOLVED rule_based_v1/unit.packaging_without_factor"] == 1
    assert source.read_bytes() == before
