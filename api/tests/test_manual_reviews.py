"""Pendências reais do corretor, escopo da Governança e encaminhamento à aprovação existente."""

import copy
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from domain.contracts import AnalyzedMaterial, MaterialRecord
from pipelines.corrections import propose_corrections
from repositories.corrections import get_correction_repository
from repositories.manual_reviews import save_manual_reviews
from repositories.normalization import get_normalization_repository
from vx_materials_api.db.models import AuditLog, ManualReview, SanitizationProposal


@pytest.fixture
def pending_case(approval_case):
    case = approval_case
    db = case["session"]
    analyzed = []
    for material in case["materials"]:
        record = MaterialRecord(
            code=material.material_code,
            status="ATIVO",
            description="FILTRO FLEETGUARD",
            unit="PC",
            ncm=material.ncm,
            database_id=str(material.id),
            version=1,
        )
        analyzed.append(
            AnalyzedMaterial(record, "PDM100", "FILTRO OLEO LUBRIFICANTE", {"FABRICANTE": "FLEETGUARD"}, None)
        )
    by_code = {}
    _, counts = propose_corrections(
        analyzed, case["catalog"], get_normalization_repository(), get_correction_repository(), by_code
    )
    context = SimpleNamespace(
        tenant_id=str(case["principals"][0].tenant_id), job_id=None, checkpoint={"analysis_signature": "test-rules"}
    )
    args = ([m.record for m in analyzed], analyzed, by_code, context, case["catalog"], "head_noun_v1")
    run_id = save_manual_reviews(db.connection(), *args)
    # A mesma execução é repetível, sem apagar o encaminhamento posterior.
    save_manual_reviews(db.connection(), *args)
    db.commit()
    rows = list(
        db.scalars(
            select(ManualReview).where(ManualReview.run_id == uuid.UUID(run_id)).order_by(ManualReview.material_id)
        )
    )
    case.update(
        reviews=rows,
        pending_counts=dict(counts),
        run_id=run_id,
        resolution={
            "expected_material_version": 1,
            "pdm_class_id": "PDM100",
            "item_name": "FILTRO OLEO LUBRIFICANTE",
            "attributes": {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009"},
            "unit": "PC",
            "ncm": "8421.23.00",
            "source": "Catálogo conferido: LF9009 FLEETGUARD.",
            "reason": "Completar referência ausente.",
        },
    )
    return case


def propose(case, payload=None, headers=None):
    return case["client"].post(
        f"/api/v1/manual-reviews/{case['reviews'][0].id}/propose",
        json=payload if payload is not None else case["resolution"],
        headers=headers if headers is not None else case["headers"],
    )


def test_counts_match_report_and_filtering_paginates_without_proposals(pending_case):
    case = pending_case
    response = case["client"].get("/api/v1/manual-reviews?limit=1")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["counts_by_reason"] == case["pending_counts"]
    assert result["materials_total"] == 2
    assert len(result["items"]) == 1 and result["next_cursor"]
    second = (
        case["client"]
        .get("/api/v1/manual-reviews", params={"run_id": result["run_id"], "cursor": result["next_cursor"], "limit": 1})
        .json()
    )
    assert second["items"][0]["id"] != result["items"][0]["id"]
    assert second["next_cursor"] is None
    code = result["items"][0]["observation"]["material_code"]
    filtered = (
        case["client"]
        .get("/api/v1/manual-reviews", params={"material_code": code, "reason": next(iter(case["pending_counts"]))})
        .json()
    )
    assert len(filtered["items"]) == 1 and filtered["counts_by_reason"] == case["pending_counts"]
    assert not {"before", "after", "value_brl", "inventory"} & result["items"][0].keys()
    assert (
        case["session"].scalar(
            select(func.count())
            .select_from(SanitizationProposal)
            .where(SanitizationProposal.tenant_id == case["principals"][0].tenant_id)
        )
        == 1
    )


def test_proposing_does_not_edit_material_and_normal_approval_applies(pending_case):
    case = pending_case
    before = [(m.id, m.version, m.pdm_description, m.attributes) for m in case["materials"]]
    response = propose(case)
    assert response.status_code == 202, response.text
    result = response.json()
    db = case["session"]
    db.expire_all()
    assert [(m.id, m.version, m.pdm_description, m.attributes) for m in case["materials"]] == before
    proposal = db.get(SanitizationProposal, uuid.UUID(result["proposal_id"]))
    assert proposal.proposal_type == "PDM_CORRECTION" and proposal.status == "PENDING"
    assert proposal.changeset["conflicts"] == []
    assert proposal.changeset["review_lane"]["tier"] == 3
    assert proposal.changeset["ncm_assessment"]["technical_consistency"] == "CONSISTENT"
    event = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "MANUAL_REVIEW_PROPOSE", AuditLog.tenant_id == case["principals"][0].tenant_id
        )
    )
    assert event.actor_user_id == case["principals"][0].user_id
    assert event.reason == case["resolution"]["reason"]
    approved = case["client"].post(
        f"/api/v1/sanitization/{proposal.id}/decide",
        json={"expected_version": 1, "review_area": "TECHNICAL", "decision": "APPROVE", "reason": "Conferido."},
        headers=case["headers"] | {"Idempotency-Key": str(uuid.uuid4())},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPLIED"
    db.expire_all()
    material = next(m for m in case["materials"] if m.id == case["reviews"][0].material_id)
    assert material.version == 2
    listed = case["client"].get("/api/v1/manual-reviews").json()
    assert listed["counts_by_reason"] == case["pending_counts"]
    assert next(r for r in listed["items"] if r["id"] == str(case["reviews"][0].id))["proposal_status"] == "APPLIED"


def test_idempotency_and_duplicate_submission(pending_case):
    first = propose(pending_case)
    assert first.status_code == 202, first.text
    assert propose(pending_case).json() == first.json()
    changed = pending_case["resolution"] | {"reason": "Outro conteúdo"}
    assert propose(pending_case, changed).json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    result = propose(pending_case, headers=pending_case["headers"] | {"Idempotency-Key": str(uuid.uuid4())})
    assert result.status_code == 409 and result.json()["error"]["code"] == "ALREADY_PROPOSED"


@pytest.mark.parametrize("role_index", [1, 2])
def test_only_governance_can_read_or_propose(pending_case, role_index):
    case = pending_case
    case["app"].state.test_principal = case["principals"][role_index]
    assert case["client"].get("/api/v1/manual-reviews").status_code == 403
    assert propose(case).status_code == 403


@pytest.mark.parametrize("scope", ["tenant", "center", "permissions"])
def test_scope_is_checked_on_list_and_write(pending_case, scope):
    case = pending_case
    principal = case["principals"][0]
    case["app"].state.test_principal = replace(
        principal,
        **{
            "tenant": {"tenant_id": uuid.uuid4()},
            "center": {"center_codes": frozenset()},
            "permissions": {"permissions": frozenset()},
        }[scope],
    )
    result = case["client"].get("/api/v1/manual-reviews")
    if scope == "permissions":
        assert result.status_code == 403
        assert propose(case).status_code == 403
    else:
        assert result.json()["items"] == []
        assert result.json()["counts_by_reason"] == {}
        assert propose(case).status_code == 404


def test_cookie_writes_require_origin_and_csrf(pending_case):
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    assert propose(pending_case, headers=headers).status_code == 403
    assert propose(pending_case, headers=headers | {"Origin": "http://localhost:8000"}).status_code == 403


@pytest.mark.parametrize(
    "change,code",
    [
        ({"attributes": {}}, "PDM_INVALID"),
        ({"pdm_class_id": "unknown"}, "PDM_INVALID"),
        ({"ncm": "0000.00.00"}, "NCM_REFERENCE_MISMATCH"),
        ({"expected_material_version": 2}, "STALE_MATERIAL"),
    ],
)
def test_invalid_resolution_stays_pending(pending_case, change, code):
    response = propose(pending_case, pending_case["resolution"] | change)
    assert response.status_code in (409, 422), response.text
    assert response.json()["error"]["code"] == code
    pending_case["session"].expire_all()
    assert pending_case["reviews"][0].proposal_id is None


def test_stale_material_and_changed_pdm_are_refused(pending_case):
    case = pending_case
    material = next(m for m in case["materials"] if m.id == case["reviews"][0].material_id)
    material.version = 2
    case["session"].commit()
    assert propose(case).json()["error"]["code"] == "STALE_MATERIAL"
    material.version = 1
    case["reviews"][0].pdm_source_sha256 = "0" * 64
    case["session"].commit()
    assert propose(case).json()["error"]["code"] == "REFERENCE_CHANGED"


def test_packaging_needs_explicit_factor_and_source(pending_case):
    case = pending_case
    material_id = case["reviews"][0].material_id
    snapshot = next(s for s in case["snapshots"] if s.material_id == material_id)
    snapshot.unit = "CX"
    case["session"].commit()
    rejected = propose(case)
    assert rejected.status_code == 422, rejected.text
    payload = copy.deepcopy(case["resolution"])
    payload["conversions"] = [
        {"from_unit": "CX", "to_unit": "PC", "factor": "10", "source": "Fabricante: dez peças por caixa."}
    ]
    accepted = propose(case, payload)
    assert accepted.status_code == 202, accepted.text
    case["session"].expire_all()
    assert snapshot.unit == "CX"


def test_changed_fiscal_basis_requires_both_reviews(pending_case):
    case = pending_case
    payload = copy.deepcopy(case["resolution"])
    payload["attributes"]["REFERENCIA FABRICANTE"] = "LF9008"
    response = propose(case, payload)
    assert response.status_code == 202, response.text
    proposal = case["session"].get(SanitizationProposal, uuid.UUID(response.json()["proposal_id"]))
    assert proposal.technical_review_status == "PENDING" and proposal.fiscal_review_status == "PENDING"


def test_catalog_uses_loaded_pdm_and_is_restricted(pending_case):
    case = pending_case
    response = case["client"].get("/api/v1/manual-reviews/catalog")
    assert response.status_code == 200
    result = response.json()
    assert result["pdm_version"] == case["catalog"].version
    assert len(result["classes"]) == len(case["catalog"].classes)
    case["app"].state.test_principal = case["principals"][1]
    assert case["client"].get("/api/v1/manual-reviews/catalog").status_code == 403


def test_changed_material_after_proposing_uses_existing_stale_guard(pending_case):
    case = pending_case
    response = propose(case)
    assert response.status_code == 202, response.text
    material = next(m for m in case["materials"] if m.id == case["reviews"][0].material_id)
    material.version = 2
    case["session"].commit()
    approved = case["client"].post(
        f"/api/v1/sanitization/{response.json()['proposal_id']}/decide",
        json={"expected_version": 1, "review_area": "TECHNICAL", "decision": "APPROVE", "reason": "Conferido."},
        headers=case["headers"] | {"Idempotency-Key": str(uuid.uuid4())},
    )
    assert approved.status_code == 409
    assert approved.json()["error"]["code"] == "STALE_PROPOSAL"


def test_list_and_proposal_match_public_contract(pending_case):
    from test_contracts import validator

    case = pending_case
    for path, schema in (
        ("/api/v1/manual-reviews", "ManualReviewList"),
        ("/api/v1/manual-reviews/catalog", "ManualReviewCatalog"),
    ):
        response = case["client"].get(path)
        assert response.status_code == 200
        validator({"$ref": f"#/components/schemas/{schema}"}).validate(response.json())
    response = propose(case)
    assert response.status_code == 202, response.text
    validator({"$ref": "#/components/schemas/ManualReviewProposed"}).validate(response.json())


def test_audit_failure_rolls_back_proposal_and_review_link(pending_case):
    from sqlalchemy import event

    case = pending_case

    def reject_event(mapper, connection, target):
        if target.action == "MANUAL_REVIEW_PROPOSE":
            raise RuntimeError("Falha simulada da auditoria")

    event.listen(AuditLog, "before_insert", reject_event)
    try:
        with pytest.raises(RuntimeError, match="Falha simulada"):
            propose(case)
    finally:
        event.remove(AuditLog, "before_insert", reject_event)
    db = case["session"]
    db.expire_all()
    assert case["reviews"][0].proposal_id is None
    assert (
        db.scalar(
            select(func.count())
            .select_from(SanitizationProposal)
            .where(SanitizationProposal.tenant_id == case["principals"][0].tenant_id)
        )
        == 1
    )


def test_inherited_inventory_outside_scope_is_hidden(pending_case):
    from vx_materials_api.db.models import InventoryConsolidation

    case = pending_case
    review = next(r for r in case["reviews"] if r.material_id == case["materials"][0].id)
    case["reviews"] = [review]
    snapshot = next(s for s in case["snapshots"] if s.center_code == "1200")
    case["session"].add(
        InventoryConsolidation(
            source_snapshot_id=snapshot.id,
            tenant_id=case["principals"][0].tenant_id,
            primary_material_id=review.material_id,
            proposal_id=case["proposal"].id,
            factor=1,
            unit="PC",
            conversion_source="Identidade conferida.",
        )
    )
    case["session"].commit()
    case["app"].state.test_principal = replace(case["principals"][0], center_codes=frozenset({"1100"}))
    assert case["client"].get("/api/v1/manual-reviews").json()["items"] == []
    assert propose(case).status_code == 404


def test_api_credential_can_only_link_the_generated_proposal(pending_case):
    from sqlalchemy.orm import Session

    case = pending_case
    connection = case["session"].connection()

    def factory():
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        db.execute(text("SET LOCAL ROLE api_user"))
        return db

    case["app"].state.session_factory = factory
    try:
        response = propose(case)
        assert response.status_code == 202, response.text
    finally:
        connection.execute(text("RESET ROLE"))


def test_rejected_resolution_can_be_proposed_again_with_history(pending_case):
    case = pending_case
    first = propose(case)
    assert first.status_code == 202, first.text
    proposal_id = first.json()["proposal_id"]
    rejected = case["client"].post(
        f"/api/v1/sanitization/{proposal_id}/decide",
        json={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "REJECT",
            "reason": "Rever a fonte informada.",
        },
        headers=case["headers"] | {"Idempotency-Key": str(uuid.uuid4())},
    )
    assert rejected.status_code == 200, rejected.text
    second = propose(case, headers=case["headers"] | {"Idempotency-Key": str(uuid.uuid4())})
    assert second.status_code == 202, second.text
    assert second.json()["proposal_id"] != proposal_id
    case["session"].expire_all()
    assert case["session"].get(SanitizationProposal, uuid.UUID(proposal_id)).status == "REJECTED"


def test_ncm_listed_for_another_item_is_rejected_by_shared_rules(pending_case):
    case = pending_case
    # Mesmo conjunto de referências da classe: filtro de óleo não usa o código de filtro de ar.
    response = propose(case, case["resolution"] | {"ncm": "8421.31.00"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "NCM_REFERENCE_MISMATCH"
    case["session"].expire_all()
    assert case["reviews"][0].proposal_id is None


@pytest.mark.parametrize("ncm", ["8421.23.00", "84212300"])
def test_ncm_is_accepted_in_either_spelling(pending_case, ncm):
    # A base traz NCM sem pontos; o PDM, com pontos. A mesma normalização da aprovação vale aqui.
    case = pending_case
    response = propose(case, case["resolution"] | {"ncm": ncm})
    assert response.status_code == 202, response.text
    proposal = case["session"].get(SanitizationProposal, uuid.UUID(response.json()["proposal_id"]))
    assert proposal.changeset["after"]["ncm"] == ncm
    assert proposal.changeset["ncm_assessment"]["technical_consistency"] == "CONSISTENT"


def test_original_stock_alias_is_supported_after_master_spelling_was_corrected(pending_case):
    case = pending_case
    row = case["reviews"][0]
    snapshot = next(s for s in case["snapshots"] if s.material_id == row.material_id)
    snapshot.unit = "UN"
    case["session"].commit()
    response = propose(case)
    assert response.status_code == 202, response.text
    proposal = case["session"].get(SanitizationProposal, uuid.UUID(response.json()["proposal_id"]))
    conversion = next(c for c in proposal.changeset["conversions"] if c["from_unit"] == "UN")
    assert conversion["to_unit"] == "PC" and conversion["factor"] == "1"
    assert conversion["source"]
    approved = case["client"].post(
        f"/api/v1/sanitization/{proposal.id}/decide",
        json={"expected_version": 1, "review_area": "TECHNICAL", "decision": "APPROVE", "reason": "Alias conferido."},
        headers=case["headers"] | {"Idempotency-Key": str(uuid.uuid4())},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPLIED"
    case["session"].expire_all()
    assert snapshot.unit == "UN"


def test_manual_proposals_never_form_a_sample_review_lot(pending_case):
    case = pending_case
    response = propose(case)
    assert response.status_code == 202, response.text
    db = case["session"]
    proposal = db.get(SanitizationProposal, uuid.UUID(response.json()["proposal_id"]))
    # Mesmo acima do mínimo de 20, encaminhamentos individuais não viram lote.
    for _ in range(20):
        db.add(
            SanitizationProposal(
                id=uuid.uuid4(),
                tenant_id=proposal.tenant_id,
                proposal_type=proposal.proposal_type,
                primary_material_id=proposal.primary_material_id,
                members=copy.deepcopy(proposal.members),
                changeset=copy.deepcopy(proposal.changeset),
                changeset_hash=proposal.changeset_hash,
                technical_review_status="PENDING",
                fiscal_review_status=proposal.fiscal_review_status,
            )
        )
    db.commit()
    lots = case["client"].get("/api/v1/sanitization/lots")
    assert lots.status_code == 200, lots.text
    assert lots.json()["items"] == []


def test_manual_factor_cannot_inflate_quantities_for_a_known_unit_alias(pending_case):
    case = pending_case
    snapshot = next(s for s in case["snapshots"] if s.material_id == case["reviews"][0].material_id)
    snapshot.unit = "UN"
    case["session"].commit()
    payload = case["resolution"] | {
        "conversions": [
            {"from_unit": "UN", "to_unit": "PC", "factor": "2", "source": "Fonte não supera a regra do alias."}
        ]
    }
    response = propose(case, payload)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "UNIT_ALIAS_FACTOR"
    case["session"].expire_all()
    assert case["reviews"][0].proposal_id is None and snapshot.unit == "UN"


@pytest.mark.parametrize("factor", ["1", "10"])
def test_missing_inventory_unit_requires_evidenced_conversion_and_normal_approval(pending_case, factor):
    from decimal import Decimal

    from vx_materials_api.db.models import InventoryConsolidation

    case = pending_case
    db = case["session"]
    review = case["reviews"][0]
    material = next(m for m in case["materials"] if m.id == review.material_id)
    snapshots = [s for s in case["snapshots"] if s.material_id == material.id]
    material.unit = None
    for snapshot in snapshots:
        snapshot.unit = None
    review.observation = {**review.observation, "unit": ""}
    review.reasons = ["UNIDADE_AUSENTE"]
    db.commit()
    original = [(s.id, s.quantity, s.total_value, dict(s.raw_record)) for s in snapshots]
    missing = propose(case)
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "UNIT_FACTOR_REQUIRED"
    conversion = {
        "from_unit": "",
        "to_unit": "PC",
        "factor": factor,
        "source": "Inventário conferido pelo responsável: saldo original convertido em peças.",
    }
    no_source = propose(case, case["resolution"] | {"conversions": [{**conversion, "source": ""}]})
    assert no_source.status_code == 422
    accepted = propose(case, case["resolution"] | {"conversions": [conversion]})
    assert accepted.status_code == 202, accepted.text
    db.expire_all()
    assert material.unit is None and material.version == 1
    assert all(s.unit is None for s in snapshots)
    proposal = db.get(SanitizationProposal, uuid.UUID(accepted.json()["proposal_id"]))
    assert proposal.changeset["conversions"] == [conversion]
    approved = case["client"].post(
        f"/api/v1/sanitization/{proposal.id}/decide",
        json={"expected_version": 1, "review_area": "TECHNICAL", "decision": "APPROVE", "reason": "Fonte conferida."},
        headers=case["headers"] | {"Idempotency-Key": str(uuid.uuid4())},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "APPLIED", approved.text
    db.expire_all()
    assert material.unit == "PC" and material.version == 2
    assert [(s.id, s.quantity, s.total_value, dict(s.raw_record)) for s in snapshots] == original
    assert all(s.unit is None for s in snapshots)
    links = [db.get(InventoryConsolidation, s.id) for s in snapshots]
    assert all(link.factor == Decimal(factor) and link.unit == "PC" for link in links)
    assert all(link.conversion_source == conversion["source"] for link in links)
