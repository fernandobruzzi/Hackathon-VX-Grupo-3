"""Seleção do extrator de evidências externas por ENRICHMENT_REPOSITORY."""

import os

from domain.contracts import EnrichmentRepository
from repositories.enrichment.catalog_labels_v1 import CatalogLabelsV1

REPOSITORIES = {CatalogLabelsV1.name: CatalogLabelsV1}


def get_enrichment_repository(name: str | None = None) -> EnrichmentRepository:
    selected = name or os.environ.get("ENRICHMENT_REPOSITORY") or CatalogLabelsV1.name
    if selected not in REPOSITORIES:
        raise ValueError(
            f"Extrator de enriquecimento desconhecido: {selected}. Disponíveis: {', '.join(sorted(REPOSITORIES))}"
        )
    return REPOSITORIES[selected]()
