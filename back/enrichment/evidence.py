"""Evidência imutável e confiança calculada por regras; nunca autoriza uma aprovação."""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass

from clients.storage import ObjectConflictError, ObjectStore
from domain.contracts import EnrichmentClaim
from enrichment.trusted_sources import SourceDocument, SourceError, SourceSpec, validate_url


@dataclass(frozen=True)
class AttributeEvidence:
    id: str
    material_code: str
    attribute: str
    proposed_value: str
    source_id: str
    source_url: str
    source_title: str
    source_excerpt: str
    source_page: int | None
    source_sha256: str
    object_key: str
    retrieved_at: str
    confidence_level: str
    confidence_basis: tuple[str, ...]
    extraction_rule: str
    simulated: bool
    approval_status: str = "PENDING"


def persist_document(store: ObjectStore, spec: SourceSpec, document: SourceDocument) -> dict:
    if document.source_id != spec.id:
        raise SourceError("Identificador da fonte divergente")
    validate_url(document.url, spec.allowed_hosts)
    key = f"evidence/{document.sha256}/source"
    store.put_if_absent(key, document.content)
    metadata = {
        "source_id": spec.id,
        "url": document.url,
        "content_type": document.content_type,
        "sha256": document.sha256,
        "object_key": key,
        "retrieved_at": document.retrieved_at,
        "simulated": document.simulated,
    }
    mode = "simulated" if document.simulated else "live"
    metadata_key = f"evidence/{document.sha256}/{spec.id}/{mode}.json"
    try:
        store.put_if_absent(metadata_key, json.dumps(metadata, sort_keys=True).encode())
    except ObjectConflictError:
        previous = json.loads(store.get(metadata_key))
        if any(previous[field] != metadata[field] for field in metadata if field != "retrieved_at"):
            raise SourceError("Metadados incompatíveis para a mesma evidência") from None
        return previous
    return metadata


def record_evidence(
    store: ObjectStore,
    code: str,
    claim: EnrichmentClaim,
    spec: SourceSpec,
    document: SourceDocument,
    pages: tuple[str, ...],
    *,
    repository_name: str = "catalog_labels_v1",
) -> AttributeEvidence:
    if (
        not claim.excerpt.strip()
        or claim.page is None
        or not 1 <= claim.page <= len(pages)
        or claim.excerpt not in pages[claim.page - 1]
    ):
        raise SourceError("Trecho da evidência ausente no documento")
    body = persist_document(store, spec, document)
    basis = ("EXACT_PART_NUMBER", "EXPLICIT_CATALOG_LABEL")
    if spec.kind == "MANUFACTURER":
        level, basis = "HIGH", ("MANUFACTURER_DOMAIN", *basis)
    elif spec.kind == "DISTRIBUTOR":
        level, basis = "MEDIUM", ("REVIEWED_DISTRIBUTOR_DOMAIN", *basis)
    else:
        raise SourceError("Tipo de fonte não confiável")
    if document.simulated:
        level, basis = "LOW", ("SIMULATED", *basis)
    identity = json.dumps(
        [
            code,
            claim.attribute,
            claim.value,
            spec.id,
            document.sha256,
            claim.excerpt,
            repository_name,
            document.simulated,
        ],
        ensure_ascii=False,
    )
    evidence = AttributeEvidence(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
        material_code=code,
        attribute=claim.attribute,
        proposed_value=claim.value,
        source_id=spec.id,
        source_url=document.url,
        source_title=spec.title,
        source_excerpt=claim.excerpt,
        source_page=claim.page,
        source_sha256=document.sha256,
        object_key=body["object_key"],
        retrieved_at=body["retrieved_at"],
        confidence_level=level,
        confidence_basis=basis,
        extraction_rule=f"{repository_name}/{claim.attribute}",
        simulated=document.simulated,
    )
    data = json.dumps(asdict(evidence), sort_keys=True, ensure_ascii=False).encode()
    digest = hashlib.sha256(data).hexdigest()
    store.put_if_absent(f"evidence/{evidence.id}/{digest}.json", data)
    return evidence
