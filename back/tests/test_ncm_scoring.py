"""Confiança do auditor LLM (#297): pontuador trocável, faixa registrada e nada aprovado por ela."""

import pytest
from tests.test_llm_audit import BOLT, analyze, catalog, model, resolve  # noqa: F401

from domain.ncm_scoring import NcmScorerError, band, confidence, normalize
from domain.runtime import AWS_RUNTIME_VARIABLES, check_simulated_clients
from pipelines.llm_audit import audit_pending_ncm
from repositories.ncm_scorer import get_ncm_scorer
from repositories.ncm_scorer.simulated_v1 import SimulatedV1NcmScorer


def test_probabilities_are_relative_to_the_pdm_candidates():
    probabilities = normalize({"8481.80.95": -0.1, "8481.80.99": -2.5})
    assert sum(probabilities.values()) == pytest.approx(1)
    assert band(probabilities["8481.80.95"]) == "ALTA"
    assert band(0.7) == "MEDIA" and band(0.5) == "BAIXA"
    with pytest.raises(NcmScorerError):
        normalize({"8481.80.95": float("nan")})


def test_uniform_simulated_scores_are_low_and_labeled():
    candidates = ("8481.80.95", "8481.80.99")
    scored = SimulatedV1NcmScorer().score("prompt", candidates)
    record = confidence("8481.80.95", candidates, scored)
    assert record["probability"] == 0.5 and record["band"] == "BAIXA"
    assert record["scorer"] == {"repository": "simulated_v1", "model": "simulated-uniform-v1", "simulated": True}


def test_scores_for_other_codes_are_not_trusted():
    scored = SimulatedV1NcmScorer().score("prompt", ("8481.80.95",))
    record = confidence("8481.80.95", ("8481.80.95", "8481.80.99"), scored)
    assert record["band"] is None and record["error"] == "SCORER_CANDIDATES_MISMATCH"


def test_auditor_records_confidence_but_it_never_approves(catalog):  # noqa: F811
    scorer = SimulatedV1NcmScorer({"7318.15.00": -0.01})
    [proposal], _ = audit_pending_ncm([analyze(catalog, BOLT)], catalog, [], model(resolve()), scorer=scorer)
    record = proposal.changeset["llm_audit"]["confidence"]
    assert record["candidates"] == ["7318.15.00"] and record["band"] == "ALTA"
    assert record["domain_validated"] is True
    # Mesmo com confiança alta: revisão técnica e fiscal, sem faixa de lote.
    assert proposal.fiscal_review_required
    assert "review_lane" not in proposal.changeset


def test_without_scorer_only_domain_validation_counts(catalog, monkeypatch):  # noqa: F811
    monkeypatch.delenv("NCM_SCORER_REPOSITORY", raising=False)
    assert get_ncm_scorer() is None
    [proposal], _ = audit_pending_ncm([analyze(catalog, BOLT)], catalog, [], model(resolve()))
    record = proposal.changeset["llm_audit"]["confidence"]
    assert record["domain_validated"] is True and record["band"] is None and record["scorer"] is None


def test_scorer_failure_keeps_the_suggestion_without_score(catalog):  # noqa: F811
    class Broken(SimulatedV1NcmScorer):
        def score(self, prompt, candidates):
            raise NcmScorerError("SCORER_UNAVAILABLE")

    [proposal], _ = audit_pending_ncm([analyze(catalog, BOLT)], catalog, [], model(resolve()), scorer=Broken())
    assert proposal.changeset["llm_audit"]["confidence"]["error"] == "SCORER_UNAVAILABLE"


def test_simulated_scorer_is_refused_outside_local(monkeypatch):
    for name in AWS_RUNTIME_VARIABLES + ("EMBEDDING_REPOSITORY", "LLM_REPOSITORY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NCM_SCORER_REPOSITORY", "simulated_v1")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="NCM_SCORER_REPOSITORY"):
        check_simulated_clients()
    with pytest.raises(ValueError, match="desconhecido"):
        get_ncm_scorer("inexistente")


class FakeBedrock:
    def __init__(self, top):
        self.top, self.bodies = top, []

    def invoke_model(self, **kwargs):
        import io
        import json

        self.bodies.append(json.loads(kwargs["body"]))
        content = [{"token": self.top[0]["token"], "logprob": self.top[0]["logprob"], "top_logprobs": self.top}]
        return {"body": io.BytesIO(json.dumps({"choices": [{"logprobs": {"content": content}}]}).encode())}


def bedrock_scorer(top, calls=5):
    from domain.llm import LlmBudget
    from repositories.ncm_scorer.bedrock_import_v1 import BedrockImportV1NcmScorer

    client = FakeBedrock(top)
    return BedrockImportV1NcmScorer(client=client, model="arn:modelo", budget=LlmBudget(calls)), client


def test_bedrock_scorer_reads_letter_logprobs_of_the_first_token():
    scorer, client = bedrock_scorer([{"token": "B", "logprob": -0.05}, {"token": " A", "logprob": -3.0}])
    scored = scorer.score("Descrição do material", ("8481.80.95", "8481.80.99", "8481.90.90"))
    assert scored.logprobs["8481.80.99"] == -0.05 and scored.logprobs["8481.80.95"] == -3.0
    # Fora das alternativas devolvidas: abaixo de todas.
    assert scored.logprobs["8481.90.90"] < -3.0
    body = client.bodies[0]
    assert body["max_tokens"] == 1 and body["logprobs"] is True and body["top_logprobs"] >= 3
    assert "C) 8481.90.90" in body["messages"][0]["content"]
    assert confidence("8481.80.99", tuple(sorted(scored.logprobs)), scored)["band"] == "ALTA"


def test_bedrock_scorer_failures_have_stable_codes():
    scorer, client = bedrock_scorer([{"token": "Z", "logprob": -0.1}], calls=1)
    with pytest.raises(NcmScorerError, match="SCORER_NO_CANDIDATE_TOKEN"):
        scorer.score("x", ("a", "b"))
    with pytest.raises(NcmScorerError, match="SCORER_BUDGET_EXHAUSTED"):
        scorer.score("x", ("a", "b"))
    # Código único não gasta chamada.
    assert scorer.score("x", ("a",)).logprobs == {"a": 0.0}
    from repositories.ncm_scorer.bedrock_import_v1 import BedrockImportV1NcmScorer

    with pytest.raises(NcmScorerError, match="SCORER_NOT_CONFIGURED"):
        BedrockImportV1NcmScorer(client=client, model="").score("x", ("a", "b"))
