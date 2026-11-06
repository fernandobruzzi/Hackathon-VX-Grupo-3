"""Registro selecionado por CLASSIFICATION_REPOSITORY, sem remover alternativas."""

import os
from collections.abc import Callable

from domain.contracts import ClassificationRepository, PdmCatalog
from repositories.classification.aliases_v1 import AliasesV1ClassificationRepository
from repositories.classification.rule_based_v1 import RuleBasedV1ClassificationRepository

DEFAULT_REPOSITORY = AliasesV1ClassificationRepository.name

REPOSITORIES: dict[str, Callable[[PdmCatalog], ClassificationRepository]] = {
    AliasesV1ClassificationRepository.name: AliasesV1ClassificationRepository,
    RuleBasedV1ClassificationRepository.name: RuleBasedV1ClassificationRepository,
}


def get_classification_repository(catalog: PdmCatalog, name: str | None = None) -> ClassificationRepository:
    selected = name or os.environ.get("CLASSIFICATION_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        factory = REPOSITORIES[selected]
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de classificacao desconhecido: {selected!r}. Disponiveis: {available}") from None
    return factory(catalog)
