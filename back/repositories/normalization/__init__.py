"""Registro dos algoritmos de normalizacao.

O algoritmo ativo vem de NORMALIZATION_REPOSITORY. Trocar de algoritmo e adicionar
uma entrada em REPOSITORIES e mudar essa variavel, sem remover os anteriores.
"""

import os
from collections.abc import Callable

from domain.contracts import NormalizationRepository
from repositories.normalization.rule_based_v1 import RuleBasedV1NormalizationRepository

DEFAULT_REPOSITORY = RuleBasedV1NormalizationRepository.name

REPOSITORIES: dict[str, Callable[[], NormalizationRepository]] = {
    RuleBasedV1NormalizationRepository.name: RuleBasedV1NormalizationRepository,
}


def get_normalization_repository(name: str | None = None) -> NormalizationRepository:
    selected = name or os.environ.get("NORMALIZATION_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        return REPOSITORIES[selected]()
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de normalizacao desconhecido: {selected!r}. Disponiveis: {available}") from None
