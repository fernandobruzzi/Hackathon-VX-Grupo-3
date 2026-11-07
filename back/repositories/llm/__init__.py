"""Registro dos modelos de linguagem, selecionado por LLM_REPOSITORY. Sem a variável, nada chama modelo."""

import os
from collections.abc import Callable

from domain.contracts import LlmRepository
from repositories.llm.bedrock_v1 import BedrockV1LlmRepository
from repositories.llm.simulated_v1 import SimulatedV1LlmRepository

REPOSITORIES: dict[str, Callable[[], LlmRepository]] = {
    BedrockV1LlmRepository.name: BedrockV1LlmRepository,
    SimulatedV1LlmRepository.name: SimulatedV1LlmRepository,
}


def get_llm_repository(name: str | None = None) -> LlmRepository | None:
    """Cada instância tem seu orçamento: crie uma por execução (job, relatório ou avaliação)."""
    selected = name or os.environ.get("LLM_REPOSITORY", "").strip()
    if not selected or selected == "none":
        return None
    try:
        factory = REPOSITORIES[selected]
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de LLM desconhecido: {selected!r}. Disponiveis: {available}") from None
    return factory()
