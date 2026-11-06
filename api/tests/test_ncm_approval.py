"""Motor NCM compartilhado e ciclo batch → revisões → auditoria."""

import copy
import json
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from approval_fixtures import decide, persist
from sqlalchemy import select

from domain.contracts import AnalyzedMaterial, MaterialRecord
from domain.ncm_rules import check_ncm_consistency
from domain.pdm_formatter import format_description
from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from pipelines.ncm_corrections import propose_ncm_corrections
from repositories.proposal_payload import approval_payload
from vx_materials_api.db.models import AuditLog
from vx_materials_api.errors import ApiError
from vx_materials_api.services.ncm_validation import evaluate_proposed_ncm


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


def test_code_in_class_union_is_not_enough_when_its_condition_is_wrong(catalog):
    changes = SimpleNamespace(
        after=SimpleNamespace(
            pdm_class_id="PDM050",
            item_name="FLANGE",
            attributes={"MATERIAL": "ACO CARBONO FORJADO A105"},
            ncm="7307.21.00",
        ),
        ncm_assessment=None,
    )
    with pytest.raises(ApiError) as error:
        evaluate_proposed_ncm(catalog, changes)
    assert error.value.code == "NCM_REFERENCE_MISMATCH"


def test_changed_fiscal_basis_requires_a_new_assessment(catalog):
    attributes = {"MATERIAL": "ACO CARBONO FORJADO A105"}
    stored = asdict(check_ncm_consistency(catalog, "PDM050", attributes, "7307.91.00", item_name="FLANGE"))
    changes = SimpleNamespace(
        after=SimpleNamespace(
            pdm_class_id="PDM050",
            item_name="FLANGE",
            attributes={"MATERIAL": "ACO INOX FORJADO A182 F316"},
            ncm="7307.21.00",
        ),
        ncm_assessment=stored,
    )
    with pytest.raises(ApiError) as error:
        evaluate_proposed_ncm(catalog, changes)
    assert error.value.code == "NCM_ASSESSMENT_CHANGED"


def configure_nut(case):
    catalog = case["catalog"]
    cls = catalog.classes["PDM003"]
    attributes = {a.name: a.allowed_values[0] for a in cls.attributes if a.required}
    item = cls.item_names[0]
    material = case["materials"][0]
    material.pdm_class_id, material.attributes = cls.id, attributes
    material.manufacturer = material.manufacturer_reference = None
    material.ncm = "7318.15.00"
    material.pdm_description = format_description(cls, item, attributes)
    record = MaterialRecord(material.material_code, "ATIVO", material.pdm_description, unit="PC", ncm=material.ncm)
    analyzed = AnalyzedMaterial(
        record, cls.id, item, attributes, validate_pdm(catalog, cls.id, attributes, item_name=item).identity_key
    )
    generated = propose_ncm_corrections([analyzed], catalog)[0]
    members, changes, digest = approval_payload(
        generated, {material.material_code: str(material.id)}, str(case["dataset"].id)
    )
    proposal = case["proposal"]
    proposal.proposal_type = "NCM_CORRECTION"
    proposal.members, proposal.changeset, proposal.changeset_hash = members, json.loads(json.dumps(changes)), digest
    proposal.fiscal_review_status = "PENDING"
    case["session"].commit()
    return material


@pytest.mark.parametrize("first", ["TECHNICAL", "FISCAL"])
def test_ncm_only_applies_after_both_reviews_and_keeps_audited_assessment(approval_case, first):
    case = approval_case
    material = configure_nut(case)
    originals = [(s.quantity, s.total_value, copy.deepcopy(s.raw_record)) for s in case["snapshots"]]
    areas = [first, "FISCAL" if first == "TECHNICAL" else "TECHNICAL"]
    version = 1
    for index, area in enumerate(areas):
        case["app"].state.test_principal = case["principals"][0 if area == "TECHNICAL" else 1]
        payload = {
            "expected_version": version,
            "review_area": area,
            "decision": "APPROVE",
            "reason": "Fonte PDM e atributos conferidos.",
        }
        response = decide(case, payload=payload, key=str(uuid.uuid4()))
        assert response.status_code == 200, response.text
        version = response.json()["version"]
        assert response.json()["status"] == ("PENDING" if index == 0 else "APPLIED")
        case["session"].expire_all()
        assert material.ncm == ("7318.15.00" if index == 0 else "7318.16.00")
    assert [(s.quantity, s.total_value, s.raw_record) for s in case["snapshots"]] == originals
    events = list(case["session"].scalars(select(AuditLog).where(AuditLog.entity_id == str(case["proposal"].id))))
    assert len(events) == 2
    assert all(e.after_json["ncm_assessment"]["pdm_source_sha256"] == case["catalog"].source_sha256 for e in events)


def test_no_ncm_change_is_applied_when_fiscal_review_is_omitted(approval_case):
    case = approval_case
    material = configure_nut(case)
    case["proposal"].fiscal_review_status = "NOT_REQUIRED"
    persist(case)
    response = decide(case)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "FISCAL_REVIEW_REQUIRED"
    case["session"].expire_all()
    assert material.ncm == "7318.15.00"


def test_modified_attributes_cannot_reuse_persisted_assessment(approval_case):
    case = approval_case
    material = configure_nut(case)
    changed = copy.deepcopy(case["proposal"].changeset)
    changed["after"]["attributes"]["BITOLA"] = "M16"
    # O valor inicial é o primeiro do catálogo, distinto de M16.
    assert material.attributes["BITOLA"] != "M16"
    case["proposal"].changeset = changed
    persist(case)
    response = decide(case)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "NCM_ASSESSMENT_CHANGED"
