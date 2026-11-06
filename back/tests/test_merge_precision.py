"""Coorte histórica de desenvolvimento: erros e dúvidas persistem depois que o algoritmo muda."""

from pathlib import Path

import pytest

from pipelines.evaluate_sanitization import compare_merges, load_cohorts
from pipelines.sanitize import _catalog, _propose, read_csv_records

KIT = Path(__file__).parents[2] / "data" / "desafio01"


@pytest.fixture(scope="module")
def evaluated():
    merges, _, _ = _propose(
        read_csv_records(str(KIT / "01_base_materiais.csv")), _catalog(str(KIT / "03_padrao_cadastro_PDM.xlsx")), None
    )
    manifest, groups, pairs = load_cohorts()
    return {**compare_merges(merges, groups, pairs, manifest["group_review_additions"]), "current_merges": merges}


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


def test_aliases_cohort_retains_its_labels_and_decided_precision(evaluated):
    import json

    from pipelines.evaluate_sanitization import cohort_data

    manifest, _, pairs = load_cohorts()
    cohort = manifest["additional_group_cohorts"][0]
    groups = json.loads(cohort_data(cohort["file"]))
    assert len(groups["reviewed"]) == 40
    assert sum(case["same_item"] is True for case in groups["reviewed"]) == 39
    report = compare_merges(evaluated["current_merges"], groups, pairs, cohort["review_additions"])["groups"]
    assert report["counts"]["reviewed"] == 38
    assert report["precision"]["denominator"] >= 35
    assert report["precision"]["value"] >= 0.95
