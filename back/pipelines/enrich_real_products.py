"""Produz evidências e propostas imutáveis dos códigos do manifesto, sem escrever no mestre."""

import csv
import hashlib
import io
import json
import uuid
from collections import defaultdict
from dataclasses import asdict

from clients.storage import ObjectStore
from domain.contracts import EnrichmentRepository, PdmCatalog
from enrichment.catalog import REAL_PRODUCTS
from enrichment.documents import document_pages
from enrichment.evidence import AttributeEvidence, persist_document, record_evidence
from enrichment.trusted_sources import SourceDocument, SourceError, TrustedSourceClient
from repositories.enrichment import get_enrichment_repository
from repositories.extraction import get_extraction_repository

PIPELINE_VERSION = "enrichment-artifacts-v2"


def _json(content) -> bytes:
    return json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


def _manifest(store: ObjectStore, key: str, catalog: PdmCatalog):
    raw = store.get(key)
    if len(raw) > 1_000_000:
        raise ValueError("Manifesto excede o limite de tamanho")
    manifest = json.loads(raw)
    uuid.UUID(manifest["dataset_id"])
    uuid.UUID(manifest["tenant_id"])
    codes = manifest["real_material_codes"]
    if not isinstance(codes, list) or len(codes) != 15 or len(set(codes)) != 15 or set(codes) != set(REAL_PRODUCTS):
        raise ValueError("Manifesto deve identificar somente os 15 códigos reais do kit")
    files = {entry["name"]: entry for entry in manifest["files"]}
    pdm = files["03_padrao_cadastro_PDM.xlsx"]
    if manifest["pdm_version"] != catalog.version or pdm["sha256"] != catalog.source_sha256:
        raise ValueError("PDM diferente da referência registrada no manifesto")
    original = files["01_base_materiais.csv"]
    content = store.get(original["object_key"])
    if len(content) > 15_000_000 or hashlib.sha256(content).hexdigest() != original["sha256"]:
        raise ValueError("Hash ou tamanho da base original inválido")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline="")))
    records = {row["CODIGO_MATERIAL"]: row for row in rows}
    if len(records) != len(rows) or not set(codes) <= records.keys():
        raise ValueError("Códigos repetidos ou ausentes na base original")
    return manifest, records, hashlib.sha256(raw).hexdigest()


def _replay_document(store: ObjectStore, metadata: dict, spec) -> SourceDocument:
    content = store.get(metadata["object_key"])
    if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
        raise SourceError("Hash da evidência armazenada divergente")
    document = SourceDocument(
        source_id=metadata["source_id"],
        url=metadata["url"],
        content=content,
        content_type=metadata["content_type"],
        retrieved_at=metadata["retrieved_at"],
        simulated=metadata.get("simulated", False),
    )
    # As mesmas verificações de identidade e URL valem na leitura offline.
    persist_document(store, spec, document)
    return document


def _proposal(
    code: str,
    row: dict,
    product,
    evidence: list[AttributeEvidence],
    catalog: PdmCatalog,
    manifest: dict,
    manifest_hash: str,
    repository_name: str,
):
    cls = catalog.classes[product.pdm_class_id]
    extraction = get_extraction_repository().extract(
        cls,
        row["DESCRICAO_LONGA"],
        manufacturer=row["FABRICANTE"] or None,
        manufacturer_reference=row["REFERENCIA_FABRICANTE"] or None,
    )
    current = {name: attr.value for name, attr in extraction.attributes.items()}
    grouped = defaultdict(list)
    for item in evidence:
        grouped[item.attribute].append(item)
    changes, conflicts = [], []
    for attribute, items in sorted(grouped.items()):
        values = sorted({item.proposed_value for item in items})
        original = current.get(attribute)
        if len(values) > 1 or (original and values != [original]):
            conflicts.append(
                {
                    "attribute": attribute,
                    "current_value": original,
                    "values": values,
                    "evidence_ids": [item.id for item in items],
                }
            )
            continue
        if not original:
            changes.append(
                {"field": attribute, "before": None, "after": values[0], "evidence_ids": [item.id for item in items]}
            )
    changeset = {
        "schema": PIPELINE_VERSION,
        "dataset_id": manifest["dataset_id"],
        "tenant_id": manifest["tenant_id"],
        "input_manifest_sha256": manifest_hash,
        "material_code": code,
        "pdm_class_id": cls.id,
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "repository": repository_name,
        "before": {
            "description": row["DESCRICAO_LONGA"],
            "manufacturer": row["FABRICANTE"],
            "reference": row["REFERENCIA_FABRICANTE"],
            "attributes": current,
        },
        "changes": changes,
        "conflicts": conflicts,
        "evidence": [asdict(item) for item in evidence],
    }
    digest = hashlib.sha256(_json(changeset)).hexdigest()
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{PIPELINE_VERSION}|{digest}")),
        "proposal_type": "ENRICHMENT",
        "status": "PENDING",
        "technical_review_status": "PENDING",
        "changeset_hash": digest,
        "changeset": changeset,
        "simulated": any(item.simulated for item in evidence),
        "pending_checks": ["CURRENT_MATERIAL_VERSION_REQUIRED", "PERSISTENCE_ADAPTER_REQUIRED"],
    }


def run_enrichment(
    store: ObjectStore,
    manifest_key: str,
    catalog: PdmCatalog,
    *,
    material_codes: list[str] | None = None,
    repository: EnrichmentRepository | None = None,
    client: TrustedSourceClient | None = None,
    evidence_manifest_key: str | None = None,
) -> dict:
    """Com evidence_manifest_key, repete a avaliação sem nenhuma chamada à rede.

    O comando publish-enrichment adapta os artefatos à fila de aprovação,
    conferindo a versão atual. Artefatos nunca alteram o cadastro diretamente.
    """
    manifest, records, manifest_hash = _manifest(store, manifest_key, catalog)
    selected = sorted(set(material_codes if material_codes is not None else manifest["real_material_codes"]))
    if not set(selected) <= set(manifest["real_material_codes"]):
        raise ValueError("Enriquecimento permitido somente para os códigos reais do manifesto")
    repository = repository or get_enrichment_repository()
    client = client or TrustedSourceClient()
    cached = None
    cached_failures = {}
    if evidence_manifest_key is not None:
        cached_report = json.loads(store.get(evidence_manifest_key))
        if cached_report["input_manifest_sha256"] != manifest_hash:
            raise ValueError("Evidências pertencem a outro manifesto")
        cached = cached_report["documents"]
        cached_failures = cached_report.get("failures", {})
    documents, failures, results = {}, {}, []
    in_memory = {}
    for code in selected:
        product = REAL_PRODUCTS[code]
        evidence, pending = [], []
        for spec in product.sources:
            try:
                if spec.id in failures:
                    raise SourceError(failures[spec.id])
                if spec.id not in in_memory:
                    if cached is not None:
                        if spec.id not in cached:
                            raise SourceError(cached_failures.get(spec.id, "Evidência ausente na execução offline"))
                        document = _replay_document(store, cached[spec.id], spec)
                    else:
                        document = client.fetch(spec)
                    pages = document_pages(document)
                    documents[spec.id] = persist_document(store, spec, document)
                    in_memory[spec.id] = (document, pages)
                document, pages = in_memory[spec.id]
                claims = repository.extract(
                    catalog.classes[product.pdm_class_id], product.manufacturer, product.reference, pages
                )
                if not claims:
                    pending.append({"source_id": spec.id, "reason": "EXACT_PRODUCT_EVIDENCE_NOT_FOUND"})
                for claim in claims:
                    if claim.attribute not in {attr.name for attr in catalog.classes[product.pdm_class_id].attributes}:
                        raise SourceError("Atributo fora da classe do PDM")
                    evidence.append(
                        record_evidence(store, code, claim, spec, document, pages, repository_name=repository.name)
                    )
            except SourceError as error:
                failures[spec.id] = str(error)
                pending.append({"source_id": spec.id, "reason": str(error)})
        if not product.sources:
            pending.append({"reason": "NO_REVIEWED_EXACT_PRODUCT_SOURCE"})
        proposal = _proposal(code, records[code], product, evidence, catalog, manifest, manifest_hash, repository.name)
        proposal_key = None
        if proposal["changeset"]["changes"] or proposal["changeset"]["conflicts"]:
            proposal_key = f"runs/enrichment/{manifest_hash}/proposals/{proposal['id']}.json"
            store.put_if_absent(proposal_key, _json(proposal))
        results.append(
            {
                "material_code": code,
                "status": "EVIDENCE_FOUND" if evidence else "PENDING",
                "evidence": [asdict(item) for item in evidence],
                "conflicts": proposal["changeset"]["conflicts"],
                "proposal_key": proposal_key,
                "pending": pending,
            }
        )
    report = {
        "pipeline_version": PIPELINE_VERSION,
        "input_manifest_key": manifest_key,
        "input_manifest_sha256": manifest_hash,
        "dataset_id": manifest["dataset_id"],
        "repository": repository.name,
        "simulated": any(item.get("simulated") for item in documents.values()),
        "documents": documents,
        "failures": failures,
        "results": results,
    }
    report_hash = hashlib.sha256(_json(report)).hexdigest()
    report_key = f"runs/enrichment/{manifest_hash}/{report_hash}.json"
    store.put_if_absent(report_key, _json(report))
    return {"report_key": report_key, **report}
