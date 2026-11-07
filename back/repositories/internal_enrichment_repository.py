"""Integra fontes internas ao saneamento; publica propostas, nunca valores no mestre."""

import json
import os
from datetime import UTC, datetime

from sqlalchemy import text

from clients.storage import ObjectConflictError
from domain.proposals import canonical_hash
from pipelines.internal_enrichment import internal_report, read_sources
from repositories.enrichment_repository import persist_enrichment, plan_internal_enrichment


def _first_observation(store, dataset_id, signature, observed_at):
    metadata_key = f"runs/internal-enrichment/{dataset_id}/sources/{signature}.json"
    metadata = {"files_sha256": signature, "retrieved_at": observed_at.isoformat()}
    try:
        store.put_if_absent(metadata_key, json.dumps(metadata, sort_keys=True).encode())
    except ObjectConflictError:
        metadata = json.loads(store.get(metadata_key))
        if metadata["files_sha256"] != signature:
            raise ValueError("Metadados internos incompatíveis com os arquivos do dataset") from None
    return metadata["retrieved_at"]


def run_internal_enrichment(analyzed, catalog, context):
    store = context.store
    if store is None:
        from clients.storage import get_object_store

        store = get_object_store()
    with context.engine.begin() as connection:
        datasets = (
            connection.execute(
                text("SELECT id, files, imported_at FROM datasets WHERE tenant_id=:tenant"),
                {"tenant": context.tenant_id},
            )
            .mappings()
            .all()
        )
    if len(datasets) != 1:
        raise ValueError("Enriquecimento interno exige um dataset por empresa")
    dataset = datasets[0]
    files = dataset["files"] or []
    supplemental_key = os.environ.get("ENRICHMENT_INTERNAL_SOURCES_KEY")
    supplemental = None
    additional_sources = []
    if supplemental_key:
        from enrichment.internal_documents import load_supplemental_sources

        content = store.get(supplemental_key)
        additional_sources = load_supplemental_sources(content, str(dataset["id"]), catalog, supplemental_key)
        supplemental = {"object_key": supplemental_key, "sha256": additional_sources[0].sha256}
    signature = (
        canonical_hash({"files": files, "supplemental": supplemental}) if supplemental else canonical_hash(files)
    )
    previous = context.checkpoint.get("internal_sources_signature")
    if previous and previous != signature:
        raise ValueError("Fontes internas mudaram durante o job. Crie um novo job.")
    context.checkpoint["internal_sources_signature"] = signature
    # A primeira observação dos mesmos bytes permanece estável em reimportações e resets.
    original_date = _first_observation(store, dataset["id"], canonical_hash(files), dataset["imported_at"])
    supplemental_date = (
        _first_observation(store, dataset["id"], supplemental["sha256"], datetime.now(UTC)) if supplemental else None
    )
    sources, unavailable = read_sources(files, store, catalog)
    sources += additional_sources
    from enrichment.assisted_extraction import AssistedExtractor

    assistant = AssistedExtractor.from_environment(catalog)
    if previous_usage := context.checkpoint.get("assisted_extraction_usage"):
        assistant.restore_usage(previous_usage)

    def save_usage(usage):
        context.checkpoint["assisted_extraction_usage"] = usage
        if context.job_id:
            from repositories.batch_repository import update_job

            with context.engine.begin() as connection:
                update_job(connection, context.job_id, context.checkpoint)

    assistant.on_usage = save_usage
    report = internal_report(analyzed, sources, catalog, dataset["id"], assistant=assistant)
    save_usage(assistant.usage)
    report["unavailable_sources"] = unavailable
    report["source_files_sha256"] = canonical_hash(files)
    report["supplemental_source"] = supplemental
    report["material_versions"] = {m.record.code: m.record.version for m in analyzed}
    for item in report["results"]:
        for evidence in item["evidence"]:
            evidence["retrieved_at"] = (
                supplemental_date if supplemental and evidence["object_key"] == supplemental_key else original_date
            )
    digest = canonical_hash(report)
    key = f"runs/internal-enrichment/{dataset['id']}/{digest}.json"
    store.put_if_absent(key, json.dumps(report, sort_keys=True, ensure_ascii=False).encode())
    published = []
    with context.engine.begin() as connection:
        if context.job_id:
            from repositories.batch_repository import update_job

            update_job(connection, context.job_id, context.checkpoint)
        for item in report["results"]:
            if not item["suggestions"]:
                continue
            material = (
                connection.execute(
                    text("SELECT * FROM materials_master WHERE tenant_id=:tenant AND material_code=:code"),
                    {"tenant": context.tenant_id, "code": item["material_code"]},
                )
                .mappings()
                .one()
            )
            if material["version"] != report["material_versions"][item["material_code"]]:
                raise ValueError("Material mudou durante o enriquecimento. Execute um novo job.")
            if material["status"] != "ATIVO":
                continue
            item_supplemental = (
                supplemental
                if any(
                    evidence["object_key"] == supplemental_key and evidence["attribute"] in item["suggestions"]
                    for evidence in item["evidence"]
                )
                else None
            )
            local_report = {
                "pipeline_version": report["pipeline_version"],
                "dataset_id": str(dataset["id"]),
                "source_files_sha256": canonical_hash(files),
                "supplemental_source": item_supplemental,
                "material_version": material["version"],
                "result": {
                    key: value
                    for key, value in item.items()
                    if key not in {"assisted_candidates", "assisted_extraction"}
                },
            }
            local_key = f"runs/internal-enrichment/{dataset['id']}/materials/{canonical_hash(local_report)}.json"
            store.put_if_absent(local_key, json.dumps(local_report, sort_keys=True, ensure_ascii=False).encode())
            changes, baseline = plan_internal_enrichment(
                dict(material) | {"dataset_id": dataset["id"]}, item, catalog, canonical_hash(files), local_key
            )
            if item_supplemental:
                changes["enrichment_context"]["supplemental_source"] = item_supplemental
            if not changes["changes"]:
                continue
            published.append(
                persist_enrichment(
                    connection,
                    material,
                    item,
                    changes,
                    baseline,
                    catalog,
                    context.tenant_id,
                    local_key,
                    context.job_id,
                    include_inserted=True,
                )
            )
        # Fontes internas e externas podem propor campos diferentes para o mesmo material.
        # Não substituir revisões independentes: a versão do material é conferida na aprovação.
    return {
        "report_key": key,
        "summary": report["summary"],
        "assisted_usage": report["assisted_usage"],
        "unavailable_sources": unavailable,
        "proposals": len(published),
        "inserted": sum(p["inserted"] for p in published),
        "proposal_ids": [p["proposal_id"] for p in published],
        "material_codes": [p["material_code"] for p in published],
    }
