"""Consome evidências persistidas; a pesquisa externa depende do serviço da #23."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(_Contract):
    source_id: str
    url: str
    title: str | None
    excerpt: str | None
    page: str | None


class Confidence(_Contract):
    level: str
    basis: list[str]


class EnrichedAttribute(_Contract):
    attribute: str
    valor: Any
    fonte: Source
    confianca: Confidence
    approval_status: str


class EnrichmentResult(_Contract):
    material_code: str
    status: Literal["EVIDENCE_FOUND", "PENDING"]
    attributes: list[EnrichedAttribute]
    conflicts: list[str]
    pending_attributes: list[str]
    pending_reason: Literal["TRUSTED_SOURCE_SERVICE_UNAVAILABLE"] | None


def source(row: dict) -> Source:
    return Source(
        source_id=str(row["id"]),
        url=row["source_url"],
        title=row["source_title"],
        excerpt=row["source_excerpt"],
        page=row["source_page"],
    )


class Enrichment:
    def __init__(self, repository):
        self._repository = repository

    def run(self, material_code: str, attributes_requested: list[str], refresh: bool = False) -> EnrichmentResult:
        if not 1 <= len(attributes_requested) <= 50 or any(not name.strip() for name in attributes_requested):
            raise ValueError("Informe de 1 a 50 atributos nao vazios")
        requested = list(dict.fromkeys(attributes_requested))
        self._repository.require_real_material(material_code)
        rows = self._repository.evidence_for_material(material_code, requested)
        attributes = [
            EnrichedAttribute(
                attribute=row["attribute_name"],
                valor=row["proposed_value"],
                fonte=source(row),
                confianca=Confidence(level=row["confidence_level"], basis=row["confidence_basis"]),
                approval_status=row["status"],
            )
            for row in rows
        ]
        values: dict[str, set[str]] = {}
        for item in attributes:
            values.setdefault(item.attribute, set()).add(json.dumps(item.valor, sort_keys=True))
        pending = requested if refresh else [name for name in requested if name not in values]
        return EnrichmentResult(
            material_code=material_code,
            status="PENDING" if pending else "EVIDENCE_FOUND",
            attributes=attributes,
            conflicts=sorted(name for name, found in values.items() if len(found) > 1),
            pending_attributes=pending,
            pending_reason="TRUSTED_SOURCE_SERVICE_UNAVAILABLE" if pending else None,
        )
