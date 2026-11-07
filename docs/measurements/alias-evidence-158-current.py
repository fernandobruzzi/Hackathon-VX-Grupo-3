"""Compare extraction in isolated worktree processes; never writes challenge inputs."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    sys.path.insert(0, str(root / "back"))
    from domain.pdm_loader import load_pdm
    from domain.pdm_validator import validate_pdm
    from pipelines.import_orders import analyze_order, read_orders
    from pipelines.sanitize import analyze_material, read_csv_records
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    kit = root / "data/desafio01"
    inputs = [
        kit / name for name in ("01_base_materiais.csv", "02_pedidos_cadastro.csv", "03_padrao_cadastro_PDM.xlsx")
    ]
    hashes = {p.name: sha(p) for p in inputs}
    catalog = load_pdm(inputs[2])
    classifier = get_classification_repository(catalog)
    extractor = get_extraction_repository()
    materials = {}
    for record in read_csv_records(inputs[0]):
        item = analyze_material(record, catalog, classifier, extractor)
        validation = (
            validate_pdm(catalog, item.pdm_class_id, item.attributes, item_name=item.item_name)
            if item.pdm_class_id
            else None
        )
        materials[record.code] = {
            "class": item.pdm_class_id,
            "item": item.item_name,
            "attributes": item.attributes,
            "status": validation.status.value if validation else "OUT_OF_SCOPE",
            "identity_key": item.identity_key,
            "description": record.description,
        }
    orders = {}
    for record in read_orders(inputs[1].read_bytes()):
        item = analyze_order(record, catalog, classifier, extractor)
        orders[record.source_order_id] = {
            "class": item.pdm_class_id,
            "item": item.item_name,
            "attributes": item.attributes,
            "status": item.status,
            "identity_key": item.identity_key,
            "description": record.original_text,
        }
    assert hashes == {p.name: sha(p) for p in inputs}, "Challenge inputs changed during run"
    source_paths = [
        "back/repositories/extraction/rule_based_v1.py",
        "back/repositories/extraction/rule_based_v1_tables.py",
        "back/repositories/classification/aliases_v1.py",
    ]
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "implementation_state": "working_tree_sources_identified_by_sha256",
        "input_sha256": hashes,
        "source_sha256": {p: sha(root / p) for p in source_paths},
        "classifier": [classifier.name, classifier.revision],
        "extractor": [extractor.name, extractor.revision],
        "materials": materials,
        "orders": orders,
    }


def compare(before, after):
    assert before["input_sha256"] == after["input_sha256"], "Inputs differ between worktrees"
    report = {
        "kind": "DEVELOPMENT_COMPARISON",
        "independent_technical_review": False,
        "limits": "Coverage and semantic deltas only; no population precision or proposal measurement.",
        "input_sha256": before["input_sha256"],
        "before": {k: v for k, v in before.items() if k not in ("materials", "orders", "input_sha256")},
        "after": {k: v for k, v in after.items() if k not in ("materials", "orders", "input_sha256")},
    }
    for kind in ("materials", "orders"):
        changes = []
        for code, left in before[kind].items():
            right = after[kind][code]
            if left != right:
                names = left["attributes"].keys() | right["attributes"].keys()
                fields = {
                    name: {"before": left["attributes"].get(name), "after": right["attributes"].get(name)}
                    for name in sorted(names)
                    if left["attributes"].get(name) != right["attributes"].get(name)
                }
                changes.append({"id": code, "fields": fields, "before": left, "after": right})
        report[kind] = {"changes": changes}
        for label, rows in (("before", before[kind]), ("after", after[kind])):
            report[kind][label] = {
                "rows": len(rows),
                "filled_attributes": sum(len(row["attributes"]) for row in rows.values()),
                "statuses": dict(Counter(row["status"] for row in rows.values())),
                "identity_keys": sum(row["identity_key"] is not None for row in rows.values()),
            }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        result = snapshot(args.root.resolve())
    else:
        if not args.baseline_root:
            parser.error("--baseline-root is required")
        snapshots = []
        for label, root in (("before", args.baseline_root.resolve()), ("after", args.root.resolve())):
            output = args.output.with_suffix(f".{label}.tmp.json")
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--root",
                    str(root),
                    "--output",
                    str(output),
                ],
                env={**os.environ, "PYTHONPATH": str(root / "back")},
                check=True,
            )
            snapshots.append(json.loads(output.read_text()))
            output.unlink()
        result = compare(*snapshots)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
