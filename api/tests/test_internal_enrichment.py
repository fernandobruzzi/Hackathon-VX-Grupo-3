"""A fonte interna do kit percorre batch, evidência, revisão e aplicação auditada."""

import csv
import hashlib
import io
import json
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
BUCHA = "BUCHA; FABRICANTE: CATERPILLAR; REFERENCIA FABRICANTE: 5072254"


@pytest.fixture
def internal_case(approval_case, connection, monkeypatch, request):
    from pipelines.full_run import run_full

    case = approval_case
    supplemental = getattr(request, "param", "csv") in {"supplemental", "supplemental_group"}
    grouped = getattr(request, "param", "csv") in {"group", "supplemental_group"}
    monkeypatch.delenv("ENRICHMENT_INTERNAL_SOURCES_KEY", raising=False)
    monkeypatch.setenv("ENRICHMENT_LLM_MAX_CALLS", "0")
    db, m, dataset = case["session"], case["materials"][0], case["dataset"]
    m.original_description_long = FILTER
    m.attributes, m.pdm_class_id = {}, None
    if grouped:
        m.original_description_long = BUCHA
        m.original_merchandise_group = "SOB01"
        m.manufacturer, m.manufacturer_reference, m.ncm = "CATERPILLAR", "5072254", "8431.49.29"
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
        | {
            "CODIGO_MATERIAL": "donor",
            "STATUS": "ATIVO",
            "DESCRICAO_LONGA": (
                BUCHA + ("" if supplemental else "; APLICACAO: ESCAVADEIRA HIDRAULICA; MODELO EQUIPAMENTO: 6015B")
                if grouped
                else FILTER + ("" if supplemental else "; ALTURA: 100MM")
            ),
            "GRUPO_MERCADORIA": m.original_merchandise_group or "",
        }
    )
    content = buf.getvalue().encode()
    dataset.files = [
        {"name": "01_base_materiais.csv", "object_key": "raw/base.csv", "sha256": hashlib.sha256(content).hexdigest()}
    ]
    db.commit()
    store = MemoryStore()
    store.put_if_absent("raw/base.csv", content)
    monkeypatch.setattr("clients.storage.get_object_store", lambda: store)
    if supplemental:
        from enrichment.internal_documents import bundle_object_key

        document = {
            "schema_version": "internal-documents-v1",
            "dataset_id": str(dataset.id),
            "documents": [
                {
                    "id": "ficha-bucha" if grouped else "ficha-filtro",
                    "title": (
                        "Ficha técnica interna — bucha 5072254" if grouped else "Ficha técnica interna — filtro LF9009"
                    ),
                    "text": (
                        BUCHA + "; APLICACAO: ESCAVADEIRA HIDRAULICA; MODELO EQUIPAMENTO: 6015B"
                        if grouped
                        else FILTER + "; ALTURA: 100MM"
                    ),
                    "kind": "INTERNAL_DOCUMENT",
                }
                | ({"merchandise_group": "SOB01"} if grouped else {})
            ],
        }
        document_bytes = json.dumps(document, ensure_ascii=False).encode()
        key = bundle_object_key(document_bytes, str(dataset.id))
        store.put_if_absent(key, document_bytes)
        monkeypatch.setenv("ENRICHMENT_INTERNAL_SOURCES_KEY", key)
        case.update(supplemental_bundle=document, supplemental_key=key, supplemental_bytes=document_bytes)

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
        group=m.original_merchandise_group or "",
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
    case.update(proposal=proposal, internal_result=result, context=context, analyzed=analyzed, store=store)
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


@pytest.mark.parametrize("internal_case", ["supplemental"], indirect=True)
def test_documentary_source_flows_through_evidence_and_audited_approval(internal_case):
    from sqlalchemy import func

    from vx_materials_api.db.models import AuditLog

    case = internal_case
    material, proposal = case["materials"][0], case["proposal"]
    supplemental = proposal.changeset["enrichment_context"]["supplemental_source"]
    assert supplemental == {
        "object_key": case["supplemental_key"],
        "sha256": hashlib.sha256(case["supplemental_bytes"]).hexdigest(),
    }
    assert "ALTURA" not in material.attributes
    detail = case["client"].get(f"/api/v1/enrichment/{proposal.id}")
    assert detail.status_code == 200, detail.text
    evidence = detail.json()["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["source_url"] == f"dataset://{case['dataset'].id}/internal-documents#ficha-filtro"
    assert evidence[0]["source_title"] == "Ficha técnica interna — filtro LF9009"
    assert evidence[0]["source_excerpt"] == FILTER + "; ALTURA: 100MM"
    assert evidence[0]["source_sha256"] == supplemental["sha256"]
    stock = [(s.quantity, s.total_value) for s in case["snapshots"]]
    response = decide(
        case,
        payload={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "APPROVE",
            "reason": "Documento interno e identidade conferidos.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPLIED"
    case["session"].expire_all()
    assert material.attributes["ALTURA"] == "100MM"
    assert not material.is_canonical and material.identity_key is None
    assert material.original_description_long == FILTER and material.ncm == "8421.23.00" and material.unit == "PC"
    assert stock == [(s.quantity, s.total_value) for s in case["snapshots"]]
    assert case["session"].scalar(select(func.count()).select_from(AuditLog)) == 1
    source = case["session"].scalar(select(EnrichmentSource))
    assert source.status == "APPROVED" and source.s3_object_key == case["supplemental_key"]


@pytest.mark.parametrize("internal_case", ["supplemental"], indirect=True)
@pytest.mark.parametrize("alteration", ["bytes", "other_dataset"])
def test_document_changed_or_rebound_to_another_dataset_blocks_approval(internal_case, alteration):
    import copy

    from approval_fixtures import persist

    from domain.enrichment_rules import evidence_hash
    from enrichment.internal_documents import bundle_object_key

    case = internal_case
    document = copy.deepcopy(case["supplemental_bundle"])
    if alteration == "bytes":
        document["documents"][0]["text"] = FILTER + "; ALTURA: 200MM"
        # Simula corrupção do armazenamento abaixo da camada de escrita imutável.
        case["store"].objects[case["supplemental_key"]] = json.dumps(document, ensure_ascii=False).encode()
    else:
        document["dataset_id"] = str(uuid.uuid4())
        content = json.dumps(document, ensure_ascii=False).encode()
        key = bundle_object_key(content, document["dataset_id"])
        digest = hashlib.sha256(content).hexdigest()
        case["store"].put_if_absent(key, content)
        source = case["session"].scalar(select(EnrichmentSource))
        source.s3_object_key, source.source_sha256 = key, digest
        changes = copy.deepcopy(case["proposal"].changeset)
        changes["enrichment_context"]["supplemental_source"] = {"object_key": key, "sha256": digest}
        changes["evidence_hashes"] = {str(source.id): evidence_hash(source)}
        case["proposal"].changeset = changes
        persist(case)
    response = decide(
        case,
        payload={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "APPROVE",
            "reason": "Verificação de vínculo documental.",
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ENRICHMENT_BASIS_CHANGED"
    case["session"].expire_all()
    assert "ALTURA" not in case["materials"][0].attributes
    assert case["proposal"].status == "PENDING"


@pytest.mark.parametrize("internal_case", ["supplemental"], indirect=True)
def test_changed_document_requires_new_job_and_preserves_the_previous_pending_review(internal_case, monkeypatch):
    import copy

    from enrichment.internal_documents import bundle_object_key
    from repositories.internal_enrichment_repository import run_internal_enrichment

    case = internal_case
    previous = case["internal_result"]
    repeated = run_internal_enrichment([case["analyzed"]], case["catalog"], case["context"])
    assert repeated["proposal_ids"] == previous["proposal_ids"] and repeated["inserted"] == 0
    document = copy.deepcopy(case["supplemental_bundle"])
    document["documents"][0]["text"] = FILTER + "; ALTURA: 200MM"
    content = json.dumps(document, ensure_ascii=False).encode()
    key = bundle_object_key(content, str(case["dataset"].id))
    case["store"].put_if_absent(key, content)
    monkeypatch.setenv("ENRICHMENT_INTERNAL_SOURCES_KEY", key)
    with pytest.raises(ValueError, match="Crie um novo job"):
        run_internal_enrichment([case["analyzed"]], case["catalog"], case["context"])
    context = RunContext(case["context"].engine, case["context"].tenant_id, store=case["store"])
    changed = run_internal_enrichment([case["analyzed"]], case["catalog"], context)
    assert changed["proposals"] == changed["inserted"] == 1
    assert changed["proposal_ids"] != previous["proposal_ids"]
    assert context.checkpoint["internal_sources_signature"] != case["context"].checkpoint["internal_sources_signature"]
    case["session"].expire_all()
    assert case["proposal"].status == "PENDING"
    new_proposal = case["session"].get(SanitizationProposal, uuid.UUID(changed["proposal_ids"][0]))
    assert new_proposal.status == "PENDING" and new_proposal.changeset["after"]["attributes"]["ALTURA"] == "200MM"
    assert "ALTURA" not in case["materials"][0].attributes


@pytest.mark.parametrize("internal_case", ["supplemental"], indirect=True)
def test_pending_documentary_proposal_does_not_become_a_donor_when_document_is_disabled(internal_case, monkeypatch):
    from repositories.internal_enrichment_repository import run_internal_enrichment

    case = internal_case
    material = case["materials"][1]
    material.original_description_long, material.attributes, material.pdm_class_id = FILTER, {}, None
    case["session"].commit()
    record = MaterialRecord(
        material.material_code,
        material.status,
        material.original_description_long,
        manufacturer=material.manufacturer,
        reference=material.manufacturer_reference,
        unit=material.unit,
        ncm=material.ncm,
        database_id=str(material.id),
    )
    analyzed = analyze_material(
        record, case["catalog"], get_classification_repository(case["catalog"]), get_extraction_repository()
    )
    monkeypatch.delenv("ENRICHMENT_INTERNAL_SOURCES_KEY")
    context = RunContext(case["context"].engine, case["context"].tenant_id, store=case["store"])
    result = run_internal_enrichment([analyzed], case["catalog"], context)
    assert result["proposals"] == result["inserted"] == 0
    assert result["summary"]["suggested_attributes"] == 0
    assert "ALTURA" not in material.attributes and "ALTURA" not in case["materials"][0].attributes
    case["session"].expire_all()
    assert case["proposal"].status == "PENDING" and case["proposal"].technical_review_status == "PENDING"


@pytest.mark.parametrize("internal_case", ["supplemental"], indirect=True)
def test_assisted_review_metadata_does_not_change_the_frozen_documentary_proposal(internal_case, monkeypatch):
    from sqlalchemy import func

    import repositories.internal_enrichment_repository as producer
    from domain.enrichment_rules import evidence_hash

    case = internal_case
    source = case["session"].scalar(select(EnrichmentSource))
    original_source_hash = evidence_hash(source)
    original_changeset_hash = case["proposal"].changeset_hash
    original_local_key = case["proposal"].changeset["enrichment_context"]["report_key"]
    report_keys = {case["internal_result"]["report_key"]}
    real_report = producer.internal_report
    variant = 0

    def with_varying_assisted_metadata(*args, **kwargs):
        report = real_report(*args, **kwargs)
        for item in report["results"]:
            # A saída assistida permanece metadado de revisão, fora da evidência documental aplicável.
            candidate = {
                "attribute": "DIAMETRO EXTERNO",
                "value": f"{variant}MM",
                "source_field": "description",
                "excerpt": "FILTRO OLEO LUBRIFICANTE",
            }
            item["assisted_candidates"] = [candidate]
            item["assisted_extraction"] = {"status": "REVIEW_REQUIRED", "candidates": [candidate]}
        return report

    monkeypatch.setattr(producer, "internal_report", with_varying_assisted_metadata)
    for variant in (50, 60):
        result = producer.run_internal_enrichment([case["analyzed"]], case["catalog"], case["context"])
        report_keys.add(result["report_key"])
        saved_report = json.loads(case["store"].get(result["report_key"]))
        assert saved_report["results"][0]["assisted_candidates"][0]["value"] == f"{variant}MM"
        assert result["proposal_ids"] == case["internal_result"]["proposal_ids"] and result["inserted"] == 0
        case["session"].expire_all()
        assert case["proposal"].changeset_hash == original_changeset_hash
        assert case["proposal"].changeset["enrichment_context"]["report_key"] == original_local_key
        assert evidence_hash(source) == original_source_hash
    assert len(report_keys) == 3
    assert case["session"].scalar(select(func.count()).select_from(EnrichmentSource)) == 1


def test_unrelated_document_keeps_original_source_date_hash_and_proposal(internal_case, monkeypatch):
    from datetime import timedelta

    from sqlalchemy import func

    from domain.enrichment_rules import evidence_hash
    from enrichment.internal_documents import bundle_object_key
    from repositories.internal_enrichment_repository import run_internal_enrichment

    case = internal_case
    source = case["session"].scalar(select(EnrichmentSource))
    original_source_hash, original_date = evidence_hash(source), source.retrieved_at
    original_changeset_hash = case["proposal"].changeset_hash
    case["dataset"].imported_at += timedelta(days=1)
    case["session"].commit()
    document = {
        "schema_version": "internal-documents-v1",
        "dataset_id": str(case["dataset"].id),
        "documents": [
            {
                "id": "filtro-outro-fabricante",
                "title": "Ficha de outro produto",
                "text": FILTER.replace("FLEETGUARD", "DONALDSON").replace("LF9009", "P551000") + "; ALTURA: 200MM",
                "kind": "INTERNAL_DOCUMENT",
            }
        ],
    }
    content = json.dumps(document, ensure_ascii=False).encode()
    key = bundle_object_key(content, str(case["dataset"].id))
    case["store"].put_if_absent(key, content)
    monkeypatch.setenv("ENRICHMENT_INTERNAL_SOURCES_KEY", key)
    context = RunContext(case["context"].engine, case["context"].tenant_id, store=case["store"])
    result = run_internal_enrichment([case["analyzed"]], case["catalog"], context)
    assert context.checkpoint["internal_sources_signature"] != case["context"].checkpoint["internal_sources_signature"]
    assert result["proposal_ids"] == case["internal_result"]["proposal_ids"] and result["inserted"] == 0
    assert json.loads(case["store"].get(result["report_key"]))["supplemental_source"]["object_key"] == key
    case["session"].expire_all()
    assert source.retrieved_at == original_date and evidence_hash(source) == original_source_hash
    assert case["proposal"].changeset_hash == original_changeset_hash
    assert case["proposal"].changeset["enrichment_context"].get("supplemental_source") is None
    assert case["session"].scalar(select(func.count()).select_from(EnrichmentSource)) == 1
    assert case["proposal"].status == "PENDING" and "ALTURA" not in case["materials"][0].attributes


@pytest.mark.parametrize("internal_case", ["group", "supplemental_group"], indirect=True)
def test_original_group_resolves_bucha_for_internal_enrichment_and_approval(internal_case):
    case = internal_case
    proposal = case["proposal"]
    assert case["analyzed"].pdm_class_id == "PDM110" and case["analyzed"].item_name == "BUCHA"
    assert proposal.changeset["after"]["item_name"] == "BUCHA"
    assert proposal.changeset["after"]["attributes"]["APLICACAO"] == "ESCAVADEIRA HIDRAULICA"
    response = decide(
        case,
        payload={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "APPROVE",
            "reason": "Identidade e grupo original da bucha conferidos.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["technical_review_status"] == "APPROVED"
    assert response.json()["status"] == "APPLIED"
    case["session"].expire_all()
    material = case["materials"][0]
    assert material.attributes["APLICACAO"] == "ESCAVADEIRA HIDRAULICA"
    assert material.original_description_long == BUCHA and material.original_merchandise_group == "SOB01"


@pytest.mark.parametrize("internal_case", ["group", "supplemental_group"], indirect=True)
@pytest.mark.parametrize("changed_group", [None, "TUB01"])
def test_missing_or_changed_original_group_refuses_approval_despite_a_revised_group(internal_case, changed_group):
    from domain.enrichment_rules import original_hash

    case = internal_case
    material = case["materials"][0]
    before_hash = original_hash(material)
    material.original_merchandise_group = changed_group
    material.merchandise_group = "SOB01"
    case["session"].commit()
    assert original_hash(material) == before_hash
    response = decide(
        case,
        payload={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "APPROVE",
            "reason": "Verificação de alteração do grupo original.",
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ENRICHMENT_BASIS_CHANGED"
    case["session"].expire_all()
    assert "APLICACAO" not in material.attributes and case["proposal"].status == "PENDING"
