import copy
import uuid
from datetime import UTC, datetime
from decimal import Decimal, localcontext

import pytest
from approval_fixtures import decide, persist
from sqlalchemy import func, select

from vx_materials_api.db.models import (
    AuditLog,
    EnrichmentSource,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialMaster,
    OperationRequest,
    SanitizationProposal,
)
from vx_materials_api.schemas.proposals import evidence_hash


@pytest.mark.parametrize("reference", ["LF 9009", "LF-9009", "LF/9009", "LF9009-00"])
def test_reference_variants_follow_shared_domain_identity(approval_case, reference):
    case = approval_case
    case["materials"][1].manufacturer_reference = reference
    case["materials"][1].attributes = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": reference}
    case["proposal"].members = [
        case["proposal"].members[0],
        case["proposal"].members[1] | {"attributes": case["materials"][1].attributes},
    ]
    persist(case)
    response = decide(case)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPLIED"


def test_queue_does_not_offer_a_merge_whose_member_fails_the_pdm(approval_case):
    # A aprovação valida cada membro pelo PDM. Sem a referência, o membro não fecha a identidade, e
    # a fila mostra o motivo sem oferecer a aprovação que seria recusada com PDM_INVALID.
    case = approval_case
    code = case["materials"][1].material_code
    case["proposal"].members = [
        case["proposal"].members[0],
        case["proposal"].members[1] | {"attributes": {"FABRICANTE": "FLEETGUARD"}},
    ]
    persist(case)
    detail = case["client"].get(f"/api/v1/sanitization/{case['proposal'].id}").json()
    blockers = [conflict for conflict in detail["conflicts"] if conflict.startswith("PDM_INVALIDO")]
    assert blockers and code in blockers[0] and "REFERENCIA FABRICANTE" in blockers[0]
    assert "APPROVE" not in detail["allowed_actions"]
    queued = case["client"].get("/api/v1/sanitization/queue").json()["items"]
    item = next(row for row in queued if row["id"] == str(case["proposal"].id))
    assert "APPROVE" not in item["allowed_actions"]
    response = decide(case)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDM_INVALID"


def test_canonical_identity_collision_rolls_back_every_change(approval_case):
    case = approval_case
    db = case["session"]
    db.add(
        MaterialMaster(
            tenant_id=case["principals"][0].tenant_id,
            source_system="ERP",
            material_code="300",
            status="ATIVO",
            is_canonical=True,
            identity_key="PDM100|FLEETGUARD|LF9009",
        )
    )
    db.commit()
    response = decide(case)
    assert response.status_code == 409
    db.expire_all()
    assert all(m.status == "ATIVO" and m.version == 1 for m in case["materials"])
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    assert db.scalar(select(func.count()).select_from(OperationRequest)) == 0
    assert db.scalar(select(func.count()).select_from(InventoryConsolidation)) == 0


def test_retargeting_a_principal_requires_its_dependents_in_the_proposal(approval_case):
    case = approval_case
    case["session"].add(
        MaterialMaster(
            tenant_id=case["principals"][0].tenant_id,
            source_system="ERP",
            material_code="300",
            status="BLOQUEADO",
            active_code_target=case["materials"][1].id,
        )
    )
    case["session"].commit()
    response = decide(case)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DEPENDENT_MEMBERS_REQUIRED"


def test_unknown_inventory_value_remains_unknown(approval_case):
    case = approval_case
    case["snapshots"][1].total_value = None
    case["session"].commit()
    case["app"].state.test_principal = case["principals"][1]
    detail = case["client"].get(f"/api/v1/sanitization/{case['proposal'].id}").json()
    assert detail["consolidated_value_brl"] is None
    case["app"].state.test_principal = case["principals"][0]
    assert decide(case).status_code == 200


def test_missing_unit_is_visible_but_cannot_be_consolidated(approval_case):
    from test_contracts import validator

    case = approval_case
    case["snapshots"][0].unit = None
    case["materials"][0].unit = None
    case["session"].commit()
    response = case["client"].get(f"/api/v1/sanitization/{case['proposal'].id}")
    assert response.status_code == 200
    validator({"$ref": "#/components/schemas/Proposal"}).validate(response.json())
    assert "APPROVE" not in response.json()["allowed_actions"]
    assert decide(case).status_code == 422


def test_large_decimal_quantities_are_not_rounded_to_float_or_default_precision(approval_case):
    case = approval_case
    quantity = Decimal("123456789012345678901234567890.123456789")
    factor = Decimal("12345678901234567890.123456789")
    value = Decimal("987654321098765432109876543210.987654321")
    case["snapshots"][1].quantity = quantity
    case["snapshots"][1].total_value = value
    case["snapshots"][1].unit = "CX"
    changes = copy.deepcopy(case["proposal"].changeset)
    changes["conversions"] = [
        {"from_unit": "CX", "to_unit": "PC", "factor": str(factor), "source": "Fator conhecido do cadastro."}
    ]
    case["proposal"].changeset = changes
    persist(case)
    response = decide(case)
    assert response.status_code == 200, response.text
    audit = case["session"].get(AuditLog, uuid.UUID(response.json()["audit_event_id"]))
    with localcontext() as context:
        context.prec = 200
        assert sum(Decimal(row["quantity"]) for row in audit.after_json["inventory"]) == quantity * factor + 3
        assert sum(Decimal(row["total_value"]) for row in audit.after_json["inventory"]) == value + 30


def test_fiscal_only_correction_does_not_canonicalize_or_change_technical_data(approval_case):
    case = approval_case
    db = case["session"]
    proposal = case["proposal"]
    proposal.proposal_type = "NCM_CORRECTION"
    proposal.members = proposal.members[:1]
    proposal.technical_review_status = "NOT_REQUIRED"
    proposal.fiscal_review_status = "PENDING"
    changes = copy.deepcopy(proposal.changeset)
    case["materials"][0].ncm = "8421.31.00"
    changes["after"]["ncm"] = "8421.23.00"
    changes["sources"]["ncm"] = "Referencia fiscal conferida."
    proposal.changeset = changes
    persist(case)
    case["app"].state.test_principal = case["principals"][1]
    response = decide(
        case, payload={"expected_version": 1, "review_area": "FISCAL", "decision": "APPROVE", "reason": "Conferido."}
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    assert not case["materials"][0].is_canonical
    assert case["materials"][0].identity_key is None
    assert case["materials"][0].ncm == changes["after"]["ncm"]
    assert case["materials"][1].version == 1
    assert db.scalar(select(func.count()).select_from(InventoryConsolidation)) == 0


def enrichment_proposal(case):
    proposal = case["proposal"]
    proposal.proposal_type = "ENRICHMENT"
    proposal.members = proposal.members[:1]
    proposal.fiscal_review_status = "PENDING"
    changes = copy.deepcopy(proposal.changeset)
    changes["after"]["attributes"]["ALTURA"] = "100MM"
    changes["sources"]["attributes"] = "Ficha tecnica do fabricante."
    source = EnrichmentSource(
        id=uuid.uuid4(),
        tenant_id=case["principals"][0].tenant_id,
        material_id=case["materials"][0].id,
        attribute_name="ALTURA",
        proposed_value="100MM",
        source_url="https://example.com/catalogo",
        source_sha256="a" * 64,
        retrieved_at=datetime.now(UTC),
        confidence_level="ALTA",
    )
    case["session"].add(source)
    case["session"].flush()
    proposal.evidence_ids = [str(source.id)]
    changes["evidence_hashes"] = {str(source.id): evidence_hash(source)}
    proposal.changeset = changes
    persist(case)
    return source


def test_enrichment_applies_only_the_evidence_bound_persisted_value(approval_case):
    case = approval_case
    source = enrichment_proposal(case)
    first = decide(case)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    case["app"].state.test_principal = case["principals"][1]
    fiscal = {"expected_version": 2, "review_area": "FISCAL", "decision": "APPROVE", "reason": "Base fiscal revisada."}
    response = decide(case, payload=fiscal, key=str(uuid.uuid4()))
    assert response.status_code == 200, response.text
    case["session"].expire_all()
    assert case["materials"][0].attributes["ALTURA"] == "100MM"
    assert source.validated_by_user_id == case["principals"][0].user_id


def test_mutating_a_bound_evidence_blocks_enrichment(approval_case):
    case = approval_case
    source = enrichment_proposal(case)
    source.source_url = "https://example.com/changed"
    case["session"].commit()
    response = decide(case)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_CHANGED"


def test_reusing_consolidated_stock_does_not_duplicate_or_reconvert_it(approval_case):
    case = approval_case
    db = case["session"]
    case["snapshots"][1].unit = "CX"
    changes = copy.deepcopy(case["proposal"].changeset)
    changes["conversions"] = [{"from_unit": "CX", "to_unit": "PC", "factor": "10", "source": "Caixa com dez pecas."}]
    case["proposal"].changeset = changes
    persist(case)
    assert decide(case).status_code == 200
    db.expire_all()
    primary = case["materials"][0]
    added = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=primary.tenant_id,
        source_system="ERP",
        material_code="300",
        status="ATIVO",
        pdm_class_id=primary.pdm_class_id,
        attributes=primary.attributes,
        unit="PC",
        ncm=primary.ncm,
        manufacturer=primary.manufacturer,
        manufacturer_reference=primary.manufacturer_reference,
        pdm_description=primary.pdm_description,
    )
    db.add(added)
    db.flush()
    db.add(
        MaterialInventorySnapshot(
            tenant_id=primary.tenant_id,
            dataset_id=case["dataset"].id,
            material_id=added.id,
            center_code="1200",
            unit="PC",
            quantity=Decimal(4),
            total_value=Decimal(40),
            source_line=4,
        )
    )
    members = [
        case["proposal"].members[0] | {"expected_version": primary.version},
        case["proposal"].members[0] | {"material_id": str(added.id), "expected_version": 1},
    ]
    changes = copy.deepcopy(changes)
    changes["conversions"] = []
    from domain.proposals import proposal_hash

    proposal = SanitizationProposal(
        id=uuid.uuid4(),
        tenant_id=primary.tenant_id,
        proposal_type="MERGE",
        primary_material_id=primary.id,
        members=members,
        changeset=changes,
        changeset_hash=proposal_hash(members, changes),
        technical_review_status="PENDING",
        fiscal_review_status="NOT_REQUIRED",
    )
    db.add(proposal)
    db.commit()
    case["proposal"] = proposal
    response = decide(case, key=str(uuid.uuid4()))
    assert response.status_code == 200, response.text
    audit = db.get(AuditLog, uuid.UUID(response.json()["audit_event_id"]))
    assert sum(Decimal(row["quantity"]) for row in audit.after_json["inventory"]) == 37
    assert sum(Decimal(row["total_value"]) for row in audit.after_json["inventory"]) == 100
    assert db.scalar(select(func.count()).select_from(InventoryConsolidation)) == 4
