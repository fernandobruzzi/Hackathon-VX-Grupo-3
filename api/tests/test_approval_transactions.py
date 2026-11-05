"""Transacoes exercitadas em PostgreSQL real e pela API."""

import copy
import uuid
from decimal import Decimal

import pytest
from approval_fixtures import decide, persist, principal_with
from sqlalchemy import func, select, text

from vx_materials_api.db.models import AuditLog, InventoryConsolidation, OperationRequest


def test_merge_conserves_inventory_and_records_real_actor(approval_case):
    case = approval_case
    db = case["session"]
    before = [(s.id, s.quantity, s.unit, s.total_value, s.raw_record) for s in case["snapshots"]]
    response = decide(case)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "APPLIED"
    assert result["result"] == {"primary_material_code": "100", "blocked_material_codes": ["200"]}
    db.expire_all()
    first, second = case["materials"]
    assert first.version == 2 and second.version == 2
    assert first.is_canonical and not second.is_canonical
    assert second.status == "BLOQUEADO" and second.active_code_target == first.id
    assert [(s.id, s.quantity, s.unit, s.total_value, s.raw_record) for s in case["snapshots"]] == before
    audit = db.get(AuditLog, uuid.UUID(result["audit_event_id"]))
    assert audit.actor_user_id == case["principals"][0].user_id
    assert audit.effective_role == "ROLE_GOVERNANCA_PDM"
    assert audit.roles_snapshot == ["ROLE_GOVERNANCA_PDM"]
    assert audit.reason == case["payload"]["reason"]
    assert audit.before_json["materials"] != audit.after_json["materials"]
    assert sum(Decimal(r["quantity"]) for r in audit.after_json["inventory"]) == 6
    assert sum(Decimal(r["total_value"]) for r in audit.after_json["inventory"]) == 60
    assert {r["center_code"] for r in audit.after_json["inventory"]} == {"1100", "1200"}
    assert db.scalar(select(func.count()).select_from(InventoryConsolidation)) == 3
    rows = db.execute(
        text(
            "SELECT center_code, sum(quantity), sum(total_value) FROM mcp_inventory_financial "
            "WHERE tenant_id=:t AND material_id=:m GROUP BY center_code"
        ),
        {"t": first.tenant_id, "m": first.id},
    ).all()
    assert {(r[0], r[1], r[2]) for r in rows} == {("1100", Decimal(3), Decimal(30)), ("1200", Decimal(3), Decimal(30))}


def test_unit_factor_requires_source_and_keeps_value(approval_case):
    case = approval_case
    case["snapshots"][1].unit = "CX"
    case["session"].commit()
    assert decide(case).status_code == 422
    changes = copy.deepcopy(case["proposal"].changeset)
    changes["conversions"] = [
        {"from_unit": "CX", "to_unit": "PC", "factor": "10", "source": "Embalagem: 10 pecas por caixa."}
    ]
    case["proposal"].changeset = changes
    persist(case)
    result = decide(case)
    assert result.status_code == 200, result.text
    case["session"].expire_all()
    assert case["snapshots"][1].quantity == 3 and case["snapshots"][1].unit == "CX"
    audit = case["session"].get(AuditLog, uuid.UUID(result.json()["audit_event_id"]))
    assert sum(Decimal(r["quantity"]) for r in audit.after_json["inventory"]) == 33
    assert sum(Decimal(r["total_value"]) for r in audit.after_json["inventory"]) == 60


def test_stale_member_is_rejected_and_audited(approval_case):
    case = approval_case
    case["materials"][1].version = 2
    case["session"].commit()
    result = decide(case)
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "STALE_PROPOSAL"
    case["session"].expire_all()
    assert case["proposal"].status == "STALE"
    assert case["materials"][0].version == 1
    assert case["materials"][1].status == "ATIVO"
    assert case["session"].scalar(select(AuditLog.action)) == "PROPOSAL_STALE"


def test_fiscal_review_and_technical_review_are_both_required(approval_case):
    case = approval_case
    changes = copy.deepcopy(case["proposal"].changeset)
    changes["after"]["ncm"] = "8421.99.99"  # Outra referencia permitida da classe de filtros.
    changes["sources"]["ncm"] = "Revisao fiscal do catalogo."
    # Usa um NCM efetivamente listado na referencia do PDM.
    codes = [code for ref in case["catalog"].classes["PDM100"].ncm_references for code in ref.codes]
    changes["after"]["ncm"] = next(code for code in codes if code != "8421.23.00")
    case["proposal"].changeset = changes
    case["proposal"].fiscal_review_status = "PENDING"
    persist(case)
    first = decide(case)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    case["session"].expire_all()
    assert case["materials"][0].version == 1
    case["app"].state.test_principal = case["principals"][1]
    fiscal = {"expected_version": 2, "review_area": "FISCAL", "decision": "APPROVE", "reason": "NCM conferido."}
    second = decide(case, payload=fiscal, key=str(uuid.uuid4()))
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPLIED"
    case["session"].expire_all()
    assert case["materials"][0].ncm == changes["after"]["ncm"]


def test_changed_changeset_invalidates_previous_review(approval_case):
    case = approval_case
    case["proposal"].fiscal_review_status = "PENDING"
    persist(case)
    assert decide(case).json()["status"] == "PENDING"
    case["session"].refresh(case["proposal"])
    changes = copy.deepcopy(case["proposal"].changeset)
    changes["sources"]["attributes"] = "Outra interpretacao posterior."
    case["proposal"].changeset = changes
    persist(case)  # Mesmo com hash recalculado pelo produtor, a aprovacao anterior nao vale.
    case["app"].state.test_principal = case["principals"][1]
    result = decide(
        case,
        payload={"expected_version": 2, "review_area": "FISCAL", "decision": "APPROVE", "reason": "Conferido."},
        key=str(uuid.uuid4()),
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "STALE_PROPOSAL"


def test_fiscal_change_cannot_bypass_review(approval_case):
    case = approval_case
    changes = copy.deepcopy(case["proposal"].changeset)
    changes["after"]["ncm"] = None
    case["proposal"].changeset = changes
    persist(case)
    assert decide(case).json()["error"]["code"] == "FISCAL_REVIEW_REQUIRED"


@pytest.mark.parametrize("field,value", [("FABRICANTE", "FRAM"), ("REFERENCIA FABRICANTE", "OTHER")])
def test_different_manufacturers_or_references_never_merge(approval_case, field, value):
    case = approval_case
    members = copy.deepcopy(case["proposal"].members)
    members[1]["attributes"][field] = value
    case["proposal"].members = members
    persist(case)
    result = decide(case)
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "IDENTITY_CONFLICT"


def test_rejection_records_decision_without_editing_master(approval_case):
    case = approval_case
    result = decide(case, payload=case["payload"] | {"decision": "REJECT"})
    assert result.json()["status"] == "REJECTED"
    case["session"].expire_all()
    assert all(m.version == 1 and m.status == "ATIVO" for m in case["materials"])
    assert case["session"].scalar(select(func.count()).select_from(InventoryConsolidation)) == 0


def test_audit_failure_rolls_back_master_and_operation(approval_case, monkeypatch):
    case = approval_case
    from vx_materials_api.services import approval_service

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(approval_service, "_audit", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        decide(case)
    case["session"].expire_all()
    assert all(m.version == 1 and m.status == "ATIVO" for m in case["materials"])
    assert case["session"].scalar(select(func.count()).select_from(OperationRequest)) == 0
    assert case["session"].scalar(select(func.count()).select_from(InventoryConsolidation)) == 0


def test_hidden_centers_and_tenants_are_not_accessible(approval_case):
    case = approval_case
    case["app"].state.test_principal = principal_with(case, center_codes=("1100",))
    assert decide(case).status_code == 404
    assert case["client"].get("/api/v1/sanitization/queue").json()["items"] == []
    case["app"].state.test_principal = principal_with(case, tenant_id=uuid.uuid4())
    assert decide(case).status_code == 404


def test_api_contract_for_details_queue_and_decision(approval_case):
    from test_contracts import validator

    case = approval_case
    for path, schema in [
        (f"/api/v1/sanitization/{case['proposal'].id}", "Proposal"),
        ("/api/v1/sanitization/queue", "ProposalQueue"),
    ]:
        result = case["client"].get(path)
        assert result.status_code == 200, result.text
        validator({"$ref": f"#/components/schemas/{schema}"}).validate(result.json())
    result = decide(case)
    validator({"$ref": "#/components/schemas/ProposalDecisionResponse"}).validate(result.json())
    audit = case["client"].get("/api/v1/audit").json()
    validator({"$ref": "#/components/schemas/AuditList"}).validate(audit)
    assert "total_value" not in str(audit)
    case["app"].state.test_principal = case["principals"][1]
    assert "total_value" in str(case["client"].get("/api/v1/audit").json())
