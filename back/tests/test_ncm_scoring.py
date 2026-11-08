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
