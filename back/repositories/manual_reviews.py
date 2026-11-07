"""Observações de pendência por material e execução, sem antes/depois ou alteração do mestre."""

import json
import uuid

from sqlalchemy import text

from domain.proposals import canonical_hash

NAMESPACE = uuid.UUID("7e93f2e6-123c-4bde-9c66-bd47c01ded98")


def save_manual_reviews(
    connection, records, analyzed, pending_by_code, context, catalog, corrector_name, enrichment=None
):
    datasets = (
        connection.execute(
            text("SELECT id::text FROM datasets WHERE tenant_id = :tenant"), {"tenant": context.tenant_id}
        )
        .scalars()
        .all()
    )
    if len(datasets) != 1:
        raise ValueError("A revisão manual exige exatamente um dataset por empresa no MVP")
    signature = context.checkpoint["analysis_signature"] + "|corrector:" + corrector_name
    if enrichment is not None:
        signature += "|internal:" + context.checkpoint["internal_sources_signature"]
    run_id = context.job_id or str(
        uuid.uuid5(
            NAMESPACE,
            canonical_hash(
                {
                    "dataset": datasets[0],
                    "rules": signature,
                    "records": [(r.code, r.version) for r in records],
                    "pending": pending_by_code,
                }
            ),
        )
    )
    by_code = {m.record.code: m for m in analyzed}
    completeness = (
        {
            item["material_code"]: {
                name: item[name]
                for name in (
                    "before",
                    "after_suggestions",
                    "suggestions",
                    "conflicts",
                    "classification",
                    "gaps",
                    "record_conflicts",
                    "assisted_candidates",
                )
            }
            for item in enrichment["results"]
        }
        if enrichment
        else {}
    )
    rows = []
    for record in records:
        reasons = pending_by_code.get(record.code)
        if not reasons:
            continue
        material = by_code[record.code]
        rows.append(
            {
                "id": str(uuid.uuid5(uuid.UUID(run_id), record.code)),
                "tenant": context.tenant_id,
                "run": run_id,
                "job": context.job_id,
                "dataset": datasets[0],
                "material": record.database_id,
                "version": record.version,
                "reasons": list(reasons),
                "signature": signature,
                "pdm": catalog.version,
                "hash": catalog.source_sha256,
                "observation": json.dumps(
                    {
                        "material_code": record.code,
                        "status": record.status,
                        "description": record.description,
                        "unit": record.unit,
                        "ncm": record.ncm or None,
                        "pdm_class_id": material.pdm_class_id,
                        "item_name": material.item_name,
                        "attributes": material.attributes,
                        "completeness": completeness.get(record.code),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    if rows:
        connection.execute(
            text("""INSERT INTO manual_reviews (id, tenant_id, run_id, job_id, dataset_id, material_id,
            expected_material_version, reasons, observation, rules_signature, pdm_version, pdm_source_sha256)
            VALUES (:id, :tenant, :run, :job, :dataset, :material, :version, :reasons,
                CAST(:observation AS jsonb), :signature, :pdm, :hash)
            ON CONFLICT (run_id, material_id) DO NOTHING"""),
            rows,
        )
    return run_id
