"""Confiança da sugestão do auditor LLM (#297): validação pelo domínio e pontuação por log probs.

O pontuador não gera resposta: recebe o texto do caso e os códigos candidatos do PDM e devolve o
log prob de cada um. A probabilidade normalizada entre os candidatos vira uma faixa que só ordena a
revisão humana. Nenhuma faixa aprova, aplica ou coloca em lote uma sugestão.
"""

import math
from dataclasses import dataclass
from typing import Protocol

SCORING_VERSION = "ncm-confidence-v1"
# Limites provisórios até a calibração com modelo real no benchmark.
BANDS = (("ALTA", 0.9), ("MEDIA", 0.6), ("BAIXA", 0.0))


class NcmScorerError(Exception):
    """Falha sem pontuação utilizável; a sugestão segue só com a validação pelo domínio."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class CandidateLogprobs:
    repository: str
    model: str
    simulated: bool
    logprobs: dict[str, float]


class NcmScorer(Protocol):
    name: str
    model: str
    simulated: bool

    def score(self, prompt: str, candidates: tuple[str, ...]) -> CandidateLogprobs: ...


def normalize(logprobs: dict[str, float]) -> dict[str, float]:
    """Softmax entre os candidatos: a probabilidade é relativa ao conjunto do PDM, não absoluta."""
    if not logprobs or any(not math.isfinite(v) for v in logprobs.values()):
        raise NcmScorerError("SCORER_INVALID_LOGPROBS")
    top = max(logprobs.values())
    weights = {code: math.exp(value - top) for code, value in logprobs.items()}
    total = sum(weights.values())
    return {code: round(weight / total, 6) for code, weight in sorted(weights.items())}


def band(probability: float) -> str:
    return next(name for name, floor in BANDS if probability >= floor)


def confidence(chosen: str, candidates: tuple[str, ...], scored: CandidateLogprobs | None, error: str | None = None):
    """Registro da confiança na sugestão. Sem pontuador, só a validação pelo domínio vale."""
    record = {
        "version": SCORING_VERSION,
        "domain_validated": True,
        "chosen": chosen,
        "candidates": list(candidates),
        "scorer": None,
        "probabilities": None,
        "probability": None,
        "band": None,
        "error": error,
    }
    if scored is None:
        return record
    if set(scored.logprobs) != set(candidates):
        return {**record, "error": "SCORER_CANDIDATES_MISMATCH"}
    probabilities = normalize(scored.logprobs)
    return {
        **record,
        "scorer": {"repository": scored.repository, "model": scored.model, "simulated": scored.simulated},
        "probabilities": probabilities,
        "probability": probabilities[chosen],
        "band": band(probabilities[chosen]),
    }
