"""Aprovação em lote de correções de forma depois de revisar uma amostra (#120)."""

import uuid

import pytest
from sqlalchemy import func, select

from vx_materials_api.db.models import AuditLog, LotReview, MaterialMaster, OperationRequest, SanitizationProposal
from vx_materials_api.schemas.proposals import proposal_hash

LOT_KEY = "UNIT_CORRECTION|rule_based_v1/unit.alias|PDM100"
LOTS = "/api/v1/sanitization/lots"
REVIEWS = "/api/v1/sanitization/lots/reviews"


def unit_proposal(case, code, *, tier=1, lot_key=LOT_KEY, lane=True, fiscal="NOT_REQUIRED"):
    """Correção de grafia de unidade de um material, como o batch grava, com o nível de revisão da #119."""
    db, catalog = case["session"], case["catalog"]
    material = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=case["dataset"].tenant_id,
        source_system="ERP",
        material_code=code,
        status="ATIVO",
        original_description_long=f"ANEL VEDACAO {code}",
        unit="PCA",
        version=1,
    )
    db.add(material)
    db.flush()
    members = [
        {
            "material_id": str(material.id),
            "expected_version": 1,
            "pdm_class_id": None,
            "item_name": None,
            "attributes": {},
        }
    ]
    changeset = {
        "schema_version": "proposal-v1",
        "dataset_id": str(case["dataset"].id),
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "after": {"pdm_class_id": None, "item_name": None, "attributes": {}, "unit": "PC", "ncm": None},
        "conversions": [],
        "conflicts": [],
        "sources": {"unit": "rule_based_v1/unit.alias"},
        "changes": [{"field": "unit", "before": "PCA", "after": "PC", "source": "rule_based_v1/unit.alias"}],
    }
    if lane:
        changeset["review_lane"] = {"tier": tier, "lot_key": lot_key, "reasons": [] if tier < 3 else ["CONFLICT"]}
    proposal = SanitizationProposal(
        id=uuid.uuid4(),
        tenant_id=case["dataset"].tenant_id,
        proposal_type="UNIT_CORRECTION",
        members=members,
        primary_material_id=material.id,
        changeset=changeset,
        changeset_hash=proposal_hash(members, changeset),
        technical_review_status="PENDING",
        fiscal_review_status=fiscal,
        version=1,
    )
    db.add(proposal)
    return material, proposal


@pytest.fixture
def lot_case(approval_case):
    case = approval_case
    pairs = [unit_proposal(case, f"U{index:03d}") for index in range(25)]
    # Fora de qualquer lote: lote pequeno, nível 3, sem nível gravado e com revisão fiscal.
    for index in range(5):
        unit_proposal(case, f"S{index:03d}", lot_key="UNIT_CORRECTION|rule_based_v1/unit.alias|PDM001")
    for index in range(25):
        unit_proposal(case, f"T{index:03d}", tier=3, lot_key="UNIT_CORRECTION|rule_based_v1/unit.alias|PDM002")
    for index in range(25):
        unit_proposal(case, f"N{index:03d}", lane=False)
    for index in range(25):
        unit_proposal(case, f"F{index:03d}", lot_key="UNIT_CORRECTION|x|PDM003", fiscal="PENDING")
    case["session"].commit()
    case["lot"] = pairs
    return case


def as_persona(case, index):
    case["app"].state.test_principal = case["principals"][index]


def open_lot(case, lot_key=LOT_KEY, tier=1):
    return case["client"].post(REVIEWS, json={"lot_key": lot_key, "tier": tier}, headers=case["headers"])


def decide_lot(case, review, *, verdicts=None, key=None, reason="Amostra conferida."):
    verdicts = verdicts or {}
    marks = [
        {"proposal_id": i["proposal_id"], "verdict": verdicts.get(i["proposal_id"], "CORRECT")}
        for i in review["sample"]
    ]
    headers = case["headers"] | {"Idempotency-Key": key or str(uuid.uuid4())}
    return case["client"].post(
        f"{REVIEWS}/{review['id']}/decide",
        json={"expected_version": review["version"], "marks": marks, "reason": reason},
        headers=headers,
    )


def count(db, model, *criteria):
    return db.scalar(select(func.count()).select_from(model).where(*criteria))


def test_only_tier_1_and_2_lots_with_enough_pending_items_are_listed(lot_case):
    response = lot_case["client"].get(LOTS)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(i["lot_key"], i["tier"], i["size"], i["sample_size"]) for i in items] == [(LOT_KEY, 1, 25, 10)]
    assert items[0]["rule"] == "rule_based_v1/unit.alias"
    assert items[0]["pdm_class_id"] == "PDM100"
    assert items[0]["open_review_id"] is None


def test_opening_draws_a_stable_server_sample(lot_case):
    first = open_lot(lot_case)
    assert first.status_code == 201, first.text
    review = first.json()
    ids = {str(p.id) for _, p in lot_case["lot"]}
    sample = [i["proposal_id"] for i in review["sample"]]
    assert len(sample) == 10 and set(sample) <= ids
    assert review["sample"][0]["changes"][0]["after"] == "PC"
    again = open_lot(lot_case)
    assert again.status_code == 200
    assert again.json()["id"] == review["id"]
    assert [i["proposal_id"] for i in again.json()["sample"]] == sample
    read = lot_case["client"].get(f"{REVIEWS}/{review['id']}").json()
    assert [i["proposal_id"] for i in read["sample"]] == sample
    assert lot_case["client"].get(LOTS).json()["items"][0]["open_review_id"] == review["id"]
    db = lot_case["session"]
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "LOT_REVIEW_OPEN")) == 1


def test_a_clean_sample_applies_every_item_with_its_own_audit(lot_case):
    review = open_lot(lot_case).json()
    response = decide_lot(lot_case, review)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["result"]["counts"] == {"APPLIED": 25, "STALE": 0, "SKIPPED": 0}
    db = lot_case["session"]
    db.expire_all()
    assert {m.unit for m, _ in lot_case["lot"]} == {"PC"}
    assert {p.status for _, p in lot_case["lot"]} == {"APPLIED"}
    audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "PROPOSAL_APPROVE_TECHNICAL")))
    assert len(audits) == 25
    assert {a.after_json["lot_review"]["id"] for a in audits} == {review["id"]}
    assert all(len(a.after_json["lot_review"]["sample_ids"]) == 10 for a in audits)
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "LOT_REVIEW_APPROVE")) == 1
    assert lot_case["client"].get(LOTS).json()["items"] == []


def test_any_wrong_item_returns_the_whole_lot_to_individual_review(lot_case):
    review = open_lot(lot_case).json()
    wrong = review["sample"][3]["proposal_id"]
    response = decide_lot(lot_case, review, verdicts={wrong: "WRONG"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RETURNED"
    assert response.json()["result"] == {"wrong_ids": [wrong], "rule": "rule_based_v1/unit.alias"}
    db = lot_case["session"]
    db.expire_all()
    assert {m.unit for m, _ in lot_case["lot"]} == {"PCA"}
    assert {p.status for _, p in lot_case["lot"]} == {"PENDING"}
    assert lot_case["client"].get(LOTS).json()["items"] == []
    assert open_lot(lot_case).status_code == 422
    stored = db.get(LotReview, uuid.UUID(review["id"]))
    assert stored.marks[wrong] == "WRONG"


def test_the_whole_sample_must_be_marked(lot_case):
    review = open_lot(lot_case).json()
    review["sample"] = review["sample"][:-1]
    response = decide_lot(lot_case, review)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SAMPLE_INCOMPLETE"


def test_changed_or_already_decided_items_do_not_block_the_rest(lot_case):
    review = open_lot(lot_case).json()
    db = lot_case["session"]
    (changed, _), (_, decided), (broken, _) = lot_case["lot"][0], lot_case["lot"][1], lot_case["lot"][2]
    changed.version = 2
    decided.status = "REJECTED"
    # Mudou a grafia sem nova versão: a correção deixa de valer e o item falha sozinho.
    broken.unit = "XYZ"
    db.commit()
    response = decide_lot(lot_case, review)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["counts"] == {"APPLIED": 22, "STALE": 1, "SKIPPED": 2}
    codes = {i["proposal_id"]: i.get("code") for i in result["items"]}
    assert codes[str(lot_case["lot"][1][1].id)] == "PROPOSAL_FINALIZED"
    assert codes[str(lot_case["lot"][2][1].id)] == "UNIT_NOT_ALIAS"
    db.expire_all()
    assert broken.unit == "XYZ" and broken.version == 1
    assert lot_case["lot"][0][1].status == "STALE"


def test_repeating_the_decision_does_not_apply_twice(lot_case):
    review = open_lot(lot_case).json()
    key = str(uuid.uuid4())
    first = decide_lot(lot_case, review, key=key)
    again = decide_lot(lot_case, review, key=key)
    assert first.status_code == again.status_code == 200
    assert again.json() == first.json()
    db = lot_case["session"]
    assert count(db, AuditLog, AuditLog.action == "PROPOSAL_APPROVE_TECHNICAL") == 25
    other = decide_lot(lot_case, review, key=key, reason="Outra justificativa.")
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    later = decide_lot(lot_case, review)
    assert later.status_code == 409
    assert later.json()["error"]["code"] == "VERSION_CONFLICT"
    assert count(db, OperationRequest, OperationRequest.operation == "sanitization.lot_decide") == 1


@pytest.mark.parametrize("persona", [1, 2])
def test_only_governance_handles_lots(lot_case, persona):
    review = open_lot(lot_case).json()
    as_persona(lot_case, persona)
    assert lot_case["client"].get(LOTS).status_code == 403
    assert open_lot(lot_case).status_code == 403
    assert lot_case["client"].get(f"{REVIEWS}/{review['id']}").status_code == 403
    assert decide_lot(lot_case, review).status_code == 403


def test_writes_require_csrf(lot_case):
    review = open_lot(lot_case).json()
    headers = {"Origin": "http://localhost:8000", "Idempotency-Key": str(uuid.uuid4())}
    response = lot_case["client"].post(REVIEWS, json={"lot_key": LOT_KEY, "tier": 1}, headers=headers)
    assert response.status_code == 403
    marks = [{"proposal_id": i["proposal_id"], "verdict": "CORRECT"} for i in review["sample"]]
    response = lot_case["client"].post(
        f"{REVIEWS}/{review['id']}/decide",
        json={"expected_version": review["version"], "marks": marks, "reason": "ok"},
        headers=headers,
    )
    assert response.status_code == 403
