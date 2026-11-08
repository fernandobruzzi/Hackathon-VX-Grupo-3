"""Sugestão do auditor LLM (#290) na fila, no detalhe e na aprovação.

O batch produz a proposta com o modelo simulado e respostas fixas; a API trata a origem
`LLM_AUDITOR` como contexto da revisão, sempre com revisão técnica e fiscal.
"""

import copy
import json
import uuid
from pathlib import Path

import pytest
from approval_fixtures import decide
from pydantic import ValidationError

from domain.contracts import MaterialRecord
from domain.llm import LlmSettings
from domain.pdm_loader import load_pdm
from pipelines.llm_audit import TOOL_NAME, audit_pending_ncm
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.llm.simulated_v1 import SimulatedV1LlmRepository
from repositories.proposal_payload import approval_payload
from vx_materials_api.schemas.proposals import ProposalChangeset

BOLT = "PARAFUSO SEXTAVADO;ROSCA:ROSCA GROSSA;BITOLA:M30;COMP:140MM;TRATAMENTO:ZINCADO BRANCO"
ANSWER = {
    "decisao": "RESOLVER",
    "classe_pdm": "PDM001",
    "nome_item": None,
    "atributos": [{"nome": "MATERIAL", "valor": "ACO CARBONO", "trecho": "ZINCADO BRANCO", "base": "INFERIDO"}],
    "ncm": "7318.15.00",
    "evidencias": ["PARAFUSO SEXTAVADO"],
    "justificativa": "Zincagem branca é acabamento de aço; a classe tem um único código.",
}


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


def audited_proposal(catalog, code="100"):
    record = MaterialRecord(code, "ATIVO", BOLT, unit="PC", ncm="7318.16.00")
    classifier = get_classification_repository(catalog, "aliases_v2")
    material = analyze_material(record, catalog, classifier, get_extraction_repository())
    llm = SimulatedV1LlmRepository({TOOL_NAME: ANSWER}, settings=LlmSettings(max_calls=5))
    [proposal], _ = audit_pending_ncm([material], catalog, [], llm)
    return proposal


MATERIAL_ID, DATASET_ID = str(uuid.UUID(int=1)), str(uuid.UUID(int=2))


def payload(catalog, material_id=MATERIAL_ID, dataset_id=DATASET_ID):
    proposal = audited_proposal(catalog)
    return approval_payload(proposal, {"100": material_id}, dataset_id)


def test_payload_carries_origin_evidence_and_auditor_sources(catalog):
    _, changes, _ = payload(catalog)
    parsed = ProposalChangeset.model_validate(json.loads(json.dumps(changes)), strict=False)
    assert parsed.origin == "LLM_AUDITOR"
    assert parsed.llm_audit.call.simulated is True
    assert parsed.llm_audit.attributes[0].trecho == "ZINCADO BRANCO"
    assert parsed.review_lane is None
    assert parsed.sources["attributes"].startswith("Auditor LLM (simulated-minimal-v1, llm-audit-v1)")
    assert parsed.sources["ncm"].startswith("LLM_AUDITOR/")


@pytest.mark.parametrize("change", ["no_context", "no_origin", "with_lane"])
def test_changeset_rejects_inconsistent_auditor_origin(catalog, change):
    _, changes, _ = payload(catalog)
    changes = json.loads(json.dumps(changes))
    if change == "no_context":
        del changes["llm_audit"]
    elif change == "no_origin":
        del changes["origin"]
    else:
        changes["review_lane"] = {"tier": 1, "lot_key": "x", "reasons": []}
    with pytest.raises(ValidationError):
        ProposalChangeset.model_validate(changes, strict=False)


def test_stored_rule_proposals_default_to_rules_origin(catalog):
    # Propostas já gravadas, sem o campo, continuam válidas com a origem padrão.
    _, changes, _ = payload(catalog)
    stored = {k: v for k, v in json.loads(json.dumps(changes)).items() if k not in {"origin", "llm_audit"}}
    assert ProposalChangeset.model_validate(stored, strict=False).origin == "RULES"


def install(case, proposal_type="NCM_CORRECTION"):
    material = case["materials"][0]
    material.ncm = "7318.16.00"
    members, changes, digest = payload(case["catalog"], str(material.id), str(case["dataset"].id))
    proposal = case["proposal"]
    proposal.proposal_type = proposal_type
    proposal.members, proposal.changeset, proposal.changeset_hash = members, json.loads(json.dumps(changes)), digest
    proposal.fiscal_review_status = "PENDING"
    case["session"].commit()
    return material


def test_queue_and_detail_show_the_auditor_origin_and_evidence(approval_case):
    install(approval_case)
    client = approval_case["client"]
    [item] = client.get("/api/v1/sanitization/queue").json()["items"]
    assert item["origin"] == "LLM_AUDITOR"
    detail = client.get(f"/api/v1/sanitization/{approval_case['proposal'].id}").json()
    assert detail["origin"] == "LLM_AUDITOR"
    audit = detail["llm_audit"]
    assert audit["simulated"] is True
    assert audit["selection_reasons"] == ["NCM_MATTER_UNPROVEN"]
    assert audit["attributes"] == [
        {"name": "MATERIAL", "value": "ACO CARBONO", "quote": "ZINCADO BRANCO", "basis": "INFERIDO"}
    ]
    assert "prompt" not in json.dumps(audit).replace("prompt_version", "")


def test_detail_of_ncm_correction_shows_only_what_approval_writes(approval_case):
    # A aprovação grava só o NCM: a revisão não pode prometer atributos nem descrição novos.
    material = install(approval_case)
    detail = approval_case["client"].get(f"/api/v1/sanitization/{approval_case['proposal'].id}").json()
    assert [row["field"] for row in detail["changes"]] == ["NCM"]
    assert detail["changes"][0]["after"] == "7318.15.00"
    assert detail["after"]["ncm"] == "7318.15.00"
    assert detail["after"]["attributes"] == {k: v for k, v in material.attributes.items() if v is not None}
    assert detail["after"]["description"] == detail["members"][0]["description"]
    assert detail["after"]["unit"] == material.unit


def test_auditor_suggestion_needs_both_reviews_and_writes_only_the_ncm(approval_case):
    case = approval_case
    material = install(case)
    before = (material.pdm_class_id, copy.deepcopy(material.attributes), material.pdm_description)
    version = 1
    for area in ["TECHNICAL", "FISCAL"]:
        case["app"].state.test_principal = case["principals"][0 if area == "TECHNICAL" else 1]
        body = {
            "expected_version": version,
            "review_area": area,
            "decision": "APPROVE",
            "reason": "Trechos conferidos.",
        }
        response = decide(case, payload=body, key=str(uuid.uuid4()))
        assert response.status_code == 200, response.text
        version = response.json()["version"]
        if area == "TECHNICAL":
            # Só a revisão técnica não aplica: o NCM exige a fiscal.
            assert response.json()["status"] == "PENDING"
    assert response.json()["status"] == "APPLIED"
    case["session"].expire_all()
    assert material.ncm == "7318.15.00"
    assert (material.pdm_class_id, material.attributes, material.pdm_description) == before


def test_auditor_origin_is_refused_outside_ncm_corrections(approval_case):
    install(approval_case, proposal_type="PDM_CORRECTION")
    response = decide(approval_case, payload={**approval_case["payload"], "primary_material_code": None})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PROPOSAL"


def test_confidence_band_and_view_come_from_the_changeset(catalog):
    from vx_materials_api.services.proposal_queries import confidence_band, llm_audit_view

    _, changes, _ = payload(catalog)
    parsed = ProposalChangeset.model_validate(json.loads(json.dumps(changes)), strict=False)
    view = llm_audit_view(parsed.llm_audit)["confidence"]
    # Sem pontuador configurado: só a validação pelo domínio, sem faixa.
    assert view["domain_validated"] is True and view["band"] is None
    assert view["candidates"] == [{"code": "7318.15.00", "probability": None}]
    assert confidence_band(parsed.llm_audit) is None
