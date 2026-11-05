"""Reavalia a coorte fixa da #32; não sorteia uma amostra nova nem mede precisão da base inteira."""

import argparse
import hashlib
import json
from pathlib import Path

from domain.contracts import MergeProposal
from domain.identity import IDENTITY_RULES_VERSION
from domain.pdm_loader import load_pdm
from pipelines.identity_review import identity_review_report
from pipelines.sanitize import analyze_material, merge_proposals, read_csv_records
from repositories.candidates import get_candidate_repository
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository


def evaluate(sample: dict, proposals: list[MergeProposal], review: dict) -> dict:
    retained, removed, unreviewed = [], [], []
    for item in sample["reviewed"]:
        original = set(item["codes"])
        kept = [list(p.material_codes) for p in proposals if set(p.material_codes) <= original]
        result = {"original_codes": item["codes"], "same_item": item["same_item"], "retained_groups": kept}
        (retained if kept else removed).append(result)
    reviewed_groups = {tuple(codes) for item in retained for codes in item["retained_groups"]}
    cohort_codes = {code for item in sample["reviewed"] for code in item["codes"]}
    for proposal in proposals:
        if set(proposal.material_codes) & cohort_codes and proposal.material_codes not in reviewed_groups:
            unreviewed.append(list(proposal.material_codes))
    decided = [item for item in retained if item["same_item"] is not None]
    true_positives = sum(len(item["retained_groups"]) for item in decided if item["same_item"])
    false_positives = sum(len(item["retained_groups"]) for item in decided if not item["same_item"])
    return {
        "scope": "FIXED_REVIEWED_COHORT_NOT_POPULATION_PRECISION",
        "baseline_groups": len(sample["reviewed"]),
        "baseline_true": sum(item["same_item"] is True for item in sample["reviewed"]),
        "baseline_false": sum(item["same_item"] is False for item in sample["reviewed"]),
        "retained_true_groups": true_positives,
        "retained_false_groups": false_positives,
        "retained_precision": true_positives / (true_positives + false_positives) if decided else None,
        "retained": retained,
        "removed": removed,
        "unreviewed_changed_groups": unreviewed,
        "cohort_manual_review": [
            item for item in review["manual_review"] if item["evidence"]["material_code"] in cohort_codes
        ],
    }


def measure(csv_path: Path, workbook: Path, sample_path: Path) -> dict:
    catalog = load_pdm(workbook)
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    analyzed = [analyze_material(r, catalog, classifier, extractor) for r in read_csv_records(str(csv_path))]
    proposals = merge_proposals(analyzed, catalog, get_candidate_repository(), get_normalization_repository())
    review = identity_review_report(analyzed, catalog)
    return {
        "rules_version": IDENTITY_RULES_VERSION,
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "pdm_sha256": catalog.source_sha256,
        "sample_sha256": hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        "materials": len(analyzed),
        "merge_proposals": len(proposals),
        "equivalence_groups": len(review["equivalence_candidates"]),
        "manual_review_materials": len(review["manual_review"]),
        "evaluation": evaluate(json.loads(sample_path.read_text(encoding="utf-8")), proposals, review),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--pdm-workbook", required=True, type=Path)
    parser.add_argument(
        "--sample", type=Path, default=Path(__file__).parents[1] / "tests/fixtures/merge_identity_review_73.json"
    )
    args = parser.parse_args()
    print(json.dumps(measure(args.csv_path, args.pdm_workbook, args.sample), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
