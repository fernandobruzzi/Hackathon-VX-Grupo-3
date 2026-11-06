"""Correção de grupo de mercadorias aprovada pela API, com o grupo original preservado."""

import uuid

import pytest
from approval_fixtures import decide, persist
from sqlalchemy import func, select

from vx_materials_api.db.models import AuditLog, OperationRequest

ORIGINAL = "MAN01"


@pytest.fixture
def group_case(approval_case):
    """Correção de PDM de um material só, como o batch grava para grupo divergente da classe."""
    case = approval_case
    material = case["materials"][0]
    material.original_merchandise_group = ORIGINAL
    group = case["catalog"].classes["PDM100"].group
    proposal = case["proposal"]
    proposal.proposal_type = "PDM_CORRECTION"
    proposal.members = [proposal.members[0]]
    proposal.changeset = proposal.changeset | {
        "after": proposal.changeset["after"] | {"merchandise_group": group},
        "changes": [
            {
                "field": "merchandise_group",
                "before": ORIGINAL,
                "after": group,
                "source": "head_noun_v1/group.from_pdm_class",
            }
        ],
        "sources": {"merchandise_group": "Grupo da classe PDM: head_noun_v1/group.from_pdm_class"},
    }
    persist(case)
    case["group"] = group
    case["payload"] = case["payload"] | {"reason": "Grupo conferido com a classe PDM."}
    return case


def test_approved_group_is_saved_as_reviewed_and_keeps_the_original(group_case):
    case = group_case
    response = decide(case)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPLIED"
    db = case["session"]
    db.expire_all()
    material = case["materials"][0]
    assert material.merchandise_group == case["group"]
    assert material.original_merchandise_group == ORIGINAL
    assert material.version == 2
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "PROPOSAL_APPROVE_TECHNICAL"))
    before = audit.before_json["materials"][0]
    after = audit.after_json["materials"][0]
    assert (before["merchandise_group"], before["original_merchandise_group"]) == (None, ORIGINAL)
    assert (after["merchandise_group"], after["original_merchandise_group"]) == (case["group"], ORIGINAL)
    assert audit.reason == "Grupo conferido com a classe PDM."


def test_group_must_match_the_confirmed_pdm_class(group_case):
    case = group_case
    proposal = case["proposal"]
    proposal.changeset = proposal.changeset | {"after": proposal.changeset["after"] | {"merchandise_group": "VAL01"}}
    persist(case)
    response = decide(case)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "GROUP_MISMATCH"
    case["session"].expire_all()
    assert case["materials"][0].merchandise_group is None
    assert case["proposal"].status == "PENDING"


def test_group_change_requires_a_source(group_case):
    case = group_case
    proposal = case["proposal"]
    proposal.changeset = proposal.changeset | {"sources": {}}
    persist(case)
    response = decide(case)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SOURCE_REQUIRED"


@pytest.mark.parametrize(("principal_index", "area"), [(1, "TECHNICAL"), (2, "TECHNICAL"), (0, "FISCAL")])
def test_wrong_role_cannot_approve_a_group(group_case, principal_index, area):
    case = group_case
    case["app"].state.test_principal = case["principals"][principal_index]
    response = decide(case, payload=case["payload"] | {"review_area": area})
    assert response.status_code == 403
    case["session"].expire_all()
    assert case["materials"][0].merchandise_group is None


def test_wrong_expected_version_changes_nothing(group_case):
    case = group_case
    response = decide(case, payload=case["payload"] | {"expected_version": 7})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_CONFLICT"
    case["session"].expire_all()
    assert case["materials"][0].merchandise_group is None


def test_repeating_the_decision_does_not_apply_twice(group_case):
    case = group_case
    key = str(uuid.uuid4())
    first = decide(case, key=key)
    second = decide(case, key=key)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    db = case["session"]
    db.expire_all()
    assert case["materials"][0].version == 2
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
    assert db.scalar(select(func.count()).select_from(OperationRequest)) == 1


def test_audit_failure_leaves_no_partial_group(group_case, monkeypatch):
    from vx_materials_api.services import approval_service

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(approval_service, "_audit", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        decide(group_case)
    db = group_case["session"]
    db.expire_all()
    assert group_case["materials"][0].merchandise_group is None
    assert group_case["materials"][0].version == 1
    assert db.scalar(select(func.count()).select_from(OperationRequest)) == 0


def test_group_changed_after_the_proposal_makes_it_stale(group_case):
    case = group_case
    case["materials"][0].original_merchandise_group = "VAL01"
    case["session"].commit()
    response = decide(case)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_PROPOSAL"
    case["session"].expire_all()
    assert case["proposal"].status == "STALE"
    assert case["materials"][0].merchandise_group is None


def test_incomplete_pdm_is_not_published_with_the_group(group_case):
    case = group_case
    proposal = case["proposal"]
    after = proposal.changeset["after"] | {"attributes": {"FABRICANTE": "FLEETGUARD"}}
    proposal.changeset = proposal.changeset | {"after": after}
    persist(case)
    response = decide(case)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDM_INVALID"
    case["session"].expire_all()
    assert case["materials"][0].merchandise_group is None
    assert case["proposal"].status == "PENDING"


def test_group_is_refused_outside_a_pdm_correction(group_case):
    case = group_case
    case["proposal"].proposal_type = "UNIT_CORRECTION"
    persist(case)
    response = decide(case)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PROPOSAL"
