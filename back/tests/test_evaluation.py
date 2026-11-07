"""A avaliação distingue incerteza de rótulo, abstenção e unidade estatística."""

import json
from collections import Counter
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from domain.evaluation import merge_metrics, resolve_reviews, wilson95
from pipelines.evaluate_sanitization import compare_merges, evaluate_technical, load_cohorts, reviewed_cases


def review(label, author="revisor", evidence=None):
    return {
        "label": label,
        "author": author,
        "evidence": ["Texto original conferido."] if evidence is None else evidence,
    }


def test_disagreement_and_uncertainty_require_explicit_resolution():
    assert resolve_reviews([review(True), review(False, "segundo")]) == (None, "DISAGREEMENT")
    assert resolve_reviews([review(True), review(None, "segundo")]) == (None, "INCONCLUSIVE")
    assert resolve_reviews([review(False), review(False, "segundo")]) == (False, "AGREEMENT")
    assert resolve_reviews([]) == (None, "NOT_REVIEWED")


@pytest.mark.parametrize(
    "invalid",
    [
        {"label": True, "evidence": ["x"]},
        review(True, ""),
        review(True, evidence=[]),
        review(1),
        {"author": "a", "evidence": ["x"]},
    ],
)
def test_review_requires_author_evidence_and_an_explicit_boolean_or_null(invalid):
    with pytest.raises(ValueError):
        resolve_reviews([invalid])


def test_the_same_author_cannot_count_as_a_second_reviewer():
    with pytest.raises(ValueError, match="dois revisores"):
        resolve_reviews([review(True, "bepo7"), review(True, " BEPO7 ")])


def test_wilson_interval_preserves_uncertainty_with_perfect_small_samples():
    interval = wilson95(40, 40)
    assert interval["lower"] == pytest.approx(0.9123783988)
    assert interval["upper"] == pytest.approx(1)
    assert wilson95(0, 40)["lower"] == pytest.approx(0)
    assert wilson95(0, 0) is None
    with pytest.raises(ValueError):
        wilson95(2, 1)


def test_unknown_labels_are_not_dropped_from_the_report():
    cases = [
        {"expected": True, "proposed": True},
        {"expected": False, "proposed": True},
        {"expected": None, "proposed": True},
        {"expected": True, "proposed": False},
    ]
    result = merge_metrics(cases, group_interval=True)
    assert result["precision"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert result["inconclusive_reviews"] == 1
    assert result["algorithm_abstention"]["value"] == 0.25
    assert result["positive_recovery_in_cohort"]["value"] == 0.5
    assert result["precision_bounds_including_unknown_labels"] == {"lower": 1 / 3, "upper": 2 / 3}
    assert result["population_duplicate_recall"] is None


def test_empty_denominators_never_become_perfect_precision():
    report = merge_metrics([])
    assert report["precision"]["value"] is None
    assert report["conditional_precision_interval"] is None
    assert report["precision_bounds_including_unknown_labels"] is None


def test_group_labels_do_not_turn_into_pair_labels_or_transfer_to_larger_groups():
    groups = {"reviewed": [{"codes": ["a", "b", "c"], "same_item": False, "note": "Um membro difere."}]}
    pairs = {"pairs": [{"codes": ["a", "b"], "same_item": True, "note": "Este par é igual."}]}
    result = compare_merges([SimpleNamespace(material_codes=("a", "b", "c"))], groups, pairs)
    assert result["groups"]["precision"]["value"] == 0
    assert result["pairs"]["precision"]["value"] == 1
    assert result["pairs"]["conditional_precision_interval"] is None
    changed = compare_merges([SimpleNamespace(material_codes=("a", "b", "c", "d"))], groups, pairs)
    assert changed["groups"]["cases"][0]["current_status"] == "CHANGED_GROUP"
    assert changed["groups"]["precision"]["value"] is None
    assert changed["pairs"]["precision"]["value"] == 1


def test_historical_cohort_and_revision_labels_remain_traceable():
    manifest, groups, pairs = load_cohorts()
    assert len(groups["reviewed"]) == 40 and len(pairs["pairs"]) == 95
    cases = reviewed_cases(groups["reviewed"], manifest["group_review_additions"])
    assert sum(case["historical_label"] is True for case in cases) == 38
    assert sum(case["expected"] is True for case in cases) == 35
    uncertain = [case for case in cases if case["expected"] is None]
    assert len(uncertain) == 3
    assert all(case["historical_label"] is True and len(case["reviews"]) == 2 for case in uncertain)
    assert sum(case["expected"] is False for case in cases) == 2


def test_frozen_cohort_detects_accidental_replacement(monkeypatch):
    import pipelines.evaluate_sanitization as module

    original = module.frozen_data
    monkeypatch.setattr(
        module, "frozen_data", lambda name: original(name) + (b" " if name == "merge_groups_v1.json" else b"")
    )
    with pytest.raises(ValueError, match="Coorte histórica"):
        load_cohorts()


def test_duplicate_cases_and_reviews_outside_the_cohort_are_rejected():
    case = {"codes": ["a", "b"], "same_item": True, "note": "Conferido."}
    with pytest.raises(ValueError):
        reviewed_cases([case, case])
    with pytest.raises(ValueError):
        reviewed_cases([case], [{"codes": ["b", "c"], **review(False)}])


def test_technical_scoring_does_not_confuse_wrong_values_missing_fields_and_safe_abstention():
    sample = {
        "author": "desenvolvimento",
        "method": "Texto",
        "selection": "Dirigida",
        "cases": [
            {
                "code": "1",
                "description": "M12 50MM",
                "expected_class_id": "PDM001",
                "evidence": ["M12 50MM"],
                "tags": ["dimensao"],
                "attributes": {"BITOLA": "M12", "COMPRIMENTO": "50MM", "MATERIAL": None, "NORMA": None},
            },
        ],
    }
    material = SimpleNamespace(
        record=SimpleNamespace(description="M12 50MM"),
        pdm_class_id="PDM001",
        attributes={"BITOLA": "M14", "MATERIAL": "ACO CARBONO"},
    )
    result = evaluate_technical(sample, {"1": material})
    assert result["counts"]["wrong_values"] == 1
    assert result["counts"]["unsupported_fills"] == 1
    assert result["counts"]["safe_abstentions"] == 1
    assert result["precision"]["value"] == 0
    assert result["algorithm_abstention"]["value"] == 0.5
    assert result["conditional_precision_interval"] is None


def test_reference_comparison_ignores_separators_but_preserves_revision_information():
    sample = {
        "author": "dev",
        "method": "Texto",
        "selection": "Dirigida",
        "cases": [
            {
                "code": "1",
                "description": "REF 809-2155 REV A",
                "expected_class_id": "PDM110",
                "evidence": ["809-2155 REV A"],
                "tags": [],
                "attributes": {"REFERENCIA FABRICANTE": "8092155 REV A"},
            },
        ],
    }
    material = SimpleNamespace(
        record=SimpleNamespace(description="REF 809-2155 REV A"),
        pdm_class_id="PDM110",
        attributes={"REFERENCIA FABRICANTE": "809-2155"},
    )
    assert evaluate_technical(sample, {"1": material})["precision"]["value"] == 0
    material.attributes["REFERENCIA FABRICANTE"] = "809-2155 REV A"
    assert evaluate_technical(sample, {"1": material})["precision"]["value"] == 1


def test_proxy_metrics_have_no_invented_precision_without_labels():
    from domain.pdm_loader import load_pdm
    from pipelines.measure_extraction import DATA, measure_against_columns

    report = measure_against_columns(load_pdm(DATA / "03_padrao_cadastro_PDM.xlsx"), [])
    assert all(value["precision_percent"] is None and value["coverage_percent"] is None for value in report.values())


def test_real_report_exposes_denominators_and_development_provenance(tmp_path, monkeypatch):
    from domain.pdm_loader import load_pdm
    from pipelines import evaluate_sanitization, full_run
    from pipelines.evaluate_sanitization import sanitization_evaluation
    from pipelines.measure_extraction import DATA
    from pipelines.sanitize import read_csv_records

    captured = {}
    original_coverage = evaluate_sanitization.coverage

    def capture(records, proposals, pending, errors):
        captured["evaluation"] = proposals
        return original_coverage(records, proposals, pending, errors)

    monkeypatch.setattr(evaluate_sanitization, "coverage", capture)
    report = sanitization_evaluation(str(DATA / "01_base_materiais.csv"), str(DATA / "03_padrao_cadastro_PDM.xlsx"))

    def save(proposals, records, context):
        captured["batch"] = proposals
        return len(proposals)

    connection = object()
    records = read_csv_records(DATA / "01_base_materiais.csv")
    catalog = load_pdm(DATA / "03_padrao_cadastro_PDM.xlsx")
    context = full_run.RunContext(engine=SimpleNamespace(begin=lambda: nullcontext(connection)), tenant_id="test")

    def save_reviews(connection_arg, records_arg, analyzed, pending_by_code, context_arg, catalog_arg, corrector_name):
        assert connection_arg is connection
        assert records_arg is records
        assert [material.record for material in analyzed] == records
        assert context_arg is context
        assert catalog_arg is catalog
        assert corrector_name == "head_noun_v1"
        captured["manual_pending"] = pending_by_code
        return "test-manual-review-run"

    monkeypatch.setattr(full_run, "save_all", save)
    monkeypatch.setattr(full_run, "save_manual_reviews", save_reviews)
    metrics = full_run.run_full(records, catalog, context)
    assert metrics["manual_review_run_id"] == "test-manual-review-run"
    assert set(captured["manual_pending"]) <= {record.code for record in records}
    assert (
        Counter(reason for reasons in captured["manual_pending"].values() for reason in reasons)
        == metrics["corrections"]["pending"]
    )
    evaluation_members = {c for p in captured["evaluation"] for c in p.material_codes}
    batch_members = {c for p in captured["batch"] for c in p.material_codes}
    assert evaluation_members == batch_members
    assert {(p.proposal_type, p.material_codes) for p in captured["evaluation"]} == {
        (p.proposal_type, p.material_codes) for p in captured["batch"]
    }
    assert report["coverage"] == metrics["coverage"]
    ncm_members = {c for p in captured["evaluation"] if p.proposal_type == "NCM_CORRECTION" for c in p.material_codes}
    other_members = {c for p in captured["evaluation"] if p.proposal_type != "NCM_CORRECTION" for c in p.material_codes}
    assert ncm_members - other_members
    assert report["coverage"]["outcomes"]["PROPOSTA"] == len(evaluation_members)

    assert report["evaluation_kind"] == "DEVELOPMENT_EVALUATION"
    assert report["independent_review"] is False and report["authorizes_merge"] is False
    assert report["coverage"]["materials_total"] == sum(report["coverage"]["outcomes"].values()) == 23554
    assert report["groups"]["counts"]["cases"] == 40
    assert report["groups"]["counts"]["reviewed"] == 37
    assert report["groups"]["inconclusive_reviews"] == 3
    assert report["pairs"]["counts"]["cases"] == 95
    assert len({row["expected_class_id"] for row in report["technical"]["cases"]}) >= 7
    assert report["technical"]["counts"]["reviewed_fields"] >= 40
    assert report["known_positive_recovery_proxy"]["measurements"]["pairs"] == 202
    # Verifica o transporte JSON sem permitir NaN em métricas indefinidas.
    json.dumps(report, allow_nan=False)
    bad = tmp_path / "different.csv"
    bad.write_text("CODIGO_MATERIAL\n1\n")
    with pytest.raises(ValueError, match="dataset"):
        sanitization_evaluation(str(bad), str(DATA / "03_padrao_cadastro_PDM.xlsx"))


def test_versioned_external_manifest_preserves_the_frozen_sources(tmp_path):
    from pipelines.evaluate_sanitization import frozen_data

    for name in ["manifest_v1.json", "merge_groups_v1.json", "merge_pairs_v1.json", "technical_v1.json"]:
        (tmp_path / name).write_bytes(frozen_data(name))
    manifest, groups, pairs = load_cohorts(tmp_path / "manifest_v1.json")
    assert manifest["cohort_id"] == "sanitization-development-v1"
    assert len(groups["reviewed"]) == 40 and len(pairs["pairs"]) == 95
    modified = json.loads((tmp_path / "manifest_v1.json").read_text())
    modified["schema_version"] = "unknown"
    (tmp_path / "manifest_v1.json").write_text(json.dumps(modified))
    with pytest.raises(ValueError, match="Versão"):
        load_cohorts(tmp_path / "manifest_v1.json")


@pytest.mark.parametrize("mutation", ["duplicate", "unpinned"])
def test_additional_cohorts_cannot_overwrite_results_or_bypass_source_hashes(tmp_path, mutation):
    from pipelines.evaluate_sanitization import frozen_data

    manifest = json.loads(frozen_data("manifest_v2.json"))
    if mutation == "duplicate":
        manifest["additional_group_cohorts"].append(manifest["additional_group_cohorts"][0])
    else:
        manifest["legacy_files"].pop(manifest["additional_group_cohorts"][0]["file"])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Coorte adicional"):
        load_cohorts(path)
