"""Cache persistido e preview limitado das fontes revisadas; publicação continua separada."""

import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from domain.enrichment_rules import check_simulated_evidence
from enrichment.catalog import REAL_PRODUCTS
from enrichment.documents import document_pages
from enrichment.evidence import build_attribute_evidence
from enrichment.trusted_sources import FetchLimits, SourceError, TrustedSourceClient, validate_url
from repositories.enrichment import get_enrichment_repository

PendingReason = Literal[
    "TRUSTED_SOURCE_SERVICE_UNAVAILABLE",
    "SOURCE_QUERY_TIMEOUT",
    "SOURCE_UNAVAILABLE",
    "EVIDENCE_NOT_FOUND",
    "NO_REVIEWED_EXACT_PRODUCT_SOURCE",
]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(_Contract):
    source_id: str
    url: str
    title: str | None
    excerpt: str | None
    page: str | None
    sha256: str | None = None


class Confidence(_Contract):
    level: str
    basis: list[str]


class EnrichedAttribute(_Contract):
    attribute: str
    valor: Any
    fonte: Source
    confianca: Confidence
    approval_status: str
    persisted: bool = True


class EnrichmentResult(_Contract):
    material_code: str
    status: Literal["EVIDENCE_FOUND", "PENDING"]
    attributes: list[EnrichedAttribute]
    conflicts: list[str]
    pending_attributes: list[str]
    pending_reason: PendingReason | None


def source(row: dict) -> Source:
    return Source(
        source_id=str(row["id"]),
        url=row["source_url"],
        title=row["source_title"],
        excerpt=row["source_excerpt"],
        page=row["source_page"],
        sha256=row.get("source_sha256"),
    )


@dataclass(frozen=True)
class ResearchResult:
    rows: tuple[dict, ...]
    pending_reason: PendingReason | None


class TrustedSourceResearch:
    """Preview do serviço existente, com três segundos de rede e nenhuma persistência."""

    def __init__(self, catalog, *, client_factory=TrustedSourceClient, clock=time.monotonic):
        self._catalog = catalog
        self._client_factory = client_factory
        self._clock = clock

    def validate_request(self, code: str, requested: list[str]):
        product = REAL_PRODUCTS.get(code)
        if product is None:
            raise ValueError("Codigo fora dos 15 produtos reais")
        pdm_class = self._catalog.classes[product.pdm_class_id]
        if not set(requested) <= {attribute.name for attribute in pdm_class.attributes}:
            raise ValueError("Atributo fora da classe PDM do produto")
        return product, pdm_class

    def run(self, code: str, requested: list[str]) -> ResearchResult:
        product, pdm_class = self.validate_request(code, requested)
        if not product.sources:
            return ResearchResult((), "NO_REVIEWED_EXACT_PRODUCT_SOURCE")
        deadline = self._clock() + 3
        repository = get_enrichment_repository()
        rows, reason = {}, None
        for spec in product.sources:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return ResearchResult(tuple(rows.values()), "SOURCE_QUERY_TIMEOUT")
            try:
                client = self._client_factory(FetchLimits(io_timeout=min(1, remaining), total_timeout=remaining))
                document = client.fetch(spec)
                if self._clock() >= deadline:
                    return ResearchResult(tuple(rows.values()), "SOURCE_QUERY_TIMEOUT")
                if document.source_id != spec.id:
                    raise SourceError("Identificador da fonte divergente")
                validate_url(document.url, spec.allowed_hosts)
                check_simulated_evidence(document.simulated)
                pages = document_pages(document)
                fresh = {}
                for claim in repository.extract(pdm_class, product.manufacturer, product.reference, pages):
                    if claim.attribute not in requested:
                        continue
                    item = build_attribute_evidence(code, claim, spec, document, pages, repository_name=repository.name)
                    fresh[item.id] = {
                        "id": item.id,
                        "attribute_name": item.attribute,
                        "proposed_value": item.proposed_value,
                        "source_url": item.source_url,
                        "source_title": item.source_title,
                        "source_excerpt": item.source_excerpt,
                        "source_page": str(item.source_page),
                        "source_sha256": item.source_sha256,
                        "confidence_level": item.confidence_level,
                        "confidence_basis": list(item.confidence_basis),
                        "status": "PENDING_PUBLICATION",
                        "persisted": False,
                    }
                if self._clock() >= deadline:
                    return ResearchResult(tuple(rows.values()), "SOURCE_QUERY_TIMEOUT")
                rows.update(fresh)
            except SourceError:
                reason = "SOURCE_UNAVAILABLE"
        return ResearchResult(tuple(rows.values()), reason or (None if rows else "EVIDENCE_NOT_FOUND"))


class Enrichment:
    def __init__(self, repository, research: TrustedSourceResearch | None = None):
        self._repository = repository
        self._research = research

    def run(self, material_code: str, attributes_requested: list[str], refresh: bool = False) -> EnrichmentResult:
        if not 1 <= len(attributes_requested) <= 50 or any(not name.strip() for name in attributes_requested):
            raise ValueError("Informe de 1 a 50 atributos nao vazios")
        requested = list(dict.fromkeys(attributes_requested))
        self._repository.require_real_material(material_code)
        if self._research is not None:
            self._research.validate_request(material_code, requested)
        rows = self._repository.evidence_for_material(material_code, requested)
        missing = [name for name in requested if not any(row["attribute_name"] == name for row in rows)]
        pending = requested if refresh else missing
        reason = "TRUSTED_SOURCE_SERVICE_UNAVAILABLE" if pending else None
        if pending and self._research is not None:
            result = self._research.run(material_code, pending)
            cached_ids = {str(row["id"]) for row in rows}
            rows = [*rows, *(row for row in result.rows if str(row["id"]) not in cached_ids)]
            pending = [name for name in requested if not any(row["attribute_name"] == name for row in rows)]
            reason = result.pending_reason or ("EVIDENCE_NOT_FOUND" if pending else None)
            if refresh and reason:
                pending = requested
        attributes = [
            EnrichedAttribute(
                attribute=row["attribute_name"],
                valor=row["proposed_value"],
                fonte=source(row),
                confianca=Confidence(level=row["confidence_level"], basis=row["confidence_basis"]),
                approval_status=row["status"],
                persisted=row.get("persisted", True),
            )
            for row in rows
        ]
        values: dict[str, set[str]] = {}
        for item in attributes:
            values.setdefault(item.attribute, set()).add(json.dumps(item.valor, sort_keys=True))
        return EnrichmentResult(
            material_code=material_code,
            status="PENDING" if pending or reason else "EVIDENCE_FOUND",
            attributes=attributes,
            conflicts=sorted(name for name, found in values.items() if len(found) > 1),
            pending_attributes=pending,
            pending_reason=reason,
        )
