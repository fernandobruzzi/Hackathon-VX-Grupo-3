"""Coorte histórica de desenvolvimento: erros e dúvidas persistem depois que o algoritmo muda."""

from pathlib import Path

import pytest

from pipelines.evaluate_sanitization import compare_merges, load_cohorts
from pipelines.sanitize import _catalog, _propose, read_csv_records

KIT = Path(__file__).parents[2] / "data" / "desafio01"


@pytest.fixture(scope="module")
def evaluated():
    review = {}
    merges, _, _ = _propose(
        read_csv_records(str(KIT / "01_base_materiais.csv")),
        _catalog(str(KIT / "03_padrao_cadastro_PDM.xlsx")),
        None,
        identity_review=review,
    )
    manifest, groups, pairs = load_cohorts()
    return {
        **compare_merges(merges, groups, pairs, manifest["group_review_additions"]),
        "current_merges": merges,
        "identity_review": review,
    }


def test_frozen_cohort_is_not_replaced_when_the_candidates_change(evaluated):
    cases = evaluated["groups"]["cases"]
    assert len(cases) == 40
    assert sum(case["historical_label"] is True for case in cases) == 38
    assert sum(case["expected"] is None for case in cases) == 3
    assert all(case["review_status"] == "INCONCLUSIVE" for case in cases if case["expected"] is None)


def test_known_errors_are_visible_even_after_they_stop_being_proposed(evaluated):
    cases = evaluated["groups"]["cases"]
    errors = {tuple(case["codes"]): case for case in cases if case["expected"] is False}
    assert set(errors) == {("19547027", "22125549"), ("17590309", "27863373")}
    proposed_errors = sum(case["proposed"] for case in errors.values())
    assert evaluated["groups"]["counts"]["wrong"] == proposed_errors
    # A #73 corrige o algoritmo. Esta issue testa a contabilidade e preserva seus contraexemplos.
    assert all(
        case["current_status"] in {"EXACT_PROPOSAL", "NOT_PROPOSED", "CHANGED_GROUP"} for case in errors.values()
    )


def test_group_interval_counts_groups_instead_of_expanding_correlated_pairs(evaluated):
    groups = evaluated["groups"]
    assert groups["counts"]["reviewed"] == 37
    assert groups["precision"]["denominator"] <= 37
    assert groups["counts"]["cases"] == 40
    assert evaluated["pairs"]["conditional_precision_interval"] is None


def test_aliases_cohort_retains_labels_and_records_conservative_abstention(evaluated):
    import json

    from pipelines.evaluate_sanitization import cohort_data

    manifest, _, pairs = load_cohorts()
    cohort = manifest["additional_group_cohorts"][0]
    groups = json.loads(cohort_data(cohort["file"]))
    assert len(groups["reviewed"]) == 40
    assert sum(case["same_item"] is True for case in groups["reviewed"]) == 39
    report = compare_merges(evaluated["current_merges"], groups, pairs, cohort["review_additions"])["groups"]
    assert report["counts"]["reviewed"] == 38
    # identity-v3 retém sete positivos históricos, dois inconclusivos e o erro conhecido.
    # Os rótulos não mudam para esconder essa perda de cobertura.
    assert report["precision"]["denominator"] == 30
    assert report["counts"]["wrong"] == 0
    assert report["inconclusive_reviews"] == 2
    assert report["positive_recovery_in_cohort"]["numerator"] == 30
    assert report["positive_recovery_in_cohort"]["denominator"] == 37
    assert report["algorithm_abstention"]["numerator"] == 10
    assert report["precision"]["value"] >= 0.95


def test_identity_v2_development_sample_keeps_its_own_review(evaluated):
    import json

    sample = json.loads((Path(__file__).parent / "fixtures/merge_identity_sample_73.json").read_text(encoding="utf-8"))
    current = {tuple(sorted(proposal.material_codes)) for proposal in evaluated["current_merges"]}
    assert sample["review_kind"] == "DEVELOPMENT_REGRESSION" and sample["independent"] is False
    assert len(sample["reviewed"]) == 40
    assert all(item["same_item"] is True for item in sample["reviewed"])
    # A #133 também retém o TE sem BW explícito, preservando seu rótulo histórico.
    qualifier_abstention = ("13563770", "29792424")
    assert qualifier_abstention not in current
    withdrawn = [
        item
        for item in sample["reviewed"]
        if tuple(sorted(item["codes"])) not in current and tuple(sorted(item["codes"])) != qualifier_abstention
    ]
    assert withdrawn
    pending = {
        row["evidence"]["material_code"]: row["reasons"] for row in evaluated["identity_review"]["manual_review"]
    }
    assert all("SUFIXO_REFERENCIA_NAO_CONFIRMADO" in pending[code] for item in withdrawn for code in item["codes"])
