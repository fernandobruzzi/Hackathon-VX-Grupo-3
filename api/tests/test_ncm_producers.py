"""Produtores novos vinculam snapshot simulado antes da aprovação estrita."""

import uuid

import pytest
from approval_fixtures import decide
from test_enrichment_flow import enrichment_case as enrichment_case
from test_manual_reviews import pending_case as pending_case
from test_manual_reviews import propose
from test_ncm_approval import configured_snapshot as configured_snapshot

from vx_materials_api.db.models import SanitizationProposal


def assert_bound(proposal, snapshot):
    assessment = proposal.changeset["ncm_assessment"]
    assert assessment["ncm_version"] == snapshot.version
    assert assessment["ncm_source_sha256"] == snapshot.source_sha256
    assert assessment["ncm_snapshot_date"] == snapshot.snapshot_date.isoformat()
    assert assessment["ncm_source_kind"] == "SIMULATED"
    assert "NCM_SOURCE_UNVERIFIED" in assessment["pending_checks"]
    assert proposal.fiscal_review_status == "PENDING"


def approve_both(case, proposal):
    case["proposal"] = proposal
    case["payload"] = {
        "expected_version": 1,
        "review_area": "TECHNICAL",
        "decision": "APPROVE",
        "reason": "Conferência local com snapshot simulado.",
    }
    first = decide(case, key=str(uuid.uuid4()))
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    case["app"].state.test_principal = case["principals"][1]
    case["payload"] |= {"expected_version": first.json()["version"], "review_area": "FISCAL"}
    second = decide(case, key=str(uuid.uuid4()))
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPLIED"


def test_fresh_manual_resolution_binds_configured_snapshot(configured_snapshot, pending_case):
    case = pending_case
    result = propose(case)
    assert result.status_code == 202, result.text
    case["session"].expire_all()
    proposal = case["session"].get(SanitizationProposal, uuid.UUID(result.json()["proposal_id"]))
    assert_bound(proposal, configured_snapshot)
    approve_both(case, proposal)


@pytest.fixture
def configured_enrichment_case(configured_snapshot, request):
    return request.getfixturevalue("enrichment_case")


def test_fresh_enrichment_publication_binds_configured_snapshot(configured_snapshot, configured_enrichment_case):
    case = configured_enrichment_case
    proposal = case["proposal"]
    assert_bound(proposal, configured_snapshot)
    approve_both(case, proposal)
