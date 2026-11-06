"""Evidências simuladas exercitam publicação, leitura e aprovação transacional sem rede."""

import copy
import csv
import hashlib
import json
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from approval_fixtures import decide, persist
from sqlalchemy import func, select

from clients.storage import ObjectConflictError, StoredObject
from domain.enrichment_rules import extraction_signature, original_hash
from domain.pdm_loader import load_pdm
from enrichment.catalog import REAL_PRODUCTS
from enrichment.trusted_sources import SourceDocument
from pipelines.enrich_real_products import run_enrichment
from repositories.enrichment_repository import publish_enrichment
from vx_materials_api.db.models import AuditLog, EnrichmentSource, InventoryConsolidation, SanitizationProposal
from vx_materials_api.errors import ApiError
from vx_materials_api.services.enrichment_validation import validate_enrichment_context

KIT = Path(__file__).parents[2] / "data/desafio01"


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def put_if_absent(self, key, content):
        if key in self.objects and self.objects[key] != content:
            raise ObjectConflictError(key)
        self.objects[key] = content
        return StoredObject(key)

    def get(self, key):
        return self.objects[key]


@pytest.fixture
def enrichment_case(approval_case, connection, monkeypatch):
    case = approval_case
    db, material, dataset = case["session"], case["materials"][0], case["dataset"]
    content = (KIT / "01_base_materiais.csv").read_bytes()
    with (KIT / "01_base_materiais.csv").open(encoding="utf-8-sig", newline="") as source:
        row = next(row for row in csv.DictReader(source) if row["CODIGO_MATERIAL"] == "28490077")
    material.material_code = row["CODIGO_MATERIAL"]
    material.original_description_long = row["DESCRICAO_LONGA"]
    material.manufacturer, material.manufacturer_reference = row["FABRICANTE"], row["REFERENCIA_FABRICANTE"]
    material.unit, material.ncm = row["UNIDADE_MEDIDA"], row["NCM"]
    material.pdm_class_id, material.pdm_description, material.attributes = None, None, {}
    files = [
        {"name": "01_base_materiais.csv", "object_key": "raw/base.csv", "sha256": hashlib.sha256(content).hexdigest()},
        {"name": "03_padrao_cadastro_PDM.xlsx", "sha256": case["catalog"].source_sha256},
    ]
    dataset.files, dataset.real_material_codes = files, sorted(REAL_PRODUCTS)
    db.commit()
    store = MemoryStore()
    store.put_if_absent("raw/base.csv", content)
    store.put_if_absent(
        "raw/manifest.json",
        json.dumps(
            {
                "dataset_id": str(dataset.id),
                "tenant_id": str(dataset.tenant_id),
                "files": files,
                "real_material_codes": sorted(REAL_PRODUCTS),
                "pdm_version": case["catalog"].version,
            }
        ).encode(),
    )

    class SimulatedCatalog:
        def fetch(self, spec):
            return SourceDocument(
                spec.id,
                spec.url,
                b"<h1>NSK 6205DDUC3</h1><h2>Specification</h2><p>Bore diameter 25 mm</p>"
                b"<p>Outside diameter 52 mm</p><p>Width 15 mm</p>",
                "text/html",
                "2026-11-06T12:00:00+00:00",
                simulated=True,
            )

    # Mantém o banco real e a transação descartável da fixture; não cria outra conexão invisível ao savepoint.
    class BoundEngine:
        @contextmanager
        def begin(self):
            with connection.begin_nested():
                yield connection

        def dispose(self):
            pass

    monkeypatch.setattr("repositories.enrichment_repository.create_engine", lambda _: BoundEngine())
    monkeypatch.setenv("APP_ENV", "local")
    report = run_enrichment(
        store, "raw/manifest.json", case["catalog"], client=SimulatedCatalog(), material_codes=[material.material_code]
    )
    result = publish_enrichment(store, report["report_key"], case["catalog"], "test-bound-connection")
    proposal = db.get(SanitizationProposal, uuid.UUID(result["proposals"][0]["proposal_id"]))
    case["proposal"] = proposal
    case["payload"] = {key: value for key, value in case["payload"].items() if key != "primary_material_code"}
    case.update(store=store, report=report)
    return case


def test_frozen_evidence_flows_to_partial_approval_without_canonicalizing(enrichment_case):
    case = enrichment_case
    db, material, proposal = case["session"], case["materials"][0], case["proposal"]
    originals = [(s.quantity, s.total_value, copy.deepcopy(s.raw_record)) for s in case["snapshots"]]
    raw_description = material.original_description_long
    assert material.attributes == {} and material.version == 1
    before_sources = db.scalar(select(func.count()).select_from(EnrichmentSource))
    repeated = publish_enrichment(case["store"], case["report"]["report_key"], case["catalog"], "bound")
    assert repeated["proposals"][0]["proposal_id"] == str(proposal.id)
    detail = case["client"].get(f"/api/v1/enrichment/{proposal.id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["pending_attributes"]
    assert all(
        e["source_url"].startswith("https://") and e["source_excerpt"] and e["source_sha256"] for e in body["evidence"]
    )
    assert all(e["confidence"] == "BAIXA" and e["simulated"] for e in body["evidence"])
    assert any(e["attribute"] == "REFERENCIA" and not e["included_in_proposal"] for e in body["evidence"])
    listed = case["client"].get("/api/v1/enrichment").json()
    assert listed["items"][0]["proposal_id"] == str(proposal.id)
    queue_detail = case["client"].get(f"/api/v1/sanitization/{proposal.id}")
    assert queue_detail.status_code == 200, queue_detail.text
    assert "APPROVE" in queue_detail.json()["allowed_actions"]
    response = decide(case)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPLIED"
    assert decide(case).json() == response.json()
    db.expire_all()
    assert material.attributes["DIAMETRO INTERNO"] == "25MM"
    assert material.attributes["DIAMETRO EXTERNO"] == "52MM"
    assert material.attributes["LARGURA"] == "15MM"
    assert not material.is_canonical and material.identity_key is None
    assert material.original_description_long == raw_description
    assert material.ncm == proposal.changeset["after"]["ncm"]
    assert [(s.quantity, s.total_value, s.raw_record) for s in case["snapshots"]] == originals
    assert db.scalar(select(func.count()).select_from(InventoryConsolidation)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
    for source in db.scalars(select(EnrichmentSource)):
        assert source.status == (
            "APPROVED" if source.attribute_name in {"DIAMETRO INTERNO", "DIAMETRO EXTERNO", "LARGURA"} else "PENDING"
        )
    after = publish_enrichment(case["store"], case["report"]["report_key"], case["catalog"], "bound")
    assert after == repeated
    assert db.scalar(select(func.count()).select_from(EnrichmentSource)) == before_sources


@pytest.mark.parametrize("field,value", [("source_excerpt", "alterado"), ("confidence_basis", ["MANUFACTURER_DOMAIN"])])
def test_changed_evidence_blocks_approval(enrichment_case, field, value):
    case = enrichment_case
    source = case["session"].scalar(select(EnrichmentSource))
    setattr(source, field, value)
    case["session"].commit()
    response = decide(case)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "EVIDENCE_CHANGED"


def test_simulated_evidence_cannot_be_approved_in_production(enrichment_case, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    response = decide(enrichment_case)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "SIMULATED_EVIDENCE_FORBIDDEN"


@pytest.mark.parametrize("ncm", [None, "", "73181500"])
def test_partial_enrichment_never_certifies_the_existing_ncm(enrichment_case, ncm):
    case = enrichment_case
    material, proposal = case["materials"][0], case["proposal"]
    material.ncm, material.ncm_review_status = ncm, "PENDING"
    changes = copy.deepcopy(proposal.changeset)
    changes["after"]["ncm"] = ncm
    proposal.changeset = changes
    proposal.fiscal_review_status = "PENDING"
    persist(case)
    detail = case["client"].get(f"/api/v1/sanitization/{proposal.id}")
    assert detail.status_code == 200, detail.text
    assert "APPROVE" in detail.json()["allowed_actions"]
    first = decide(case)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    case["app"].state.test_principal = case["principals"][1]
    fiscal = {"expected_version": 2, "review_area": "FISCAL", "decision": "APPROVE", "reason": "Atributos conferidos."}
    second = decide(case, payload=fiscal, key=str(uuid.uuid4()))
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPLIED"
    case["session"].expire_all()
    assert material.ncm == ncm and material.ncm_review_status == "PENDING"
    events = list(case["session"].scalars(select(AuditLog)))
    assert len(events) == 2
    assert all(event.after_json["ncm_assessment"]["technical_consistency"] != "CONSISTENT" for event in events)


def test_enrichment_read_scope_and_stale_version(enrichment_case):
    case = enrichment_case
    path = f"/api/v1/enrichment/{case['proposal'].id}"
    case["app"].state.test_principal = case["principals"][2]
    assert case["client"].get(path).status_code == 403
    case["app"].state.test_principal = replace(case["principals"][0], center_codes=frozenset({"9999"}))
    assert case["client"].get(path).status_code == 404
    assert case["client"].get("/api/v1/enrichment").json()["items"] == []
    case["app"].state.test_principal = replace(case["principals"][0], tenant_id=uuid.uuid4())
    assert case["client"].get(path).status_code == 404
    case["app"].state.test_principal = case["principals"][0]
    case["materials"][0].version += 1
    case["session"].commit()
    assert decide(case).status_code == 409


def test_context_rejects_changed_original_rules_and_fiscal_scope():
    catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
    primary = SimpleNamespace(
        id=uuid.uuid4(),
        material_code="28490077",
        original_description_long="ROLAMENTO NSK 6205DDUC3",
        manufacturer="NSK",
        manufacturer_reference="6205DDUC3",
        pdm_class_id=None,
        attributes={},
        unit="PC",
        ncm="84821010",
    )
    context = SimpleNamespace(
        model_dump=lambda: {
            "schema_version": "enrichment-v1",
            "original_hash": original_hash(primary),
            "extraction_signature": extraction_signature(catalog),
            "divergent_attributes": [],
            "blocked_attributes": [],
        }
    )
    changes = SimpleNamespace(
        enrichment_context=context,
        after=SimpleNamespace(
            pdm_class_id="PDM020",
            item_name="ROLAMENTO RIGIDO ESFERAS",
            attributes={"FABRICANTE": "NSK"},
            unit="PC",
            ncm="99999999",
        ),
    )
    dataset = SimpleNamespace(real_material_codes=sorted(REAL_PRODUCTS))
    with pytest.raises(ApiError) as error:
        validate_enrichment_context(changes, primary, dataset, catalog)
    assert error.value.code == "ENRICHMENT_SCOPE"
    changes.after.ncm = primary.ncm
    original = context.model_dump()
    context.model_dump = lambda: original | {"original_hash": "0" * 64}
    with pytest.raises(ApiError) as error:
        validate_enrichment_context(changes, primary, dataset, catalog)
    assert error.value.code == "ENRICHMENT_BASIS_CHANGED"
