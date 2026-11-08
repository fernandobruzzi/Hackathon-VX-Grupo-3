"""Avaliador do benchmark de NCM: pontuação isolada do gabarito e números atuais registrados."""

from pathlib import Path

import pytest

from pipelines.measure_ncm_benchmark import measure, normalize_ncm, score

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7318.15.00", "73181500"),
        ("73181500", "73181500"),
        ("7318 15 00", "73181500"),
        ("7318.15", None),
        ("NCM 73181500", None),
        ("", None),
    ],
)
def test_normalization_never_extracts_or_completes(raw, expected):
    assert normalize_ncm(raw) == expected


def row(key, situation, gold, ncm, family="Parafusos", eligible="true"):
    return {
        "ID_BENCHMARK": key,
        "FAMILIA_GABARITO": family,
        "ELEGIVEL_BENCHMARK_NCM": eligible,
        "SITUACAO_NCM_ORIGINAL": situation,
        "NCM_GABARITO": gold,
        "NCM": ncm,
    }


def test_score_separates_preservation_fixes_abstentions_and_pending():
    rows = [
        row("a", "CORRETO", "73181500", "7318.15.00"),
        row("b", "CORRETO", "73181500", "73181500"),
        row("c", "INCORRETO", "73181500", "73181900"),
        row("d", "AUSENTE", "73181500", ""),
        row("e", "NAO_AVALIAVEL", "", "", eligible="false"),
    ]
    predictions = {"a": "73181500", "b": "73181600", "c": "73181500", "d": None, "e": "40169300"}
    report = score(rows, predictions, proposed={"a", "b", "c", "e"})["total"]
    assert report["by_situation"]["CORRETO"]["numerator"] == 1
    assert report["improper_changes"] == 1
    assert report["format_only_proposals"] == 1
    assert report["errors_and_missing_resolved"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["abstentions"] == 1
    assert report["pending_routed_to_review"]["numerator"] == 0


def test_current_rules_on_benchmark_v1(monkeypatch):
    # Medição de desenvolvimento com rótulos documentais; não é acurácia homologada.
    monkeypatch.setenv("CLASSIFICATION_REPOSITORY", "aliases_v2")
    report = measure(ROOT / "data/benchmark_ncm/v1", str(ROOT / "data/desafio01/03_padrao_cadastro_PDM.xlsx"))
    total = report["total"]
    assert report["rotulos"] == "DOCUMENTAL_SEM_REVISAO_INDEPENDENTE"
    assert total["improper_changes"] == 0
    assert total["errors_and_missing_resolved"]["numerator"] >= 677
    assert total["errors_and_missing_resolved"]["denominator"] == 695
    assert total["balanced_accuracy"] >= 0.95
    assert total["pending_routed_to_review"] == {"numerator": 363, "denominator": 363, "value": 1.0}


def test_auditor_measurement_reports_by_family_without_the_answer_key(monkeypatch):
    # Simulado: abstém-se em tudo, então o total com auditor é igual ao das regras.
    monkeypatch.setenv("CLASSIFICATION_REPOSITORY", "aliases_v2")
    monkeypatch.setenv("LLM_REPOSITORY", "simulated_v1")
    monkeypatch.setenv("LLM_MAX_CALLS_PER_RUN", "1000")
    report = measure(
        ROOT / "data/benchmark_ncm/v1", str(ROOT / "data/desafio01/03_padrao_cadastro_PDM.xlsx"), llm_audit=True
    )
    audit = report["llm_audit"]
    assert audit["usage"]["simulated"] is True
    assert audit["cases"] == audit["families"]["total"]["cases"] > 0
    assert audit["families"]["total"].get("proposed", 0) == 0
    assert audit["with_auditor"]["total"] == report["total"]


def test_auditor_measurement_requires_a_configured_model(monkeypatch):
    monkeypatch.delenv("LLM_REPOSITORY", raising=False)
    pdm = str(ROOT / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
    with pytest.raises(ValueError, match="LLM_REPOSITORY"):
        measure(ROOT / "data/benchmark_ncm/v1", pdm, llm_audit=True)
