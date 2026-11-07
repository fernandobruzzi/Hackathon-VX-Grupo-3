"""Mede elegibilidade na base; não escreve nem estima precisão dos resultados."""

import argparse
import json
import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from domain.automatic_corrections import POLICY_VERSION
from domain.pdm_loader import load_pdm
from pipelines.automatic_corrections import assess_record, current_rules
from pipelines.corrections import correction_proposals
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository
from repositories.proposal_payload import approval_payload
from repositories.text_loss import get_text_loss_repository


def candidates(record, catalog):
    analyzed = analyze_material(record, catalog, get_classification_repository(catalog), get_extraction_repository())
    corrector = get_correction_repository()
    result = corrector.correct(analyzed, catalog, get_normalization_repository())
    return correction_proposals(analyzed, result, catalog, corrector.name, get_text_loss_repository())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--pdm-workbook", required=True, type=Path)
    args = parser.parse_args()
    catalog = load_pdm(args.pdm_workbook)
    counts, reasons, examples = Counter(), Counter(), {}
    size = 0
    dataset = str(uuid5(NAMESPACE_URL, "measurement"))
    for source in read_csv_records(args.csv):
        size += 1
        record = replace(source, database_id=str(uuid5(NAMESPACE_URL, source.code)))
        for proposal in candidates(record, catalog):
            _, payload, _ = approval_payload(proposal, {record.code: record.database_id}, dataset)
            verdict = assess_record(
                catalog,
                record,
                proposal.proposal_type,
                payload,
                {"unit": record.unit, "ncm": record.ncm or None, "attributes": {}},
                dataset,
            )
            key = f"{proposal.proposal_type}:{'ELIGIBLE' if verdict.eligible else 'REVIEW'}"
            counts[key] += 1
            for reason in verdict.reasons:
                reasons[reason] += 1
                sample_key = key + ":" + reason
                if len(examples.setdefault(sample_key, [])) < 3:
                    examples[sample_key].append(
                        {
                            "code": record.code,
                            "original": record.description,
                            "changes": payload["changes"],
                            "attributes": verdict.evidence["attributes"],
                        }
                    )
    commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    print(
        json.dumps(
            {
                "commit": commit,
                "policy": POLICY_VERSION,
                "rules": current_rules(catalog),
                "pdm_version": catalog.version,
                "pdm_sha256": catalog.source_sha256,
                "records": size,
                "counts": dict(counts),
                "reasons": dict(reasons),
                "examples": examples,
                "limits": "Elegibilidade de domínio; a API valida estado, escopo, colisões e efeitos em transação. "
                "Contagens não medem precisão; exemplos exigem revisão humana.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
