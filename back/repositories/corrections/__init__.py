"""Registro das regras de correção de descrição, grupo e unidade, selecionado por CORRECTION_REPOSITORY."""

import os
from collections.abc import Callable

from domain.contracts import CorrectionRepository
from repositories.corrections.head_noun_v1 import HeadNounV1CorrectionRepository
from repositories.corrections.head_noun_v2 import HeadNounV2CorrectionRepository

DEFAULT_REPOSITORY = HeadNounV2CorrectionRepository.name

REPOSITORIES: dict[str, Callable[[], CorrectionRepository]] = {
    HeadNounV1CorrectionRepository.name: HeadNounV1CorrectionRepository,
    HeadNounV2CorrectionRepository.name: HeadNounV2CorrectionRepository,
}


def get_correction_repository(name: str | None = None) -> CorrectionRepository:
    selected = name or os.environ.get("CORRECTION_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        return REPOSITORIES[selected]()
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de correcao desconhecido: {selected!r}. Disponiveis: {available}") from None
