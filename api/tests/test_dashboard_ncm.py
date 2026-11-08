"""NCM operacional exige decisões fiscais e conserva o escopo do dashboard."""

import copy
import uuid

import pytest
from approval_fixtures import decide
from test_dashboard import SNAPSHOTS, approve, login, principal, write_headers
from test_dashboard import dashboard_case as dashboard_case
from test_dashboard import storage as storage
from test_ncm_approval import configure_nut

from vx_materials_api.db.models import SanitizationProposal
from vx_materials_api.services.metrics_service import metrics


def test_ncm_without_decisions_has_no_precision_or_after(dashboard_case):
    client, _, _, _, _, _, _ = dashboard_case
    login(client)
    response = client.get("/api/v1/dashboard/metrics")
    ncm = response.json()["ncm"]
    assert ncm["missing_before"] == 1
    assert ncm["missing_after"] is None
    assert ncm["content"]["created"] == 0
    assert ncm["operational_precision"] is None
    assert ncm["fiscal_decided"] == 0
    benchmark = ncm["benchmark"]
    assert benchmark["data_origin"] == "DEVELOPMENT_MEASUREMENT"
    assert benchmark["labels"] == "DOCUMENTAL_SEM_REVISAO_INDEPENDENTE"
    assert benchmark["rules_version"] and benchmark["measured_at"]
    assert len(benchmark["families"]) == 80
    assert all(f["resolved"] <= f["eligible_problems"] for f in benchmark["families"])


def test_ncm_after_is_only_the_registered_snapshot(dashboard_case, storage):
    client, _, _, _, _, proposal, _ = dashboard_case
    login(client)
    approve(client, proposal)
    assert client.get("/api/v1/dashboard/metrics").json()["ncm"]["missing_after"] is None
    response = client.post(SNAPSHOTS, json={}, headers=write_headers(client))
    assert response.status_code == 201, response.text
    ncm = client.get("/api/v1/dashboard/metrics").json()["ncm"]
    assert ncm["missing_before"] == 1
    assert ncm["missing_after"] == 0


@pytest.mark.parametrize("decision", ["APPROVE", "REJECT"])
def test_ncm_precision_uses_actual_fiscal_decisions_once(approval_case, decision):
    case = approval_case
    configure_nut(case)
    db = case["session"]
    assert metrics(db, case["principals"][0]).ncm.operational_precision is None
    # Aprovação técnica não entra no denominador fiscal.
    assert decide(case).status_code == 200
    assert metrics(db, case["principals"][0]).ncm.fiscal_decided == 0
    case["app"].state.test_principal = case["principals"][1]
    key = str(uuid.uuid4())
    payload = {"expected_version": 2, "review_area": "FISCAL", "decision": decision, "reason": "Conferido."}
    for _ in range(2):
        response = decide(case, payload=payload, key=key)
        assert response.status_code == 200, response.text
    result = metrics(db, case["principals"][0]).ncm
    assert result.content.created == 1
    assert result.fiscal_decided == 1
    assert result.operational_precision == (1.0 if decision == "APPROVE" else 0.0)
    assert result.content.fiscal_approved == (1 if decision == "APPROVE" else 0)
    assert result.content.rejected == (1 if decision == "REJECT" else 0)


def test_fiscal_approval_then_technical_rejection_is_one_funnel_outcome(approval_case):
    case = approval_case
    configure_nut(case)
    case["app"].state.test_principal = case["principals"][1]
    fiscal = {"expected_version": 1, "review_area": "FISCAL", "decision": "APPROVE", "reason": "NCM conferido."}
    assert decide(case, payload=fiscal).status_code == 200
    case["app"].state.test_principal = case["principals"][0]
    technical = {
        "expected_version": 2,
        "review_area": "TECHNICAL",
        "decision": "REJECT",
        "reason": "Revisar descrição.",
    }
    assert decide(case, payload=technical, key=str(uuid.uuid4())).status_code == 200
    ncm = metrics(case["session"], case["principals"][0]).ncm
    assert ncm.content.created == ncm.content.rejected == 1
    assert ncm.content.fiscal_approved == ncm.content.pending == ncm.content.stale == 0
    assert ncm.fiscal_approved_decisions == ncm.fiscal_decided == 1
    assert ncm.operational_precision == 1.0


def test_format_only_proposals_are_separate_and_scoped(dashboard_case):
    _, db, dataset, materials, snapshots, template, _ = dashboard_case
    for snapshot in snapshots:
        if snapshot.material_id == materials[0].id:
            snapshot.raw_record = {**snapshot.raw_record, "NCM": "84212300"}
    changes = copy.deepcopy(template.changeset)
    members = copy.deepcopy(template.members[:1])
    proposal = SanitizationProposal(
        id=uuid.uuid4(),
        tenant_id=template.tenant_id,
        proposal_type="NCM_CORRECTION",
        members=members,
        primary_material_id=materials[0].id,
        changeset=changes,
        changeset_hash="test",
        fiscal_review_status="PENDING",
    )
    db.add(proposal)
    db.flush()
    result = metrics(db, principal()).ncm
    assert result.format_only.created == 1
    assert result.format_only.pending == 1
    assert result.content.created == 0
    assert result.operational_precision is None
    # A coluna preenchida sem evento fiscal não inventa uma medição de aceitação.
    proposal.fiscal_review_status = "APPROVED"
    db.flush()
    assert metrics(db, principal()).ncm.fiscal_decided == 0
    # Reproposta após correção anterior: comparar com o antes vinculado à proposta,
    # não com o NCM do primeiro dataset nem com a master mutável.
    proposal.changeset = {
        **changes,
        "after": {**changes["after"], "ncm": "7318.16.00"},
        "ncm_before_assessment": {"input_ncm": "73181600"},
    }
    db.flush()
    assert metrics(db, principal()).ncm.format_only.created == 1
    proposal.changeset = {
        **proposal.changeset,
        "ncm_before_assessment": {"input_ncm": None},
    }
    db.flush()
    assert metrics(db, principal()).ncm.content.created == 1
    # Outro dataset, tenant e membro fora dos centros não entram no funil.
    proposal.changeset = {**changes, "dataset_id": str(uuid.uuid4())}
    db.flush()
    assert metrics(db, principal()).ncm.format_only.created == 0
    proposal.changeset = changes
    proposal.members = copy.deepcopy(template.members)
    db.flush()
    assert metrics(db, principal(centers=("1100",))).ncm.format_only.created == 0
    proposal.members = members
    proposal.tenant_id = uuid.uuid4()
    db.flush()
    assert metrics(db, principal()).ncm.format_only.created == 0
