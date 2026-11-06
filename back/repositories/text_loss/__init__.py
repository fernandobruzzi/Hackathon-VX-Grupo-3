"""Registro das regras de perda de texto, selecionado por TEXT_LOSS_REPOSITORY."""

import os
from collections.abc import Callable

from domain.contracts import TextLossRepository
from repositories.extraction import get_extraction_repository
from repositories.text_loss.unresolved_terms_v1 import UnresolvedTermsV1TextLossRepository

DEFAULT_REPOSITORY = UnresolvedTermsV1TextLossRepository.name

REPOSITORIES: dict[str, Callable[[], TextLossRepository]] = {
    # Usa a mesma extração da análise, escolhida por EXTRACTION_REPOSITORY.
    UnresolvedTermsV1TextLossRepository.name: lambda: UnresolvedTermsV1TextLossRepository(get_extraction_repository()),
}


def get_text_loss_repository(name: str | None = None) -> TextLossRepository:
    selected = name or os.environ.get("TEXT_LOSS_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        return REPOSITORIES[selected]()
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(
            f"Repositorio de perda de texto desconhecido: {selected!r}. Disponiveis: {available}"
        ) from None
