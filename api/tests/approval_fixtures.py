"""Propostas persistidas de teste; nao substituem o produtor batch da #19."""

import uuid
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot, MaterialMaster, SanitizationProposal, UserSso
from vx_materials_api.main import create_app
from vx_materials_api.schemas.proposals import proposal_hash
from vx_materials_api.security.approval_identity import Principal
from vx_materials_api.security.permissions import permissions_for

PDM_PATH = Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx"


def seed_case(session, tenant):
    catalog = load_pdm(PDM_PATH)
    users = []
    for role in ["ROLE_GOVERNANCA_PDM", "ROLE_AUDITOR_FISCAL", "ROLE_SOLICITANTE"]:
        user = UserSso(
            id=uuid.uuid4(),
            tenant_id=tenant,
            issuer="test",
            subject=str(uuid.uuid4()),
            display_name=role,
            roles_snapshot=[role],
        )
        session.add(user)
        users.append(user)
    dataset = Dataset(id=uuid.uuid4(), tenant_id=tenant, files={}, real_material_codes=[])
    session.add(dataset)
    attributes = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009"}
    validation = validate_pdm(catalog, "PDM100", attributes, item_name="FILTRO OLEO LUBRIFICANTE", unit="PC")
    materials = [
        MaterialMaster(
            id=uuid.uuid4(),
            tenant_id=tenant,
            source_system="ERP",
            material_code=code,
            status="ATIVO",
            original_description_long=f"FILTRO FLEETGUARD {code}",
            pdm_class_id="PDM100",
            pdm_version=catalog.version,
            attributes=attributes,
            manufacturer="FLEETGUARD",
            manufacturer_reference="LF9009",
            unit="PC",
            ncm="8421.23.00",
            version=1,
            pdm_description=validation.formatted_description,
        )
        for code in ["100", "200"]
    ]
    session.add_all(materials)
    session.flush()
    snapshots = [
        MaterialInventorySnapshot(
            id=uuid.uuid4(),
            tenant_id=tenant,
            dataset_id=dataset.id,
            material_id=material.id,
            center_code=center,
            quantity=Decimal(quantity),
            unit="PC",
            unit_price=Decimal("10"),
            total_value=Decimal(quantity) * 10,
            source_line=index,
            raw_record={"original": True},
        )
        for index, (material, center, quantity) in enumerate(
            [
                (materials[0], "1100", "2"),
                (materials[1], "1200", "3"),
                (materials[1], "1100", "1"),
            ],
            start=1,
        )
    ]
    session.add_all(snapshots)
    members = [
        {
            "material_id": str(m.id),
            "expected_version": 1,
            "pdm_class_id": "PDM100",
            "item_name": "FILTRO OLEO LUBRIFICANTE",
            "attributes": attributes,
        }
        for m in materials
    ]
    changes = {
        "schema_version": "proposal-v1",
        "dataset_id": str(dataset.id),
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "after": {
            "pdm_class_id": "PDM100",
            "item_name": "FILTRO OLEO LUBRIFICANTE",
            "attributes": attributes,
            "unit": "PC",
            "ncm": "8421.23.00",
        },
        "conversions": [],
        "conflicts": [],
        "sources": {},
    }
    proposal = SanitizationProposal(
        id=uuid.uuid4(),
        tenant_id=tenant,
        proposal_type="MERGE",
        members=members,
        primary_material_id=materials[0].id,
        changeset=changes,
        changeset_hash=proposal_hash(members, changes),
        technical_review_status="PENDING",
        fiscal_review_status="NOT_REQUIRED",
        version=1,
    )
    session.add(proposal)
    session.commit()
    principals = [
        Principal(
            u.id,
            tenant,
            tuple(u.roles_snapshot),
            permissions_for(tuple(u.roles_snapshot)),
            display_name=u.display_name,
            center_codes=frozenset({"1100", "1200"}),
            csrf_token="csrf",
        )
        for u in users
    ]
    return catalog, dataset, materials, snapshots, proposal, principals


@pytest.fixture
def approval_case(connection, tenant, monkeypatch):
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    catalog, dataset, materials, snapshots, proposal, principals = seed_case(session, tenant)
    app = create_app(
        session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
        identity_provider=lambda db: app.state.test_principal,
    )
    app.state.test_principal = principals[0]
    app.state.pdm_catalog = catalog
    with TestClient(app, base_url="http://localhost:8000") as client:
        case = {
            "session": session,
            "proposal": proposal,
            "materials": materials,
            "snapshots": snapshots,
            "principals": principals,
            "app": app,
            "client": client,
            "dataset": dataset,
            "catalog": catalog,
            "headers": {
                "Origin": "http://localhost:8000",
                "X-CSRF-Token": "csrf",
                "Idempotency-Key": str(uuid.uuid4()),
            },
            "payload": {
                "expected_version": 1,
                "review_area": "TECHNICAL",
                "decision": "APPROVE",
                "primary_material_code": "100",
                "reason": "Identidade e evidencias conferidas.",
            },
        }
        yield case
    session.close()


def decide(case, *, payload=None, key=None):
    headers = case["headers"] | ({"Idempotency-Key": key} if key else {})
    return case["client"].post(
        f"/api/v1/sanitization/{case['proposal'].id}/decide", json=payload or case["payload"], headers=headers
    )


def persist(case):
    proposal = case["proposal"]
    proposal.changeset_hash = proposal_hash(proposal.members, proposal.changeset, proposal.evidence_ids)
    case["session"].commit()


def principal_with(case, **values):
    return replace(case["principals"][0], **values)
