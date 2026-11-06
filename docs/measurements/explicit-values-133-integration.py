"""Compare only the extractor on the same current pipelines; writes a development report."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def delta_fields(before, after):
    return {
        name: {
            "kind": "added" if name not in before else "removed" if name not in after else "changed",
            "before": before.get(name),
            "after": after.get(name),
        }
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "back"))

    from domain.identity import IDENTITY_RULES_VERSION, material_review_reasons
    from domain.identity_decision import decide_identity
    from domain.pdm_loader import load_pdm
    from domain.pdm_validator import validate_pdm
    from pipelines.corrections import propose_corrections
    from pipelines.evaluate_sanitization import cohort_data, compare_merges, load_cohorts
    from pipelines.identity_review import identity_review_report
    from pipelines.import_orders import analyze_order, read_orders
    from pipelines.measure_merge_identity import evaluate as evaluate_fixed_identity_cohort
    from pipelines.ncm_corrections import propose_ncm_corrections
    from pipelines.sanitize import analysis_signature, analyze_material, merge_proposals, read_csv_records
    from repositories.candidates import get_candidate_repository
    from repositories.classification import get_classification_repository
    from repositories.corrections import get_correction_repository
    from repositories.extraction import get_extraction_repository
    from repositories.normalization import get_normalization_repository

    extractor_path = "back/repositories/extraction/rule_based_v1.py"
    before_bytes = subprocess.check_output(["git", "show", f"{args.baseline}:{extractor_path}"], cwd=root)
    before_path = Path("/tmp/explicit_values_133_baseline_extractor.py")
    before_path.write_bytes(before_bytes)
    spec = importlib.util.spec_from_file_location("explicit_values_133_baseline_extractor", before_path)
    baseline_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline_module)
    before_extractor = baseline_module.RuleBasedV1ExtractionRepository()
    after_extractor = get_extraction_repository()

    kit = root / "data/desafio01"
    csv_path = kit / "01_base_materiais.csv"
    order_path = kit / "02_pedidos_cadastro.csv"
    workbook = kit / "03_padrao_cadastro_PDM.xlsx"
    catalog = load_pdm(workbook)
    classifier = get_classification_repository(catalog)
    records = read_csv_records(str(csv_path))
    orders = read_orders(order_path.read_bytes())
    normalizer = get_normalization_repository()
    corrector = get_correction_repository()
    candidates = get_candidate_repository()
    manifest, historical_groups, historical_pairs = load_cohorts()
    fixed_sample_path = root / "back/tests/fixtures/merge_identity_review_73.json"
    fixed_sample = json.loads(fixed_sample_path.read_text())

    def run(label, extractor):
        start = time.monotonic()
        print(f"{label}: analyzing {len(records)} materials", flush=True)
        analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
        counts = Counter()
        for material in analyzed:
            if material.pdm_class_id is None:
                counts["OUT_OF_SCOPE"] += 1
                continue
            validation = validate_pdm(catalog, material.pdm_class_id, material.attributes, item_name=material.item_name)
            counts[validation.status.value] += 1
            counts["filled_attributes"] += len(material.attributes)
            counts["identity_keys"] += material.identity_key is not None
        print(f"{label}: building proposals", flush=True)
        merges = merge_proposals(analyzed, catalog, candidates, normalizer)
        corrections, pending = propose_corrections(analyzed, catalog, normalizer, corrector)
        ncm = propose_ncm_corrections(analyzed, catalog)
        corrections += ncm
        correction_counts = Counter(proposal.proposal_type for proposal in corrections)
        free = Counter(proposal.proposal_type for proposal in corrections if not proposal.conflicts)
        correction_fields = Counter(
            change["field"] for proposal in corrections for change in proposal.changeset["changes"]
        )
        historical = compare_merges(merges, historical_groups, historical_pairs, manifest["group_review_additions"])
        additional = {}
        for cohort in manifest.get("additional_group_cohorts", []):
            groups = json.loads(cohort_data(cohort["file"]))
            additional[cohort["id"]] = {
                "source_sha256": sha(cohort_data(cohort["file"])),
                **compare_merges(merges, groups, historical_pairs, cohort["review_additions"])["groups"],
            }
        order_analyses = [analyze_order(order, catalog, classifier, extractor) for order in orders]
        identity_review = identity_review_report(analyzed, catalog)
        print(f"{label}: complete in {time.monotonic() - start:.2f}s", flush=True)
        return {
            "materials": analyzed,
            "material_counts": dict(counts),
            "orders": order_analyses,
            "order_statuses": dict(Counter(order.status for order in order_analyses)),
            "merges": merges,
            "corrections": corrections,
            "proposal_counts": {
                "merges": len(merges),
                "merge_materials": len({code for proposal in merges for code in proposal.material_codes}),
                "conflict_free_merges": sum(not proposal.conflicts for proposal in merges),
                "corrections": dict(correction_counts),
                "conflict_free_corrections": dict(free),
                "correction_fields": dict(correction_fields),
                "pending_reasons": dict(pending),
            },
            "historical_cohorts": {"original": historical, "additional_groups": additional},
            "fixed_identity_cohort": evaluate_fixed_identity_cohort(fixed_sample, merges, identity_review),
            "identity_review_counts": {k: len(v) for k, v in identity_review.items() if isinstance(v, list)},
        }

    before = run("before", before_extractor)
    after = run("after", after_extractor)
    materials_changes = []
    material_deltas = {"added": Counter(), "removed": Counter(), "changed": Counter()}
    for left, right in zip(before["materials"], after["materials"], strict=True):
        fields = delta_fields(left.attributes, right.attributes)
        for name, change in fields.items():
            material_deltas[change["kind"]][name] += 1
        if fields or left.identity_key != right.identity_key:
            materials_changes.append(
                {
                    "code": left.record.code,
                    "class": left.pdm_class_id,
                    "description": left.record.description,
                    "fields": fields,
                    "identity_before": left.identity_key,
                    "identity_after": right.identity_key,
                }
            )
    order_changes = []
    order_deltas = {"added": Counter(), "removed": Counter(), "changed": Counter()}
    for row, left, right in zip(orders, before["orders"], after["orders"], strict=True):
        fields = delta_fields(left.attributes, right.attributes)
        for name, change in fields.items():
            order_deltas[change["kind"]][name] += 1
        if left != right:
            order_changes.append(
                {"id": row.source_order_id, "before": asdict(left), "after": asdict(right), "fields": fields}
            )
    merges_before = {proposal.material_codes for proposal in before["merges"]}
    merges_after = {proposal.material_codes for proposal in after["merges"]}
    correction_deltas = {}
    for proposal_type in sorted({p.proposal_type for p in before["corrections"] + after["corrections"]}):
        left = {p.material_codes for p in before["corrections"] if p.proposal_type == proposal_type}
        right = {p.material_codes for p in after["corrections"] if p.proposal_type == proposal_type}
        correction_deltas[proposal_type] = {"removed": sorted(left - right), "added": sorted(right - left)}

    shared_paths = [
        "back/domain/contracts.py",
        "back/domain/identity.py",
        "back/domain/identity_decision.py",
        "back/domain/pdm_validator.py",
        "back/pipelines/sanitize.py",
        "back/pipelines/full_run.py",
        "back/pipelines/identity_review.py",
        "back/pipelines/import_orders.py",
        "back/pipelines/corrections.py",
        "back/pipelines/ncm_corrections.py",
        "back/pipelines/evaluate_sanitization.py",
        "back/pipelines/measure_merge_identity.py",
        "back/repositories/classification/aliases_v1.py",
        "back/repositories/classification/rule_based_v1.py",
        "back/repositories/extraction/rule_based_v1_tables.py",
        "back/repositories/candidates/exact_identity_v1.py",
    ]

    def tracked_evidence(run_result, codes):
        materials = {material.record.code: material for material in run_result["materials"]}
        selected = [materials[code] for code in codes]
        evidence = {
            "materials": [
                {
                    "code": material.record.code,
                    "description": material.record.description,
                    "pdm_class_id": material.pdm_class_id,
                    "item_name": material.item_name,
                    "attributes": material.attributes,
                    "identity_key": material.identity_key,
                    "identity_review_reasons": material_review_reasons(material, catalog.classes[material.pdm_class_id])
                    if material.pdm_class_id is not None
                    else ["CLASSE_NAO_CONFIRMADA"],
                }
                for material in selected
            ],
            "merge_groups": [
                proposal.material_codes
                for proposal in run_result["merges"]
                if set(codes) & set(proposal.material_codes)
            ],
        }
        if len(selected) == 2:
            evidence["shared_identity_decision"] = asdict(decide_identity(catalog, *selected))
        return evidence

    tracked_codes = [("16490712", "25536305"), ("13563770", "29792424"), ("28611241",)]
    report = {
        "schema": "explicit-values-integration-development-diff-v1",
        "baseline_commit": args.baseline,
        "method": (
            "Same current classifier, PDM, identity rules and proposal builders; "
            "only extractor varies. No database writes."
        ),
        "baseline_extractor_sha256": sha(before_bytes),
        "candidate_extractor_sha256": sha((root / extractor_path).read_bytes()),
        "measurement_script_sha256": sha(Path(__file__).read_bytes()),
        "revisions": {"before": before_extractor.revision, "after": after_extractor.revision},
        "identity_rules_version": IDENTITY_RULES_VERSION,
        "analysis_signatures": {
            "before": analysis_signature(catalog, classifier, before_extractor),
            "after": analysis_signature(catalog, classifier, after_extractor),
        },
        "inputs_sha256": {path.name: sha(path.read_bytes()) for path in [csv_path, order_path, workbook]},
        "shared_implementations_sha256": {path: sha((root / path).read_bytes()) for path in shared_paths},
        "materials": {
            "total": len(records),
            "before": before["material_counts"],
            "after": after["material_counts"],
            "changed": len(materials_changes),
            "field_deltas": {k: dict(v) for k, v in material_deltas.items()},
            "changes": materials_changes,
        },
        "orders": {
            "total": len(orders),
            "statuses": {"before": before["order_statuses"], "after": after["order_statuses"]},
            "changed": len(order_changes),
            "field_deltas": {k: dict(v) for k, v in order_deltas.items()},
            "changes": order_changes,
        },
        "proposals": {"before": before["proposal_counts"], "after": after["proposal_counts"]},
        "merge_groups_removed": sorted(merges_before - merges_after),
        "merge_groups_added": sorted(merges_after - merges_before),
        "correction_materials_delta": correction_deltas,
        "ncm_correction_materials_removed": correction_deltas["NCM_CORRECTION"]["removed"],
        "ncm_correction_materials_added": correction_deltas["NCM_CORRECTION"]["added"],
        "historical_cohorts": {"before": before["historical_cohorts"], "after": after["historical_cohorts"]},
        "fixed_identity_cohort": {
            "source_sha256": sha(fixed_sample_path.read_bytes()),
            "before": before["fixed_identity_cohort"],
            "after": after["fixed_identity_cohort"],
        },
        "identity_review_counts": {
            "before": before["identity_review_counts"],
            "after": after["identity_review_counts"],
        },
        "tracked_conservative_regressions": [
            {
                "codes": codes,
                "before": tracked_evidence(before, codes),
                "after": tracked_evidence(after, codes),
            }
            for codes in tracked_codes
        ],
        "limitations": [
            "No new technical labels, independent review or population precision.",
            "Removed fields are abstentions, not automatically confirmed technical errors.",
            "Historical labels, frozen cohort files and prior measurements remain unchanged.",
            "Order status counts are pre-database analysis; matching existing master materials is handled by the API.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "materials_before": report["materials"]["before"],
                "materials_after": report["materials"]["after"],
                "changed": report["materials"]["changed"],
                "field_deltas": report["materials"]["field_deltas"],
                "orders": report["orders"]["statuses"],
                "proposals": report["proposals"],
                "removed_merge_groups": len(report["merge_groups_removed"]),
                "added_merge_groups": len(report["merge_groups_added"]),
                "ncm_removed": len(report["ncm_correction_materials_removed"]),
                "ncm_added": len(report["ncm_correction_materials_added"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
