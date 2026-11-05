"""Registro dos algoritmos de extração de atributos.

O algoritmo ativo vem de EXTRACTION_REPOSITORY. Trocar de algoritmo é adicionar uma entrada em
REPOSITORIES e mudar essa variável, sem remover os anteriores.
"""

import os
from collections.abc import Callable

from domain.contracts import ExtractionRepository
from repositories.extraction.rule_based_v1 import RuleBasedV1ExtractionRepository

DEFAULT_REPOSITORY = RuleBasedV1ExtractionRepository.name

REPOSITORIES: dict[str, Callable[[], ExtractionRepository]] = {
    RuleBasedV1ExtractionRepository.name: RuleBasedV1ExtractionRepository,
}


def get_extraction_repository(name: str | None = None) -> ExtractionRepository:
    selected = name or os.environ.get("EXTRACTION_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        return REPOSITORIES[selected]()
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de extracao desconhecido: {selected!r}. Disponiveis: {available}") from None
