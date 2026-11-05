"""Registro dos geradores de candidatos a duplicidade, selecionado por CANDIDATE_REPOSITORY."""

import os
from collections.abc import Callable

from domain.contracts import CandidateRepository
from repositories.candidates.exact_identity_v1 import ExactIdentityV1CandidateRepository
from repositories.candidates.tokens_v1 import TokensV1CandidateRepository

# Identidade exata primeiro: em revisão manual, só 7 de 23 pares decididos de tokens_v1 eram o
# mesmo item, enquanto a identidade exata acertou todos. Ver tests/fixtures/merge_review.json.
DEFAULT_REPOSITORY = ExactIdentityV1CandidateRepository.name

REPOSITORIES: dict[str, Callable[[], CandidateRepository]] = {
    ExactIdentityV1CandidateRepository.name: ExactIdentityV1CandidateRepository,
    TokensV1CandidateRepository.name: TokensV1CandidateRepository,
}


def get_candidate_repository(name: str | None = None) -> CandidateRepository:
    selected = name or os.environ.get("CANDIDATE_REPOSITORY") or DEFAULT_REPOSITORY
    try:
        return REPOSITORIES[selected]()
    except KeyError:
        available = ", ".join(sorted(REPOSITORIES))
        raise ValueError(f"Repositorio de candidatos desconhecido: {selected!r}. Disponiveis: {available}") from None
