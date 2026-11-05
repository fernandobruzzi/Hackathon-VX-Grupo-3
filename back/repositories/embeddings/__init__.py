"""Registro dos modelos de embeddings, selecionado por EMBEDDING_REPOSITORY. Sem a variável, a busca
não usa embeddings."""

import os
from collections.abc import Callable

from domain.contracts import EmbeddingRepository
from repositories.embeddings.bedrock_titan_v1 import BedrockTitanV1EmbeddingRepository
from repositories.embeddings.ollama_nomic_v1 import OllamaNomicV1EmbeddingRepository
from repositories.embeddings.simulated_v1 import SimulatedV1EmbeddingRepository

REPOSITORIES: dict[str, Callable[[], EmbeddingRepository]] = {
    BedrockTitanV1EmbeddingRepository.name: BedrockTitanV1EmbeddingRepository,
    OllamaNomicV1EmbeddingRepository.name: OllamaNomicV1EmbeddingRepository,
    SimulatedV1EmbeddingRepository.name: SimulatedV1EmbeddingRepository,
}


def get_embedding_repository(name: str | None = None) -> EmbeddingRepository | None:
    selected = name or os.environ.get("EMBEDDING_REPOSITORY")
    if not selected or selected == "none":
        return None
    try:
        return REPOSITORIES[selected]()
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de embeddings desconhecido: {selected!r}. Disponiveis: {available}") from None
