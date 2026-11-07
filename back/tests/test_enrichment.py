"""Documentos simulados verificam isolamento, evidências, divergências e repetição sem rede."""

import csv
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from clients.storage import LocalObjectStore, ObjectConflictError, StoredObject
from domain.contracts import EnrichmentClaim
from domain.pdm_loader import load_pdm
from enrichment.catalog import LF9009, REAL_PRODUCTS
from enrichment.documents import document_pages
from enrichment.evidence import record_evidence
from enrichment.trusted_sources import SourceDocument, SourceError
from pipelines.enrich_real_products import run_enrichment
from repositories.enrichment import REPOSITORIES, get_enrichment_repository

KIT = Path(__file__).parents[2] / "data/desafio01"
STAMP = "2026-11-05T12:00:00+00:00"


class MemoryStore:
    name = "memory"

    def __init__(self):
        self.objects = {}

    def put_if_absent(self, key, content):
        if key in self.objects and self.objects[key] != content:
            raise ObjectConflictError(key)
        self.objects[key] = content
        return StoredObject(key)

    def get(self, key):
        return self.objects[key]


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture
def stored_input(catalog):
    store = MemoryStore()
    # Embaralhar linhas e incluir um sintético no fim não altera os códigos do manifesto.
    rows = list(csv.DictReader((KIT / "01_base_materiais.csv").open(encoding="utf-8-sig", newline="")))
    selected = [row for row in rows if row["CODIGO_MATERIAL"] in REAL_PRODUCTS][::-1] + [rows[0]]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(selected)
    content = output.getvalue().encode()
    manifest = {
        "dataset_id": "88888888-8888-4888-8888-888888888888",
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "pdm_version": catalog.version,
        "real_material_codes": sorted(REAL_PRODUCTS),
        "files": [
            {
                "name": "01_base_materiais.csv",
                "object_key": "raw/base.csv",
                "sha256": hashlib.sha256(content).hexdigest(),
            },
            {"name": "03_padrao_cadastro_PDM.xlsx", "sha256": catalog.source_sha256},
        ],
    }
    store.put_if_absent("raw/base.csv", content)
    store.put_if_absent("raw/manifest.json", json.dumps(manifest).encode())
    return store, manifest


def simulated_document(spec, reference="LF9009", height="300"):
    content = (
        f"<html><h1>{reference} Fleetguard</h1><h2>Specification</h2><p>Height {height} mm</p>"
        "<p>Largest Outside Diameter 4.68 inch / 118.87 mm</p></html>"
    ).encode()
    return SourceDocument(spec.id, spec.url, content, "text/html", STAMP, simulated=True)


class SimulatedClient:
    def __init__(self):
        self.calls = []

    def fetch(self, spec):
        self.calls.append(spec.id)
        if spec.id == LF9009.id:
            return simulated_document(spec)
        raise SourceError("Fonte simulada indisponível")


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_repository_contract_keeps_literal_evidence_and_allowed_attributes(catalog, name):
    document = simulated_document(LF9009)
    pages = document_pages(document)
    claims = get_enrichment_repository(name).extract(catalog.classes["PDM100"], "FLEETGUARD", "LF9009", pages)
    assert any(claim.attribute == "ALTURA" and claim.value == "300MM" for claim in claims)
    for claim in claims:
        assert claim.attribute in {attr.name for attr in catalog.classes["PDM100"].attributes}
        assert claim.excerpt in pages[claim.page - 1]


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_repository_contract_rejects_other_variants_and_unrelated_products(catalog, name):
    repository = get_enrichment_repository(name)
    for reference in ("LF9009X", "LF9009/UPGRADE", "LF3970"):
        pages = document_pages(simulated_document(LF9009, reference))
        assert repository.extract(catalog.classes["PDM100"], "FLEETGUARD", "LF9009", pages) == ()


def test_repository_selection_is_configurable(monkeypatch):
    class Alternative(REPOSITORIES["catalog_labels_v1"]):
        name = "alternative"

    monkeypatch.setitem(REPOSITORIES, Alternative.name, Alternative)
    monkeypatch.setenv("ENRICHMENT_REPOSITORY", Alternative.name)
    assert get_enrichment_repository().name == Alternative.name
    with pytest.raises(ValueError, match="desconhecido"):
        get_enrichment_repository("missing")


def test_only_manifest_codes_are_consulted_even_after_reordering(stored_input, catalog):
    store, manifest = stored_input
    client = SimulatedClient()
    report = run_enrichment(store, "raw/manifest.json", catalog, client=client)
    assert {item["material_code"] for item in report["results"]} == set(manifest["real_material_codes"])
    assert len(report["results"]) == 15
    assert client.calls.count(LF9009.id) == 1  # Dois códigos reais usam a mesma fonte.
    assert report["simulated"] is True
    assert next(item for item in report["results"] if item["material_code"] == "16303905")["status"] == "PENDING"


def test_synthetic_code_is_rejected_before_any_fetch(stored_input, catalog):
    store, _ = stored_input
    client = SimulatedClient()
    with pytest.raises(ValueError, match="somente"):
        run_enrichment(store, "raw/manifest.json", catalog, client=client, material_codes=["12345678"])
    assert client.calls == []


@pytest.mark.parametrize("change", ["code", "duplicate", "pdm", "source"])
def test_tampered_manifest_and_original_are_rejected(stored_input, catalog, change):
    store, manifest = stored_input
    if change == "code":
        manifest["real_material_codes"][0] = "synthetic"
    elif change == "duplicate":
        manifest["real_material_codes"][0] = manifest["real_material_codes"][1]
    elif change == "pdm":
        manifest["files"][1]["sha256"] = "0" * 64
    else:
        store.objects["raw/base.csv"] += b"alterado"
    store.objects["raw/manifest.json"] = json.dumps(manifest).encode()
    client = SimulatedClient()
    with pytest.raises(ValueError):
        run_enrichment(store, "raw/manifest.json", catalog, client=client)
    assert not client.calls


def test_evidence_and_proposals_preserve_originals_and_require_review(stored_input, catalog):
    store, _ = stored_input
    original = dict(store.objects)
    report = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])
    result = report["results"][0]
    assert result["status"] == "EVIDENCE_FOUND"
    evidence = next(item for item in result["evidence"] if item["attribute"] == "ALTURA")
    assert evidence["source_url"] == LF9009.url
    assert evidence["source_excerpt"] == "Height 300 mm"
    assert evidence["source_page"] == 1
    assert evidence["confidence_level"] == "LOW"
    assert "SIMULATED" in evidence["confidence_basis"]
    assert evidence["approval_status"] == "PENDING"
    assert evidence["extraction_rule"] == "catalog_labels_v1/ALTURA"
    assert hashlib.sha256(store.get(evidence["object_key"])).hexdigest() == evidence["source_sha256"]
    proposal = json.loads(store.get(result["proposal_key"]))
    assert proposal["proposal_type"] == "ENRICHMENT"
    assert proposal["status"] == proposal["technical_review_status"] == "PENDING"
    assert proposal["changeset"]["before"]["description"] == "FILTRO LF9009"
    assert "CURRENT_MATERIAL_VERSION_REQUIRED" in proposal["pending_checks"]
    assert all(store.get(key) == value for key, value in original.items())


def test_replay_is_offline_and_does_not_duplicate_artifacts(stored_input, catalog):
    store, _ = stored_input
    client = SimulatedClient()
    first = run_enrichment(store, "raw/manifest.json", catalog, client=client, material_codes=["27841570"])
    before = dict(store.objects)

    class NoNetwork:
        def fetch(self, spec):
            raise AssertionError("Replay não pode acessar a rede")

    second = run_enrichment(
        store,
        "raw/manifest.json",
        catalog,
        client=NoNetwork(),
        material_codes=["27841570"],
        evidence_manifest_key=first["report_key"],
    )
    assert second == first
    assert store.objects == before


def test_replay_checks_document_integrity(stored_input, catalog):
    store, _ = stored_input
    report = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])
    store.objects[report["documents"][LF9009.id]["object_key"]] += b"alterado"
    replay = run_enrichment(
        store, "raw/manifest.json", catalog, material_codes=["27841570"], evidence_manifest_key=report["report_key"]
    )
    assert replay["results"][0]["status"] == "PENDING"
    assert replay["results"][0]["proposal_key"] is None


def test_refetching_identical_content_keeps_the_same_proposal(stored_input, catalog):
    store, _ = stored_input
    first = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])

    class LaterClient:
        def fetch(self, spec):
            if spec.id != LF9009.id:
                raise SourceError("Fonte simulada indisponível")
            return replace(simulated_document(spec), retrieved_at="2026-11-06T12:00:00+00:00")

    second = run_enrichment(store, "raw/manifest.json", catalog, client=LaterClient(), material_codes=["27841570"])
    assert second == first


def test_reference_only_in_related_products_does_not_confirm_identity(catalog):
    html = b"<h1>LF3970</h1><h2>Related Products</h2><h1>LF9009</h1><p>Height 300 mm</p>"
    document = SourceDocument(LF9009.id, LF9009.url, html, "text/html", STAMP)
    assert (
        get_enrichment_repository().extract(catalog.classes["PDM100"], "FLEETGUARD", "LF9009", document_pages(document))
        == ()
    )


def test_divergent_sources_are_visible_and_neither_value_is_chosen(stored_input, catalog, monkeypatch):
    store, _ = stored_input
    second_spec = replace(LF9009, id="second-reviewed-source")
    monkeypatch.setitem(REAL_PRODUCTS, "27841570", replace(REAL_PRODUCTS["27841570"], sources=(LF9009, second_spec)))

    class ConflictingClient:
        def fetch(self, spec):
            return simulated_document(spec, height="300" if spec.id == LF9009.id else "301")

    report = run_enrichment(
        store, "raw/manifest.json", catalog, client=ConflictingClient(), material_codes=["27841570"]
    )
    result = report["results"][0]
    conflict = next(item for item in result["conflicts"] if item["attribute"] == "ALTURA")
    assert conflict["values"] == ["300MM", "301MM"]
    assert len(conflict["evidence_ids"]) == 2
    proposal = json.loads(store.get(result["proposal_key"]))
    assert not any(change["field"] == "ALTURA" for change in proposal["changeset"]["changes"])


def test_invented_excerpt_is_rejected():
    doc = simulated_document(LF9009)
    with pytest.raises(SourceError, match="Trecho"):
        record_evidence(
            MemoryStore(),
            "27841570",
            EnrichmentClaim("ALTURA", "999MM", "Height 999 mm", 1),
            LF9009,
            doc,
            document_pages(doc),
        )


def test_real_confidence_depends_on_source_kind_not_a_model_score():
    doc = replace(simulated_document(LF9009), simulated=False)
    claim = EnrichmentClaim("ALTURA", "300MM", "Height 300 mm", 1)
    high = record_evidence(MemoryStore(), "27841570", claim, LF9009, doc, document_pages(doc))
    medium = record_evidence(
        MemoryStore(), "27841570", claim, replace(LF9009, kind="DISTRIBUTOR"), doc, document_pages(doc)
    )
    assert (high.confidence_level, medium.confidence_level) == ("HIGH", "MEDIUM")
    assert high.approval_status == medium.approval_status == "PENDING"


def test_local_store_persists_report_and_replay(tmp_path, stored_input, catalog):
    memory, _ = stored_input
    store = LocalObjectStore(tmp_path)
    for key, content in memory.objects.items():
        store.put_if_absent(key, content)
    report = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])
    assert store.get(report["report_key"])
    replay = run_enrichment(
        store, "raw/manifest.json", catalog, material_codes=["27841570"], evidence_manifest_key=report["report_key"]
    )
    assert replay == report


def test_related_products_and_scripts_do_not_supply_attributes(catalog):
    html = (
        b"<h1>LF9009 FLEETGUARD</h1><script>Height 999 mm</script><h2>Specification</h2>"
        b"<p>Height 300 mm</p><h2>Related Parts</h2><p>LF3970 Height 176 mm</p>"
    )
    document = SourceDocument(LF9009.id, LF9009.url, html, "text/html", STAMP)
    claims = get_enrichment_repository().extract(
        catalog.classes["PDM100"], "FLEETGUARD", "LF9009", document_pages(document)
    )
    assert {claim.value for claim in claims if claim.attribute == "ALTURA"} == {"300MM"}


def test_reviewed_catalog_matches_exactly_the_original_real_records():
    with (KIT / "01_base_materiais.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    assert {row["CODIGO_MATERIAL"] for row in rows[-15:]} == set(REAL_PRODUCTS)
    assert len(REAL_PRODUCTS) == 15


def test_cli_offline_reads_the_same_store(tmp_path, stored_input, catalog, monkeypatch, capsys):
    from cli import main

    memory, _ = stored_input
    store = LocalObjectStore(tmp_path)
    for key, content in memory.objects.items():
        store.put_if_absent(key, content)
    report = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    assert (
        main(
            [
                "enrich-real-products",
                "--manifest-key",
                "raw/manifest.json",
                "--pdm-workbook",
                str(KIT / "03_padrao_cadastro_PDM.xlsx"),
                "--material-code",
                "27841570",
                "--evidence-manifest-key",
                report["report_key"],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["report_key"] == report["report_key"]


@pytest.mark.parametrize("kind", ["encrypted", "many_pages", "invalid"])
def test_unsupported_pdf_is_a_pending_source_error(kind):
    from pypdf import PdfWriter

    stream = io.BytesIO()
    if kind == "invalid":
        content = b"not a PDF"
    else:
        writer = PdfWriter()
        for _ in range(11 if kind == "many_pages" else 1):
            writer.add_blank_page(width=72, height=72)
        if kind == "encrypted":
            writer.encrypt("test-only-password")
        writer.write(stream)
        content = stream.getvalue()
    doc = SourceDocument("pdf", LF9009.url, content, "application/pdf", STAMP, simulated=True)
    with pytest.raises(SourceError, match="PDF"):
        document_pages(doc)


@pytest.mark.parametrize("array", [False, True])
def test_compressed_pdf_stops_at_decoding_budget_before_assembling_page(array):
    from pypdf import PdfWriter, get_configuration
    from pypdf.errors import LimitReachedError
    from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=72, height=72)
    parts = []
    for _ in range(2 if array else 1):
        stream = DecodedStreamObject()
        stream.set_data(b" " * (1_200_000 if array else 2_400_000))
        parts.append(writer._add_object(stream.flate_encode()))
    page[NameObject("/Contents")] = ArrayObject(parts) if array else parts[0]
    output = io.BytesIO()
    writer.write(output)
    assert len(output.getvalue()) < 2_000_000
    document = SourceDocument("pdf", LF9009.url, output.getvalue(), "application/pdf", STAMP)
    configuration = get_configuration()
    with pytest.raises(SourceError) as error:
        document_pages(document)
    assert isinstance(error.value.__cause__, LimitReachedError)
    assert get_configuration() == configuration


def test_readonly_evidence_builder_matches_the_persisted_producer():
    from enrichment import evidence as module

    builder = getattr(module, "build_attribute_evidence", None)
    assert builder is not None, "O preview deve reutilizar validação, confiança e identidade do produtor"
    document = simulated_document(LF9009)
    pages = document_pages(document)
    claim = EnrichmentClaim("ALTURA", "300MM", "Height 300 mm", 1)
    preview = builder("16031971", claim, LF9009, document, pages)
    store = MemoryStore()
    assert store.objects == {}
    persisted = record_evidence(store, "16031971", claim, LF9009, document, pages)
    assert preview == persisted
    assert store.objects
