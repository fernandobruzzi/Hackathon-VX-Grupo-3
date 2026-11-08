"""Algoritmos RAG selecionáveis; o adaptador de persistência mantém a autoridade sobre o escopo."""

import os

from domain.contracts import RagMaterialRepository
from repositories.rag.context_v1 import ContextV1RagRepository

REPOSITORIES = {ContextV1RagRepository.name: ContextV1RagRepository}
DEFAULT_REPOSITORY = ContextV1RagRepository.name


def get_rag_repository(name: str | None = None, **dependencies) -> RagMaterialRepository:
    selected = name or os.environ.get("RAG_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        repository = REPOSITORIES[selected]
    except KeyError:
        raise ValueError(
            f"Repositório RAG desconhecido: {selected}. Disponíveis: {', '.join(sorted(REPOSITORIES))}"
        ) from None
    return repository(**dependencies)
