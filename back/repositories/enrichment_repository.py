"""Adapta o relatório imutável ao contrato de aprovação; não escreve no cadastro mestre."""

import hashlib
import json
import os
import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import create_engine, text

from clients.ncm_snapshot_store import load_configured_ncm_snapshot
from clients.storage import ObjectStore
from domain.enrichment_rules import (
    check_simulated_evidence,
    evidence_hash,
    extraction_signature,
    original_attributes,
    original_hash,
    original_item_name,
)
from domain.ncm_rules import check_ncm_consistency, requires_snapshot_fiscal_review
from domain.pdm_validator import is_valid_value
from domain.proposals import proposal_hash
from enrichment.catalog import REAL_PRODUCTS
from pipelines.enrich_real_products import _manifest, run_enrichment


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def replay_report(store, report_key, catalog):
    content = store.get(report_key)
    if len(content) > 10_000_000:
        raise ValueError("Relatorio excede o limite")
    report = json.loads(content)
    digest = hashlib.sha256(_json(report).encode()).hexdigest()
    if report_key.rsplit("/", 1)[-1] != f"{digest}.json":
        raise ValueError("Hash do relatorio divergente")
    codes = [item["material_code"] for item in report["results"]]
    if len(codes) != len(set(codes)) or not set(codes) <= REAL_PRODUCTS.keys():
        raise ValueError("Relatorio fora dos 15 codigos reais")
    manifest, _, manifest_hash = _manifest(store, report["input_manifest_key"], catalog)
    if manifest_hash != report["input_manifest_sha256"]:
        raise ValueError("Manifesto diferente do relatorio")
    # Reextrai dos bytes preservados com o repositório do servidor. Não confia nos valores do JSON recebido.
    replay = run_enrichment(
        store, report["input_manifest_key"], catalog, material_codes=codes, evidence_manifest_key=report_key
    )
    check_simulated_evidence(replay["simulated"])
    return manifest, replay


def plan_enrichment(material, item, catalog, manifest_hash, report_key):
    code = material["material_code"]
    if code not in REAL_PRODUCTS or item["material_code"] != code:
        raise ValueError("Proposta fora dos 15 produtos reais ou identidade divergente")
    product = REAL_PRODUCTS[code]
    baseline = original_attributes(catalog, product.pdm_class_id, material)
    grouped = defaultdict(list)
    for source in item["evidence"]:
        grouped[source["attribute"]].append(source)
    after = dict(baseline)
    divergent, blocked, changes = [], [], []
    definitions = {a.name: a for a in catalog.classes[product.pdm_class_id].attributes}
    for name, sources in sorted(grouped.items()):
        candidates = {source["proposed_value"] for source in sources}
        current = baseline.get(name)
        if len(candidates) != 1 or (current and current not in candidates):
            divergent.append(name)
            continue
        candidate = next(iter(candidates))
        if name not in definitions or not is_valid_value(definitions[name], candidate):
            blocked.append(name)
            continue
        if not current:
            after[name] = candidate
            changes.append({"field": name, "before": None, "after": candidate, "source": sources[0]["source_url"]})
    context = {
        "schema_version": "enrichment-v1",
        "report_key": report_key,
        "manifest_sha256": manifest_hash,
        "original_hash": original_hash(material),
        "extraction_signature": extraction_signature(catalog),
        "divergent_attributes": divergent,
        "blocked_attributes": blocked,
    }
    conflicts = [] if changes else ["Nenhum atributo sem divergencia ou incompatibilidade PDM pode ser aplicado."]
    if material.get("pdm_class_id") and material["pdm_class_id"] != product.pdm_class_id:
        conflicts.append("Classe atual diverge da classe do produto real: exige nova revisao.")
    item_name = original_item_name(catalog, product.pdm_class_id, material)
    if item_name is None:
        conflicts.append("Nome do item nao foi confirmado na descricao original.")
    return {
        "schema_version": "proposal-v1",
        "dataset_id": str(material["dataset_id"]),
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "primary_material_code": code,
        "after": {
            "pdm_class_id": product.pdm_class_id,
            "item_name": item_name,
            "attributes": after,
            "unit": material["unit"],
            "ncm": material["ncm"],
        },
        "sources": {
            "pdm_class_id": "Identidade original dos 15 produtos do manifesto",
            "attributes": f"{extraction_signature(catalog)}; atributos originais e evidencias externas registradas",
            "unit": "Unidade atual preservada",
            "ncm": "NCM atual preservado",
        },
        "conflicts": conflicts,
        "changes": changes,
        "enrichment_context": context,
    }, baseline


def publish_enrichment(store: ObjectStore, report_key: str, catalog, database_url: str | None = None) -> dict:
    manifest, report = replay_report(store, report_key, catalog)
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("Defina DATABASE_URL com a credencial batch_user")
    engine = create_engine(url)
    published = []
    try:
        with engine.begin() as connection:
            dataset = (
                connection.execute(
                    text("SELECT id,tenant_id,files,real_material_codes FROM datasets WHERE id=:id"),
                    {"id": manifest["dataset_id"]},
                )
                .mappings()
                .one()
            )
            if (
                str(dataset["tenant_id"]) != manifest["tenant_id"]
                or set(dataset["real_material_codes"]) != set(REAL_PRODUCTS)
                or dataset["files"] != manifest["files"]
            ):
                raise ValueError("Dataset nao corresponde ao manifesto original")
            for item in report["results"]:
                if not item["evidence"]:
                    continue
                material = dict(
                    connection.execute(
                        text("SELECT * FROM materials_master WHERE tenant_id=:tenant AND material_code=:code"),
                        {"tenant": manifest["tenant_id"], "code": item["material_code"]},
                    )
                    .mappings()
                    .one()
                )
                if material["status"] != "ATIVO":
                    continue
                material["dataset_id"] = dataset["id"]
                changes, baseline = plan_enrichment(
                    material, item, catalog, report["input_manifest_sha256"], report_key
                )
                if not changes["changes"]:
                    previous = connection.execute(
                        text("""SELECT id FROM sanitization_proposals
                        WHERE tenant_id=:tenant AND primary_material_id=:material AND proposal_type='ENRICHMENT'
                          AND changeset->'enrichment_context'->>'report_key'=:report
                        ORDER BY created_at DESC LIMIT 1"""),
                        {"tenant": manifest["tenant_id"], "material": str(material["id"]), "report": report_key},
                    ).scalar()
                    if previous:
                        published.append({"material_code": item["material_code"], "proposal_id": str(previous)})
                        continue
                evidence_ids, hashes = [], {}
                for evidence in item["evidence"]:
                    source = {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{material['id']}|{evidence['id']}")),
                        "tenant_id": manifest["tenant_id"],
                        "material_id": str(material["id"]),
                        "attribute_name": evidence["attribute"],
                        "proposed_value": evidence["proposed_value"],
                        "source_url": evidence["source_url"],
                        "source_title": evidence["source_title"],
                        "source_excerpt": evidence["source_excerpt"],
                        "source_page": str(evidence["source_page"]) if evidence["source_page"] is not None else None,
                        "source_sha256": evidence["source_sha256"],
                        "s3_object_key": evidence["object_key"],
                        "retrieved_at": datetime.fromisoformat(evidence["retrieved_at"].replace("Z", "+00:00")),
                        "confidence_level": evidence["confidence_level"],
                        "confidence_basis": [
                            *evidence["confidence_basis"],
                            "EXTRACTION_RULE:" + evidence["extraction_rule"],
                        ],
                    }
                    connection.execute(
                        text("""INSERT INTO enrichment_sources
                        (id,tenant_id,material_id,attribute_name,proposed_value,source_url,source_title,source_excerpt,
                         source_page,source_sha256,s3_object_key,retrieved_at,confidence_level,confidence_basis)
                        VALUES (:id,:tenant_id,:material_id,:attribute_name,CAST(:proposed_json AS jsonb),
                                :source_url,:source_title,
                                :source_excerpt,:source_page,:source_sha256,:s3_object_key,:retrieved_at,:confidence_level,
                                CAST(:basis_json AS jsonb)) ON CONFLICT(id) DO NOTHING"""),
                        source
                        | {
                            "proposed_json": _json(source["proposed_value"]),
                            "basis_json": _json(source["confidence_basis"]),
                        },
                    )
                    stored = (
                        connection.execute(text("SELECT * FROM enrichment_sources WHERE id=:id"), {"id": source["id"]})
                        .mappings()
                        .one()
                    )
                    if (
                        evidence_hash(stored) != evidence_hash(source)
                        or str(stored["material_id"]) != str(material["id"])
                        or str(stored["tenant_id"]) != manifest["tenant_id"]
                    ):
                        raise ValueError("Evidencia persistida mudou: exige nova proposta")
                    evidence_ids.append(source["id"])
                    hashes[source["id"]] = evidence_hash(stored)
                after = changes["after"]
                changes["ncm_assessment"] = asdict(
                    check_ncm_consistency(
                        catalog,
                        after["pdm_class_id"],
                        after["attributes"],
                        after["ncm"],
                        item_name=after["item_name"],
                        snapshot=load_configured_ncm_snapshot(),
                    )
                )
                changes["evidence_hashes"] = hashes
                members = [
                    {
                        "material_id": str(material["id"]),
                        "expected_version": material["version"],
                        "pdm_class_id": changes["after"]["pdm_class_id"],
                        "item_name": changes["after"]["item_name"],
                        "attributes": baseline,
                    }
                ]
                digest = proposal_hash(members, changes, evidence_ids)
                proposal_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ENRICHMENT|{material['id']}|{digest}"))
                fiscal = requires_snapshot_fiscal_review(changes["ncm_assessment"]) or bool(
                    material["attributes"] and material["attributes"] != changes["after"]["attributes"]
                )
                connection.execute(
                    text("""INSERT INTO sanitization_proposals
                    (id,tenant_id,proposal_type,members,primary_material_id,changeset,changeset_hash,evidence_ids,
                     technical_review_status,fiscal_review_status)
                    VALUES (:id,:tenant,'ENRICHMENT',CAST(:members AS jsonb),:primary,CAST(:changes AS jsonb),:hash,
                            CAST(:evidence AS jsonb),'PENDING',:fiscal) ON CONFLICT(id) DO NOTHING"""),
                    {
                        "id": proposal_id,
                        "tenant": manifest["tenant_id"],
                        "members": _json(members),
                        "primary": str(material["id"]),
                        "changes": _json(changes),
                        "hash": digest,
                        "evidence": _json(evidence_ids),
                        "fiscal": "PENDING" if fiscal else "NOT_REQUIRED",
                    },
                )
                published.append({"material_code": item["material_code"], "proposal_id": proposal_id})
    finally:
        engine.dispose()
    return {"report_key": report_key, "proposals": published, "master_data_modified": False}
