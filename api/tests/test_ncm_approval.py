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


@pytest.fixture
def configured_snapshot(monkeypatch, tmp_path, request):
    from datetime import date

    from clients.ncm_snapshot_store import NcmSnapshotStore
    from clients.storage import LocalObjectStore
    from domain.ncm_snapshot import NcmSourceKind, load_ncm_snapshot

    raw = (Path(__file__).parents[2] / "back/tests/fixtures/ncm_simulated.json").read_bytes()
    scenario = getattr(request, "param", "unverified")
    source_kind = NcmSourceKind.SIMULATED
    if scenario in ("absent", "expired"):
        payload = json.loads(raw)
        row = next(r for r in payload["Nomenclaturas"] if r["Codigo"] == "7318.16.00")
        row.update({"Codigo": "9999.99.99"} if scenario == "absent" else {"Data_Fim": "05/11/2026"})
        raw = json.dumps(payload).encode()
        # Apenas simula o transporte neste teste; o conteúdo continua sendo fixture.
        source_kind = NcmSourceKind.OFFICIAL_DOWNLOAD
    snapshot = load_ncm_snapshot(raw, snapshot_date=date(2026, 11, 6), source_kind=source_kind)
    NcmSnapshotStore(LocalObjectStore(tmp_path)).register(snapshot, raw)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("NCM_SNAPSHOT_VERSION", snapshot.version)
    return snapshot


def test_api_assessment_records_configured_snapshot_and_rejects_legacy_proposals(catalog, configured_snapshot):
    snapshot = configured_snapshot
    changes = SimpleNamespace(
        after=SimpleNamespace(pdm_class_id="PDM003", item_name=None, attributes={}, ncm="7318.16.00"),
        ncm_assessment=None,
    )
    with pytest.raises(ApiError) as error:
        evaluate_proposed_ncm(catalog, changes)
    assert error.value.code == "NCM_ASSESSMENT_CHANGED"
    changes.ncm_assessment = asdict(check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", snapshot=snapshot))
    result = evaluate_proposed_ncm(catalog, changes)
    from test_contracts import validator

    validator({"$ref": "#/components/schemas/NcmAssessment"}).validate(json.loads(json.dumps(result)))
    assert result["ncm_version"] == snapshot.version
    assert result["ncm_source_sha256"] == snapshot.source_sha256
    assert result["ncm_snapshot_date"] == "2026-11-06"
    assert result["ncm_source_kind"] == "SIMULATED"
    assert result["requires_fiscal_review"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("ncm_version", "another"),
        ("ncm_source_sha256", "0" * 64),
        ("ncm_snapshot_date", "2026-11-07"),
        ("ncm_source_kind", "OFFICIAL_DOWNLOAD"),
    ],
)
def test_changed_snapshot_identity_cannot_reuse_assessment(catalog, configured_snapshot, field, value):
    assessment = asdict(check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00", snapshot=configured_snapshot))
    assessment[field] = value
    changes = SimpleNamespace(
        after=SimpleNamespace(pdm_class_id="PDM003", item_name=None, attributes={}, ncm="7318.16.00"),
        ncm_assessment=assessment,
    )
    with pytest.raises(ApiError) as error:
        evaluate_proposed_ncm(catalog, changes)
    assert error.value.code == "NCM_ASSESSMENT_CHANGED"


def test_configured_reference_failure_is_explicit(catalog, monkeypatch):
    monkeypatch.setenv("NCM_SNAPSHOT_VERSION", "not-loaded")
    with pytest.raises(ApiError) as error:
        evaluate_proposed_ncm(catalog, SimpleNamespace(ncm_assessment=None))
    assert error.value.code == "NCM_REFERENCE_UNAVAILABLE"


@pytest.mark.parametrize("configured_snapshot", ["unverified", "absent", "expired"], indirect=True)
def test_configured_snapshot_requires_fiscal_even_without_ncm_change(approval_case, configured_snapshot):
    case = approval_case
    material = configure_nut(case)
    material.ncm = "7318.16.00"
    case["proposal"].fiscal_review_status = "NOT_REQUIRED"
    persist(case)
    response = decide(case)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "FISCAL_REVIEW_REQUIRED"
    case["session"].expire_all()
    assert material.version == 1


def test_configured_reference_switch_invalidates_persisted_proposal(approval_case, configured_snapshot, monkeypatch):
    case = approval_case
    configure_nut(case)
    monkeypatch.delenv("NCM_SNAPSHOT_VERSION")
    response = decide(case)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "NCM_ASSESSMENT_CHANGED"


def test_v1_assessment_requires_regeneration_even_without_snapshot(catalog, monkeypatch):
    monkeypatch.delenv("NCM_SNAPSHOT_VERSION", raising=False)
    old = asdict(check_ncm_consistency(catalog, "PDM003", {}, "7318.16.00"))
    for field in ("ncm_version", "ncm_source_sha256", "ncm_snapshot_date", "ncm_source_kind"):
        old.pop(field)
    old["rules_version"] = "pdm-ncm-v1"
    changes = SimpleNamespace(
        after=SimpleNamespace(pdm_class_id="PDM003", item_name=None, attributes={}, ncm="7318.16.00"),
        ncm_assessment=old,
    )
    with pytest.raises(ApiError) as error:
        evaluate_proposed_ncm(catalog, changes)
    assert error.value.code == "NCM_ASSESSMENT_CHANGED"


def test_approved_configured_snapshot_metadata_reaches_transactional_audit(approval_case, configured_snapshot):
    case = approval_case
    material = configure_nut(case)
    for index, area in enumerate(("TECHNICAL", "FISCAL")):
        case["app"].state.test_principal = case["principals"][index]
        response = decide(
            case,
            payload={
                "expected_version": index + 1,
                "review_area": area,
                "decision": "APPROVE",
                "reason": "Fixture simulada conferida em teste.",
            },
            key=str(uuid.uuid4()),
        )
        assert response.status_code == 200, response.text
    case["session"].expire_all()
    assert material.ncm == "7318.16.00"
    events = list(case["session"].scalars(select(AuditLog).where(AuditLog.entity_id == str(case["proposal"].id))))
    assert len(events) == 2
    for event in events:
        assessment = event.after_json["ncm_assessment"]
        assert assessment["ncm_version"] == configured_snapshot.version
        assert assessment["ncm_source_sha256"] == configured_snapshot.source_sha256
        assert assessment["ncm_snapshot_date"] == "2026-11-06"
        assert assessment["ncm_source_kind"] == "SIMULATED"
