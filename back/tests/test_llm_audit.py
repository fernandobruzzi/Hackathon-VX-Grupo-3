"""Auditor LLM (#290): só casos pendentes, resposta revalidada pelo domínio e proposta rotulada.

O modelo é o simulado, com respostas fixas por caso: os testes medem o que o domínio aceita ou
descarta, nunca a qualidade de um modelo real.
"""

from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from clients.storage import LocalObjectStore
from domain.contracts import MaterialRecord
from domain.llm import LlmSettings
from domain.pdm_loader import load_pdm
from pipelines import full_run
from pipelines.llm_audit import (
    ABSTAINED,
    CONFIRMED,
    DISCARDED,
    FAILED,
    NO_CLASS,
    ORIGIN,
    PROMPT_VERSION,
    PROPOSED,
    SKIPPED,
    TOOL_NAME,
    audit_cases,
    audit_pending_ncm,
    build_prompt,
    select_audit_cases,
)
from pipelines.ncm_corrections import propose_ncm_corrections
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.llm.simulated_v1 import SimulatedV1LlmRepository

KIT = Path(__file__).parents[2] / "data/desafio01"
# Real do benchmark: sem material nem classe de resistência, as regras não provam a posição 7318.
BOLT = "PARAFUSO SEXTAVADO;ROSCA:ROSCA GROSSA;BITOLA:M30;COMP:140MM;TRATAMENTO:ZINCADO BRANCO"
STEEL = {"nome": "MATERIAL", "valor": "ACO CARBONO", "trecho": "ZINCADO BRANCO", "base": "INFERIDO"}


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


def analyze(catalog, description, ncm="7318.16.00", code="x"):
    record = MaterialRecord(code, "ATIVO", description, unit="PC", ncm=ncm)
    classifier = get_classification_repository(catalog, "aliases_v2")
    return analyze_material(record, catalog, classifier, get_extraction_repository())


def model(answer=None, calls=10):
    responses = {TOOL_NAME: answer} if answer is not None else None
    return SimulatedV1LlmRepository(responses, settings=LlmSettings(max_calls=calls))


def resolve(**overrides):
    answer = {
        "decisao": "RESOLVER",
        "classe_pdm": "PDM001",
        "nome_item": None,
        "atributos": [STEEL],
        "ncm": "7318.15.00",
        "evidencias": ["PARAFUSO SEXTAVADO"],
        "justificativa": "Parafuso zincado é de aço; o PDM tem um único código para a classe.",
    }
    return {**answer, **overrides}


def only_case(catalog, description, **kwargs):
    material = analyze(catalog, description, **kwargs)
    [case] = select_audit_cases([material], catalog, set())
    return case


def test_selects_only_what_the_rules_left_pending_with_the_reason(catalog):
    proven = analyze(catalog, "PARAFUSO SEXTAVADO M12X50 8.8 ACO CARBONO DIN 933", code="ok")
    pending = analyze(catalog, BOLT, code="pending")
    unknown = analyze(catalog, "XPTO 123 SEM NOME", code="unknown")
    proposed = {p.suggested_primary_code for p in propose_ncm_corrections([proven, pending, unknown], catalog)}
    assert proposed == {"ok"}
    cases = {c.material.record.code: c for c in select_audit_cases([proven, pending, unknown], catalog, proposed)}
    assert set(cases) == {"pending", "unknown"}
    assert cases["pending"].reasons == ("NCM_MATTER_UNPROVEN",)
    assert cases["pending"].candidate_classes[0] == "PDM001"
    assert cases["unknown"].reasons == (NO_CLASS,)


def test_prompt_never_carries_the_current_ncm(catalog):
    case = only_case(catalog, BOLT, ncm="9999.88.77")
    prompt = build_prompt(case, catalog)
    assert "9999" not in prompt
    assert BOLT in prompt
    assert "7318.15.00" in prompt  # referências do PDM da classe candidata


def test_resolved_case_becomes_a_labeled_proposal_with_both_reviews(catalog):
    material = analyze(catalog, BOLT)
    rules = propose_ncm_corrections([material], catalog)
    assert rules == []
    proposals, report = audit_pending_ncm([material], catalog, rules, model(resolve()))
    [proposal] = proposals
    assert proposal.proposal_type == "NCM_CORRECTION"
    assert proposal.fiscal_review_required
    assert proposal.changeset["origin"] == ORIGIN
    assert proposal.changeset["after"]["ncm"] == "7318.15.00"
    assert proposal.changeset["after"]["attributes"]["MATERIAL"] == "ACO CARBONO"
    audit = proposal.changeset["llm_audit"]
    assert audit["prompt_version"] == PROMPT_VERSION
    assert audit["call"]["model"] == "simulated-minimal-v1"
    assert audit["simulated"] is True
    assert audit["inferred_attributes"] == ["MATERIAL"]
    assert audit["evidence"] == ["PARAFUSO SEXTAVADO"]
    assert audit["selection_reasons"] == ["NCM_MATTER_UNPROVEN"]
    assert audit["context"]["candidate_classes"][0] == "PDM001"
    assert ORIGIN in proposal.changeset["changes"][0]["source"]
    assert report["by_status"] == {PROPOSED: 1}
    assert report["usage"]["simulated"] is True
    # Nunca entra em lote: sem faixa de revisão, e o id não colide com o das regras.
    assert "review_lane" not in proposal.changeset
    proven = analyze(catalog, "PARAFUSO SEXTAVADO M12X50 8.8 ACO CARBONO DIN 933")
    assert propose_ncm_corrections([proven], catalog)[0].id != proposal.id


def test_simulated_model_abstains_and_the_case_stays_pending(catalog):
    material = analyze(catalog, BOLT)
    proposals, report = audit_pending_ncm([material], catalog, [], model())
    assert proposals == []
    assert report["by_status"] == {ABSTAINED: 1}


def test_without_a_model_nothing_runs(catalog):
    assert audit_pending_ncm([analyze(catalog, BOLT)], catalog, [], None) == ([], None)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"evidencias": ["PARAFUSO ALLEN"]}, "LLM_QUOTE_NOT_FOUND"),
        ({"atributos": [{**STEEL, "trecho": "ACO GALVANIZADO"}]}, "LLM_QUOTE_NOT_FOUND"),
        ({"atributos": [{**STEEL, "valor": "LATAO"}]}, "LLM_ATTRIBUTE_NOT_ADMITTED"),
        ({"atributos": [{**STEEL, "nome": "COR"}]}, "LLM_ATTRIBUTE_UNKNOWN"),
        ({"atributos": [{**STEEL, "base": "LITERAL"}]}, "LLM_LITERAL_VALUE_NOT_IN_QUOTE"),
        (
            {"atributos": [STEEL, {"nome": "BITOLA", "valor": "M24", "trecho": "M30", "base": "INFERIDO"}]},
            "LLM_ATTRIBUTE_CONFLICT",
        ),
        ({"atributos": []}, "NCM_MATTER_UNPROVEN"),
        ({"ncm": "8484.10.00"}, "NCM_OUTSIDE_PDM_REFERENCE"),
        ({"ncm": None}, "NCM_DIFFERS_FROM_DOMAIN"),
        ({"classe_pdm": "PDM031"}, "LLM_CLASS_NOT_CANDIDATE"),
        ({"nome_item": "PORCA SEXTAVADA"}, "LLM_ITEM_NAME_INVALID"),
    ],
)
def test_domain_discards_what_does_not_close_with_the_reason(catalog, overrides, reason):
    [outcome] = audit_cases([only_case(catalog, BOLT)], catalog, model(resolve(**overrides)))
    assert outcome.status == DISCARDED
    assert reason in outcome.detail
    assert outcome.proposal is None


def test_domain_confirmation_without_change_proposes_nothing(catalog):
    # Mesmo pendente, o auditor que só confirma o código atual não gera revisão nova.
    material = analyze(catalog, BOLT, ncm="")
    case = replace(
        select_audit_cases([material], catalog, set())[0],
        material=replace(material, record=replace(material.record, ncm="7318.15.00")),
    )
    [outcome] = audit_cases([case], catalog, model(resolve()))
    assert outcome.status == CONFIRMED
    assert outcome.proposal is None


def test_errors_and_exhausted_budget_keep_the_case_pending(catalog):
    cases = [only_case(catalog, BOLT), only_case(catalog, BOLT, code="y")]
    outcomes = audit_cases(cases, catalog, model(resolve(), calls=1))
    assert [o.status for o in outcomes] == [PROPOSED, FAILED]
    assert outcomes[1].detail == ("LLM_BUDGET_EXHAUSTED",)
    assert outcomes[1].proposal is None


def test_case_without_candidate_class_spends_no_call(catalog):
    llm = model(resolve())
    [outcome] = audit_cases([only_case(catalog, "XPTO 123 SEM NOME")], catalog, llm)
    assert outcome.status == SKIPPED
    assert llm.budget.used == 0


def run_context(monkeypatch, tmp_path):
    """Execução sem banco: enriquecimento interno vazio e pendências manuais descartadas."""
    store = LocalObjectStore(tmp_path)
    store.put_if_absent("diagnostic", b'{"results": []}')
    monkeypatch.setattr(full_run, "_save_checkpoint", lambda context: None)
    monkeypatch.setattr(
        full_run,
        "run_internal_enrichment",
        lambda *args: {"report_key": "diagnostic", "proposals": 0, "inserted": 0, "material_codes": []},
    )
    monkeypatch.setattr(full_run, "save_manual_reviews", lambda *args: "run")
    engine = SimpleNamespace(begin=lambda: nullcontext(object()))
    return full_run.RunContext(engine=engine, tenant_id="t", store=store)


def test_full_run_adds_auditor_proposals_and_model_usage(catalog, monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr(full_run, "save_all", lambda proposals, records, context: captured.extend(proposals) or 0)
    monkeypatch.setattr(full_run, "get_llm_repository", lambda: model(resolve()))
    records = [MaterialRecord("1", "ATIVO", BOLT, unit="PC", ncm="7318.16.00")]
    context = run_context(monkeypatch, tmp_path)
    result = full_run.run_full(records, catalog, context)
    [proposal] = [p for p in captured if p.proposal_type == "NCM_CORRECTION"]
    assert proposal.changeset["origin"] == ORIGIN
    assert result["llm_audit"]["by_status"] == {PROPOSED: 1}
    assert result["model_usage"]["calls"] == {"simulated-minimal-v1": 1}
    assert result["model_usage"]["llm_audit"]["simulated"] is True
    assert "simulado" in result["model_usage"]["note"]


def test_full_run_without_model_reports_no_usage(catalog, monkeypatch, tmp_path):
    monkeypatch.setattr(full_run, "save_all", lambda proposals, records, context: 0)
    monkeypatch.delenv("LLM_REPOSITORY", raising=False)
    records = [MaterialRecord("1", "ATIVO", BOLT, unit="PC", ncm="7318.16.00")]
    context = run_context(monkeypatch, tmp_path)
    result = full_run.run_full(records, catalog, context)
    assert result["llm_audit"] is None
    assert result["model_usage"]["calls"] == {}
