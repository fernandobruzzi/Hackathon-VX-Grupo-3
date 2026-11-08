"""Pontuador simulado, sem rede: log probs fixos por código ou iguais para todos os candidatos.
Serve para testes e execução local; não mede qualidade e é recusado fora de APP_ENV=local."""

from domain.ncm_scoring import CandidateLogprobs


class SimulatedV1NcmScorer:
    name = "simulated_v1"
    model = "simulated-uniform-v1"
    simulated = True

    def __init__(self, logprobs: dict[str, float] | None = None) -> None:
        self.logprobs = dict(logprobs or {})
        self.calls = 0

    def score(self, prompt: str, candidates: tuple[str, ...]) -> CandidateLogprobs:
        self.calls += 1
        # Sem valor fixo, todos os candidatos empatam: a confiança fica baixa quando há mais de um.
        values = {code: self.logprobs.get(code, 0.0) for code in candidates}
        return CandidateLogprobs(self.name, self.model, self.simulated, values)
