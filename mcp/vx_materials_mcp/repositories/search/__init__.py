"""Registro dos algoritmos de busca de materiais parecidos, selecionado por SEARCH_REPOSITORY."""

import os
from collections.abc import Callable
from typing import Protocol

from vx_materials_mcp.repositories.search.hybrid_embeddings_v1 import HybridEmbeddingsV1SearchRepository
from vx_materials_mcp.repositories.search.hybrid_v1 import HybridV1SearchRepository, SearchQuery


class SearchRepository(Protocol):
    """Um algoritmo de busca. Para testar outro, crie um novo repositório aqui e registre-o;
    os existentes permanecem no código."""

    name: str

    def search(self, query: SearchQuery) -> dict: ...


DEFAULT_REPOSITORY = HybridV1SearchRepository.name

REPOSITORIES: dict[str, Callable[..., SearchRepository]] = {
    HybridEmbeddingsV1SearchRepository.name: HybridEmbeddingsV1SearchRepository,
    HybridV1SearchRepository.name: HybridV1SearchRepository,
}


def get_search_repository(name: str | None = None, **dependencies) -> SearchRepository:
    selected = name or os.environ.get("SEARCH_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        factory = REPOSITORIES[selected]
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de busca desconhecido: {selected!r}. Disponiveis: {available}") from None
    return factory(**dependencies)
