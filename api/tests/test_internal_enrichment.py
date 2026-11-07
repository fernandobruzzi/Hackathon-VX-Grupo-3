"""A fonte interna do kit percorre batch, evidência, revisão e aplicação auditada."""

import csv
import hashlib
import io
import uuid
from contextlib import contextmanager

import pytest
from approval_fixtures import decide
from sqlalchemy import select
from test_enrichment_flow import MemoryStore

from domain.contracts import MaterialRecord
from pipelines.full_run import RunContext
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_api.db.models import EnrichmentSource, SanitizationProposal

FILTER = "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9009"


@pytest.fixture
def internal_case(approval_case, connection):
    from pipelines.full_run import run_full

    case = approval_case
    db, m, dataset = case["session"], case["materials"][0], case["dataset"]
    m.original_description_long = FILTER
    m.attributes, m.pdm_class_id = {}, None
    db.commit()
    headers = [
        "CODIGO_MATERIAL",
        "STATUS",
        "DESCRICAO_LONGA",
        "DESCRICAO_CURTA",
        "GRUPO_MERCADORIA",
        "FABRICANTE",
        "REFERENCIA_FABRICANTE",
        "UNIDADE_MEDIDA",
        "NCM",
    ]
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, headers)
    writer.writeheader()
    writer.writerow(
        dict.fromkeys(headers, "")
        | {"CODIGO_MATERIAL": "donor", "STATUS": "ATIVO", "DESCRICAO_LONGA": FILTER + "; ALTURA: 100MM"}
    )
    content = buf.getvalue().encode()
    dataset.files = [
        {"name": "01_base_materiais.csv", "object_key": "raw/base.csv", "sha256": hashlib.sha256(content).hexdigest()}
    ]
    db.commit()
    store = MemoryStore()
    store.put_if_absent("raw/base.csv", content)

    class BoundEngine:
        @contextmanager
        def begin(self):
            with connection.begin_nested():
                yield connection

    context = RunContext(BoundEngine(), str(m.tenant_id), store=store)
    record = MaterialRecord(
        m.material_code,
        m.status,
        m.original_description_long,
        manufacturer=m.manufacturer,
        reference=m.manufacturer_reference,
        unit=m.unit,
        ncm=m.ncm,
        database_id=str(m.id),
    )
    analyzed = analyze_material(
        record, case["catalog"], get_classification_repository(case["catalog"]), get_extraction_repository()
    )
    result = run_full([record], case["catalog"], context)["internal_enrichment"]
    assert result["proposals"] == 1
    proposal = db.scalar(select(SanitizationProposal).where(SanitizationProposal.proposal_type == "ENRICHMENT"))
    case.update(proposal=proposal, internal_result=result, context=context, analyzed=analyzed)
    return case


def test_internal_enrichment_approves_with_evidence_and_repeats_without_duplicates(internal_case):
    from repositories.internal_enrichment_repository import run_internal_enrichment

    case = internal_case
    m = case["materials"][0]
    first = case["internal_result"]
    assert (
        run_internal_enrichment([case["analyzed"]], case["catalog"], case["context"])["proposal_ids"]
        == first["proposal_ids"]
    )
    from datetime import timedelta

    case["dataset"].imported_at += timedelta(days=1)
    case["session"].commit()
    restored = run_internal_enrichment([case["analyzed"]], case["catalog"], case["context"])
    assert restored["proposal_ids"] == first["proposal_ids"]
    from dataclasses import replace

    other = replace(
        case["analyzed"],
        record=replace(case["analyzed"].record, code="unrelated", version=2),
        identity_key=None,
        pdm_class_id=None,
        attributes={},
    )
    unrelated = run_internal_enrichment([case["analyzed"], other], case["catalog"], case["context"])
    assert unrelated["proposal_ids"] == first["proposal_ids"]
    detail = case["client"].get(f"/api/v1/enrichment/{case['proposal'].id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["evidence"][0]["source_url"].startswith("dataset://")
    stock = [(s.quantity, s.total_value) for s in case["snapshots"]]
    response = decide(
        case,
        payload={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "APPROVE",
            "reason": "Fonte interna conferida.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPLIED"
    case["session"].expire_all()
    assert m.attributes["ALTURA"] == "100MM" and not m.is_canonical
    assert m.original_description_long == FILTER and m.ncm == "8421.23.00" and m.unit == "PC"
    from dataclasses import replace

    record = replace(case["analyzed"].record, version=m.version, attributes=m.attributes)
    current = analyze_material(
        record, case["catalog"], get_classification_repository(case["catalog"]), get_extraction_repository()
    )
    repeated = run_internal_enrichment([current], case["catalog"], case["context"])
    assert repeated["proposals"] == 0
    assert stock == [(s.quantity, s.total_value) for s in case["snapshots"]]


def test_internal_source_cannot_masquerade_as_external_evidence(internal_case):
    case = internal_case
    source = case["session"].scalar(select(EnrichmentSource))
    source.source_url = "https://example.com/product"
    # O contrato mesmo reassinado continua sujeito à verificação do escopo das fontes.
    from approval_fixtures import persist

    from domain.enrichment_rules import evidence_hash

    changes = dict(case["proposal"].changeset)
    changes["evidence_hashes"] = {str(source.id): evidence_hash(source)}
    case["proposal"].changeset = changes
    persist(case)
    response = decide(
        case,
        payload={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "APPROVE",
            "reason": "Teste de escopo.",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INTERNAL_SOURCE_REQUIRED"


def test_internal_rerun_preserves_an_independent_external_review(internal_case):
    import copy

    from repositories.internal_enrichment_repository import run_internal_enrichment
    from vx_materials_api.schemas.proposals import proposal_hash

    case = internal_case
    current = case["proposal"]
    changes = copy.deepcopy(current.changeset)
    changes["enrichment_context"]["schema_version"] = "enrichment-v1"
    external = SanitizationProposal(
        id=uuid.uuid4(),
        tenant_id=current.tenant_id,
        proposal_type="ENRICHMENT",
        members=current.members,
        primary_material_id=current.primary_material_id,
        changeset=changes,
        changeset_hash=proposal_hash(current.members, changes, current.evidence_ids),
        evidence_ids=current.evidence_ids,
        technical_review_status="APPROVED",
        fiscal_review_status="PENDING",
        status="PENDING",
    )
    case["session"].add(external)
    case["session"].commit()
    run_internal_enrichment([case["analyzed"]], case["catalog"], case["context"])
    case["session"].expire_all()
    assert external.status == "PENDING" and external.technical_review_status == "APPROVED"
