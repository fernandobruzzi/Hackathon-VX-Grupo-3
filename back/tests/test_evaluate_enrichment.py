"""A revisão mede atributos congelados e nunca autoriza a publicação."""

from copy import deepcopy

import pytest

from domain.proposals import canonical_hash
from pipelines.evaluate_enrichment import create_review_packet, evaluate_packet


@pytest.fixture
def report():
    return {
        "pipeline_version": "internal-enrichment-v1",
        "dataset_id": "dataset",
        "pdm_version": "v1",
        "pdm_source_sha256": "a" * 64,
        "results": [
            {
                "material_code": "100",
                "pdm_class_id": "PDM100",
                "original": {
                    "description": "FILTRO OLEO; FABRICANTE: ACME; REFERENCIA: LF100",
                    "short_description": "FILTRO OLEO ACME LF100",
                    "manufacturer": "ACME",
                    "reference": "LF100",
                    "attributes": {"FABRICANTE": "ACME", "REFERENCIA FABRICANTE": "LF100"},
                },
                "suggestions": {"ALTURA": "100MM", "MATERIAL": "ACO"},
                "evidence": [
                    {
                        "id": "height",
                        "attribute": "ALTURA",
                        "proposed_value": "100MM",
                        "source_url": "dataset://dataset/base#donor",
                        "source_excerpt": "ALTURA: 100MM",
                        "source_sha256": "b" * 64,
                    },
                    {
                        "id": "material",
                        "attribute": "MATERIAL",
                        "proposed_value": "ACO",
                        "source_excerpt": "MATERIAL: ACO",
                    },
                ],
                "assisted_candidates": [
                    {
                        "attribute": "DIAMETRO",
                        "value": "10MM",
                        "source_field": "description",
                        "excerpt": "DIAMETRO: 10MM",
                    }
                ],
            }
        ],
    }


def reviews(packet, labels):
    return {
        "packet_sha256": packet["packet_sha256"],
        "reviews": [
            {"case_id": case["id"], "author": "Técnico A", "label": label, "evidence": ["Trecho conferido."]}
            for case, label in zip(packet["cases"], labels, strict=True)
        ],
    }


def resign(packet):
    packet["packet_sha256"] = canonical_hash({k: v for k, v in packet.items() if k != "packet_sha256"})


def test_packet_is_repeatable_freezes_each_attribute_and_has_no_labels(report):
    packet = create_review_packet(report, seed=42, sample_size=2)
    assert packet == create_review_packet(report, seed=42, sample_size=2)
    assert packet["report_sha256"] == canonical_hash(report)
    assert packet["sampling"]["population_size"] == 3
    assert len(packet["cases"]) == 2
    assert len(packet["sampling"]["frame"]) == 3
    assert packet["authorizes_apply"] is False
    for case in packet["cases"]:
        assert "label" not in case
        assert case["evidence"]
        assert case["case_sha256"] == canonical_hash({k: v for k, v in case.items() if k != "case_sha256"})


def test_packet_contains_documentary_and_assisted_candidates_as_distinct_cases(report):
    packet = create_review_packet(report)
    assert len(packet["cases"]) == 3
    kinds = {case["kind"] for case in packet["cases"]}
    assert kinds == {"INTERNAL_SUGGESTION", "ASSISTED_CANDIDATE"}
    assisted = next(case for case in packet["cases"] if case["kind"] == "ASSISTED_CANDIDATE")
    assert assisted["evidence"] == [{"source_field": "description", "source_excerpt": "DIAMETRO: 10MM"}]


def test_each_candidate_freezes_the_target_original_and_baseline(report):
    packet = create_review_packet(report)
    original = deepcopy(report["results"][0]["original"])
    assert all(case["target"] == original for case in packet["cases"])
    report["results"][0]["original"]["attributes"]["FABRICANTE"] = "OUTRO"
    assert all(case["target"] == original for case in packet["cases"])
    packet["cases"][0]["target"]["attributes"]["FABRICANTE"] = "ALTERADO"
    assert packet["cases"][1]["target"] == original
    resign(packet)
    with pytest.raises(ValueError, match="Caso"):
        evaluate_packet(packet, {"packet_sha256": packet["packet_sha256"], "reviews": []})


def test_evaluation_counts_missing_inconclusive_and_decided_separately(report):
    packet = create_review_packet(report)
    labels = ["SUPPORTED", "UNSUPPORTED", "INCONCLUSIVE"]
    result = evaluate_packet(packet, reviews(packet, labels))
    assert result["counts"] == {"selected": 3, "reviewed": 3, "supported": 1, "unsupported": 1, "inconclusive": 1}
    assert result["decided_precision"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert result["decided_precision_interval"]["method"] == "WILSON"
    assert result["authorizes_apply"] is False
    assert result["independent_review"] is False
    assert result["by_attribute"]
    assert result["by_class"]


def test_blank_or_partially_reviewed_packet_never_claims_precision(report):
    packet = create_review_packet(report)
    result = evaluate_packet(packet, {"packet_sha256": packet["packet_sha256"], "reviews": []})
    assert result["counts"]["inconclusive"] == 3
    assert result["review_coverage"]["value"] == 0
    assert result["decided_precision"]["value"] is None
    assert result["decided_precision_interval"] is None


@pytest.mark.parametrize("label", ["UNSUPPORTED", "INCONCLUSIVE"])
def test_disagreement_and_inconclusive_reviews_never_become_majority_votes(report, label):
    packet = create_review_packet(report, sample_size=1)
    data = reviews(packet, ["SUPPORTED"])
    data["reviews"].append({**data["reviews"][0], "author": "Técnico B", "label": label})
    result = evaluate_packet(packet, data)
    assert result["counts"]["supported"] == 0
    assert result["counts"]["inconclusive"] == 1
    assert result["cases"][0]["status"] in {"DISAGREEMENT", "INCONCLUSIVE"}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["cases"][0].update(value="999MM"),
        lambda p: p["sampling"].update(seed=100),
        lambda p: p["cases"].append(p["cases"][0]),
        lambda p: p.update(report_sha256="f" * 64),
    ],
)
def test_changed_packet_is_rejected(report, mutation):
    packet = create_review_packet(report)
    data = reviews(packet, ["SUPPORTED"] * 3)
    mutation(packet)
    with pytest.raises(ValueError, match="[Pp]acote"):
        evaluate_packet(packet, data)


def test_resigned_changed_case_is_rejected_by_case_hash(report):
    packet = create_review_packet(report)
    packet["cases"][0]["value"] = "999MM"
    resign(packet)
    with pytest.raises(ValueError, match="[Cc]aso"):
        evaluate_packet(packet, {"packet_sha256": packet["packet_sha256"], "reviews": []})


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["reviews"].append(r["reviews"][0]),
        lambda r: r["reviews"][0].update(case_id="unknown"),
        lambda r: r["reviews"][0].update(label="APPROVED"),
        lambda r: r["reviews"][0].update(author="  "),
        lambda r: r["reviews"][0].update(evidence=[]),
        lambda r: r.update(packet_sha256="f" * 64),
    ],
)
def test_bad_reviews_cannot_supply_a_metric(report, change):
    packet = create_review_packet(report, sample_size=1)
    data = reviews(packet, ["SUPPORTED"])
    change(data)
    with pytest.raises(ValueError):
        evaluate_packet(packet, data)


def test_duplicate_report_rows_or_assisted_candidates_are_rejected(report):
    duplicate = deepcopy(report)
    duplicate["results"].append(deepcopy(duplicate["results"][0]))
    with pytest.raises(ValueError, match="repetid"):
        create_review_packet(duplicate)
    duplicate = deepcopy(report)
    duplicate["results"][0]["assisted_candidates"] *= 2
    with pytest.raises(ValueError, match="repetid"):
        create_review_packet(duplicate)


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_sample_size_must_be_a_positive_integer(report, size):
    with pytest.raises(ValueError):
        create_review_packet(report, sample_size=size)


def test_empty_candidate_population_has_defined_denominators():
    packet = create_review_packet({"results": []})
    result = evaluate_packet(packet, {"packet_sha256": packet["packet_sha256"], "reviews": []})
    assert result["counts"]["selected"] == 0
    assert result["sampling_coverage"]["value"] is None
    assert result["decided_precision"]["value"] is None


def test_authors_are_unique_despite_case_and_spacing(report):
    packet = create_review_packet(report, sample_size=1)
    data = reviews(packet, ["SUPPORTED"])
    data["reviews"].append({**data["reviews"][0], "author": "  TÉCNICO a  "})
    with pytest.raises(ValueError, match="autor"):
        evaluate_packet(packet, data)


def test_reviewer_cannot_turn_the_packet_into_publication_authority(report):
    packet = create_review_packet(report)
    packet["authorizes_apply"] = True
    resign(packet)
    with pytest.raises(ValueError, match="Pacote"):
        evaluate_packet(packet, {"packet_sha256": packet["packet_sha256"], "reviews": []})


def test_results_do_not_retain_mutable_references_to_inputs(report):
    original = deepcopy(report)
    packet = create_review_packet(report)
    data = reviews(packet, ["SUPPORTED"] * 3)
    result = evaluate_packet(packet, data)
    result["cases"][0]["evidence"].clear()
    result["cases"][0]["reviews"][0]["evidence"].clear()
    assert report == original
    assert packet["cases"][0]["evidence"]
    assert data["reviews"][0]["evidence"]


@pytest.mark.parametrize("bad_review", [None, [], {"case_id": "x", "author": "A", "label": [], "evidence": []}])
def test_malformed_review_json_is_a_validation_error(report, bad_review):
    packet = create_review_packet(report)
    with pytest.raises(ValueError):
        evaluate_packet(packet, {"packet_sha256": packet["packet_sha256"], "reviews": [bad_review]})
