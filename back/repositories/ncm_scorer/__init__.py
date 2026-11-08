"""Pontuadores de confiança do NCM (#297), selecionados por NCM_SCORER_REPOSITORY. Sem a variável,
nenhum modelo pontua e a confiança é só a validação pelo domínio."""

import os
from collections.abc import Callable

from domain.ncm_scoring import NcmScorer
from repositories.ncm_scorer.bedrock_import_v1 import BedrockImportV1NcmScorer
from repositories.ncm_scorer.simulated_v1 import SimulatedV1NcmScorer

REPOSITORIES: dict[str, Callable[[], NcmScorer]] = {
    BedrockImportV1NcmScorer.name: BedrockImportV1NcmScorer,
    SimulatedV1NcmScorer.name: SimulatedV1NcmScorer,
}


def get_ncm_scorer(name: str | None = None) -> NcmScorer | None:
    selected = name or os.environ.get("NCM_SCORER_REPOSITORY", "").strip()
    if not selected or selected == "none":
        return None
    try:
        factory = REPOSITORIES[selected]
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Pontuador de NCM desconhecido: {selected!r}. Disponiveis: {available}") from None
    return factory()
