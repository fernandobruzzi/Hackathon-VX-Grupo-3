"""Preview sem persistência usa cliente, documentos e extrator reais com bytes simulados."""

import pytest
from conftest import PDM
from test_enrichment import Repository, evidence

from domain.pdm_loader import load_pdm
from enrichment.catalog import REAL_PRODUCTS
from enrichment.trusted_sources import SourceDocument, SourceError
from vx_materials_mcp.tools import enrich_from_trusted_source as module


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(PDM)


class Client:
    def __init__(self, *, fail=False, clock=None, url=None, source_id=None, content=b"DONALDSON DBL7300 Height 200 mm"):
        self.fail, self.clock, self.url, self.source_id = fail, clock, url, source_id
        self.content = content
        self.calls = []

    def fetch(self, source):
        self.calls.append(source)
        if self.fail:
            raise SourceError("Fonte indisponível de teste")
        if self.clock is not None:
            self.clock[0] += 4
        return SourceDocument(
            self.source_id or source.id,
            self.url or source.url,
            self.content,
            "text/plain",
            "2026-11-07T00:00:00+00:00",
            True,
        )


def research(catalog, client, *, clock=lambda: 0.0):
    factory = getattr(module, "TrustedSourceResearch", None)
    assert factory is not None, "A pesquisa precisa reutilizar o cliente e extrator da #23"
    return factory(catalog, client_factory=lambda limits: client, clock=clock)


def test_preview_uses_registered_extractor_and_never_claims_persistence(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    client = Client()
    result = module.Enrichment(Repository(), research(catalog, client)).run("18308575", ["FABRICANTE", "ALTURA"])
    assert result.status == "EVIDENCE_FOUND"
    assert {(row.attribute, row.valor) for row in result.attributes} == {
        ("FABRICANTE", "DONALDSON"),
        ("ALTURA", "200MM"),
    }
    assert all(row.persisted is False and row.approval_status == "PENDING_PUBLICATION" for row in result.attributes)
    assert all(row.confianca.level == "LOW" and "SIMULATED" in row.confianca.basis for row in result.attributes)
    assert all(row.fonte.sha256 and len(row.fonte.sha256) == 64 for row in result.attributes)
    assert all(row.fonte.url == REAL_PRODUCTS["18308575"].sources[0].url for row in result.attributes)
    assert client.calls == list(REAL_PRODUCTS["18308575"].sources)


def test_complete_cache_does_not_fetch_external_sources(catalog):
    client = Client(fail=True)
    result = module.Enrichment(Repository(rows=[evidence()]), research(catalog, client)).run("18308575", ["FABRICANTE"])
    assert result.status == "EVIDENCE_FOUND"
    assert result.attributes[0].persisted is True
    assert client.calls == []


def test_late_refresh_discards_new_preview_and_preserves_cached_evidence(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    clock = [0.0]
    result = module.Enrichment(
        Repository(rows=[evidence()]), research(catalog, Client(clock=clock), clock=lambda: clock[0])
    ).run("18308575", ["FABRICANTE"], refresh=True)
    assert result.status == "PENDING"
    assert result.pending_reason == "SOURCE_QUERY_TIMEOUT"
    assert result.pending_attributes == ["FABRICANTE"]
    assert len(result.attributes) == 1 and result.attributes[0].persisted is True


def test_source_failure_preserves_partial_cache_without_scheduling_a_job(catalog):
    result = module.Enrichment(Repository(rows=[evidence()]), research(catalog, Client(fail=True))).run(
        "18308575", ["FABRICANTE", "ALTURA"]
    )
    assert result.status == "PENDING"
    assert result.pending_reason == "SOURCE_UNAVAILABLE"
    assert result.pending_attributes == ["ALTURA"]
    assert len(result.attributes) == 1 and result.attributes[0].persisted is True


def test_refresh_keeps_divergent_cached_and_preview_values_for_review(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    result = module.Enrichment(Repository(rows=[evidence("OUTRO")]), research(catalog, Client())).run(
        "18308575", ["FABRICANTE"], refresh=True
    )
    assert result.conflicts == ["FABRICANTE"]
    assert {row.valor for row in result.attributes} == {"OUTRO", "DONALDSON"}


@pytest.mark.parametrize("code, names", [("synthetic", ["FABRICANTE"]), ("18308575", ["URL_ARBITRARIA"])])
def test_unknown_product_or_attribute_never_fetches_a_source(catalog, code, names):
    client = Client()
    with pytest.raises(ValueError):
        module.Enrichment(Repository(), research(catalog, client)).run(code, names)
    assert client.calls == []


def test_authorization_precedes_external_research(catalog):
    client = Client()
    with pytest.raises(ValueError, match="15 produtos"):
        module.Enrichment(Repository(eligible=False), research(catalog, client)).run("18308575", ["FABRICANTE"])
    assert client.calls == []


@pytest.mark.parametrize("options", [{"url": "https://127.0.0.1/private"}, {"source_id": "other-source"}])
def test_document_must_match_the_server_selected_source(catalog, monkeypatch, options):
    monkeypatch.setenv("APP_ENV", "local")
    result = module.Enrichment(Repository(), research(catalog, Client(**options))).run("18308575", ["FABRICANTE"])
    assert result.status == "PENDING"
    assert result.pending_reason == "SOURCE_UNAVAILABLE"
    assert result.attributes == []


def test_unreviewed_exact_reference_never_substitutes_a_product_variant(catalog):
    client = Client()
    result = module.Enrichment(Repository(), research(catalog, client)).run("16303905", ["DIAMETRO INTERNO"])
    assert result.pending_reason == "NO_REVIEWED_EXACT_PRODUCT_SOURCE"
    assert result.attributes == [] and client.calls == []


def test_simulated_bytes_cannot_be_presented_as_deployed_evidence(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="simulad"):
        module.Enrichment(Repository(), research(catalog, Client())).run("18308575", ["FABRICANTE"])


def test_partial_preview_leaves_the_missing_attribute_explicit(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    result = module.Enrichment(Repository(), research(catalog, Client())).run(
        "18308575", ["FABRICANTE", "DIAMETRO EXTERNO"]
    )
    assert result.status == "PENDING" and result.pending_reason == "EVIDENCE_NOT_FOUND"
    assert result.pending_attributes == ["DIAMETRO EXTERNO"]


def test_registered_tool_invokes_the_bounded_preview_adapter(catalog, monkeypatch):
    import asyncio

    from vx_materials_mcp import server as server_module

    monkeypatch.setenv("APP_ENV", "local")
    client = Client()
    monkeypatch.setattr(
        server_module, "TrustedSourceResearch", lambda _catalog: research(catalog, client), raising=False
    )
    server = server_module.build_server(catalog, resources=Repository())
    result = asyncio.run(
        server.call_tool(
            "enrich_from_trusted_source", {"material_code": "18308575", "attributes_requested": ["ALTURA"]}
        )
    )
    assert result.structured_content["status"] == "EVIDENCE_FOUND"
    assert result.structured_content["attributes"][0]["persisted"] is False
    assert client.calls


def test_multiple_sources_share_one_network_deadline(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    clock, limits = [0.0], []

    class TwoSources:
        def fetch(self, source):
            clock[0] += 1.25
            return SourceDocument(
                source.id,
                source.url,
                b"FLEETGUARD LF9009 Height 200 mm",
                "text/plain",
                "2026-11-07T00:00:00+00:00",
                True,
            )

    def factory(limit):
        limits.append(limit)
        return TwoSources()

    preview = module.TrustedSourceResearch(catalog, client_factory=factory, clock=lambda: clock[0])
    result = module.Enrichment(Repository(), preview).run("16031971", ["FABRICANTE"])
    assert result.status == "EVIDENCE_FOUND"
    assert [limit.total_timeout for limit in limits] == [3, 1.75]
    assert all(limit.io_timeout <= 1 for limit in limits)
    assert len(result.attributes) == 2


def test_transport_deadline_failure_is_reported_as_timeout_with_cache_preserved(catalog):
    clock = [0.0]

    class LateFailure:
        def fetch(self, _source):
            clock[0] += 4
            raise SourceError("Tempo total de consulta excedido")

    result = module.Enrichment(
        Repository(rows=[evidence()]), research(catalog, LateFailure(), clock=lambda: clock[0])
    ).run("18308575", ["FABRICANTE"], refresh=True)
    assert result.pending_reason == "SOURCE_QUERY_TIMEOUT"
    assert result.pending_attributes == ["FABRICANTE"]
    assert len(result.attributes) == 1 and result.attributes[0].persisted is True


@pytest.mark.parametrize(
    "change",
    [
        {"manufacturer_reference": "6310-2Z/C3"},
        {"manufacturer": "NSK"},
        {"pdm_class_id": "PDM100"},
        {"attributes": {"REFERENCIA": "6310-ZZ/C3"}},
    ],
)
def test_changed_current_product_never_fetches_the_original_catalog_source(catalog, change):
    current = {
        "manufacturer": "SKF",
        "manufacturer_reference": "6205-2RSH/C3",
        "pdm_class_id": "PDM020",
        "attributes": {},
        **change,
    }
    cached = {**evidence("25MM"), "attribute_name": "DIAMETRO INTERNO"}
    client = Client()
    result = module.Enrichment(Repository(rows=[cached], current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"], refresh=True
    )
    assert result.status == "PENDING" and result.pending_reason == "CURRENT_PRODUCT_IDENTITY_CHANGED"
    assert result.pending_attributes == ["DIAMETRO INTERNO"]
    assert len(result.attributes) == 1 and result.attributes[0].persisted is True
    assert client.calls == []


def test_changed_product_cache_is_provenance_without_claiming_current_evidence_found(catalog):
    current = {
        "manufacturer": "SKF",
        "manufacturer_reference": "6310-2Z/C3",
        "pdm_class_id": "PDM020",
        "attributes": {},
    }
    cached = {**evidence("25MM"), "attribute_name": "DIAMETRO INTERNO"}
    client = Client()
    result = module.Enrichment(Repository(rows=[cached], current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"]
    )
    assert result.status == "PENDING" and result.pending_reason == "CURRENT_PRODUCT_IDENTITY_CHANGED"
    assert result.attributes[0].persisted is True
    assert client.calls == []


@pytest.mark.parametrize("code", sorted(REAL_PRODUCTS))
def test_reviewed_bootstrap_identity_survives_missing_canonical_metadata(catalog, code):
    from pathlib import Path

    from pipelines.sanitize import read_csv_records

    records = {row.code: row for row in read_csv_records(Path(PDM).with_name("01_base_materiais.csv"))}
    row = records[code]
    current = {
        "manufacturer": row.manufacturer,
        "manufacturer_reference": row.reference,
        "pdm_class_id": None,
        "attributes": {},
        "original_description_long": row.description,
        "original_description_short": row.short_description,
    }
    checker = getattr(research(catalog, Client()), "matches_current_product", None)
    assert checker is not None, "O preview precisa conferir o produto atual além do código do manifesto"
    assert checker(code, current)


def test_genuine_bearing_reference_separator_spelling_keeps_research_available(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")

    class BearingClient(Client):
        def fetch(self, source):
            self.calls.append(source)
            return SourceDocument(
                source.id,
                source.url,
                b"SKF 6205-2RSH/C3 Bore diameter 25 mm",
                "text/plain",
                "2026-11-07T00:00:00+00:00",
                True,
            )

    current = {
        "manufacturer": " skf ",
        "manufacturer_reference": "6205 2rsh / c3",
        "pdm_class_id": "PDM020",
        "attributes": {},
    }
    client = BearingClient()
    result = module.Enrichment(Repository(current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"]
    )
    assert result.status == "EVIDENCE_FOUND"
    assert result.attributes[0].valor == "25MM" and client.calls


@pytest.mark.parametrize("description", ["ROL 6310-2Z/C3 SKF", "ROL 6205-2RSH/C3X SKF", "ROL 6205-2RSH/C3/EM SKF"])
def test_missing_metadata_never_overrides_conflicting_or_variant_raw_reference(catalog, description):
    current = {
        "manufacturer": "SKF",
        "manufacturer_reference": "",
        "pdm_class_id": None,
        "attributes": {},
        "original_description_long": description,
    }
    client = Client()
    result = module.Enrichment(Repository(current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"]
    )
    assert result.pending_reason == "CURRENT_PRODUCT_IDENTITY_CHANGED"
    assert client.calls == []


def test_real_bootstrap_bearing_can_preview_before_canonical_fields_exist(catalog, monkeypatch):
    from pathlib import Path

    from pipelines.sanitize import read_csv_records

    monkeypatch.setenv("APP_ENV", "local")
    row = next(row for row in read_csv_records(Path(PDM).with_name("01_base_materiais.csv")) if row.code == "20866024")
    current = {
        "manufacturer": row.manufacturer,
        "manufacturer_reference": row.reference,
        "pdm_class_id": None,
        "attributes": {},
        "original_description_long": row.description,
    }
    client = Client(content=b"SKF 6205-2RSH/C3 Bore diameter 25 mm")
    result = module.Enrichment(Repository(current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"]
    )
    assert result.status == "EVIDENCE_FOUND"
    assert result.attributes[0].valor == "25MM" and client.calls


def test_missing_manufacturer_does_not_hide_a_conflicting_reviewed_brand_in_raw_source(catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    current = {
        "manufacturer": "",
        "manufacturer_reference": "",
        "pdm_class_id": None,
        "attributes": {},
        "original_description_long": "ROL 6205-2RSH/C3 NSK",
    }
    client = Client(content=b"SKF 6205-2RSH/C3 Bore diameter 25 mm")
    result = module.Enrichment(Repository(current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"]
    )
    assert result.pending_reason == "CURRENT_PRODUCT_IDENTITY_CHANGED"
    assert client.calls == []


@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [
        ("X-", ""),
        ("X/", ""),
        ("X.", ""),
        ("X", ""),
        ("1-", ""),
        ("1/", ""),
        ("1.", ""),
        ("1", ""),
        ("X_", ""),
        ("1_", ""),
        ("", "-EM"),
        ("", "/EM"),
        ("", ".EM"),
        ("", "EM"),
        ("", "-1"),
        ("", "/1"),
        ("", ".1"),
        ("", "1"),
        ("", "_EM"),
        ("", "_1"),
    ],
)
@pytest.mark.parametrize("refresh", [False, True])
def test_raw_reference_requires_the_whole_reviewed_sku_token(catalog, monkeypatch, prefix, suffix, refresh):
    monkeypatch.setenv("APP_ENV", "local")
    current = {
        "manufacturer": "SKF",
        "manufacturer_reference": "",
        "pdm_class_id": None,
        "attributes": {},
        "original_description_long": f"ROL {prefix}6205-2RSH/C3{suffix} SKF",
    }
    cached = {**evidence("25MM"), "attribute_name": "DIAMETRO INTERNO"}
    client = Client(content=b"SKF 6205-2RSH/C3 Bore diameter 25 mm")
    result = module.Enrichment(Repository(rows=[cached], current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"], refresh=refresh
    )
    assert result.status == "PENDING"
    assert result.pending_reason == "CURRENT_PRODUCT_IDENTITY_CHANGED"
    assert result.pending_attributes == ["DIAMETRO INTERNO"]
    assert len(result.attributes) == 1 and result.attributes[0].persisted is True
    assert client.calls == []


@pytest.mark.parametrize("spelling", ["6205 2rsh / c3", "6205.2rsh.c3", "6205/2rsh-c3"])
@pytest.mark.parametrize("refresh", [False, True])
def test_raw_reference_preserves_case_and_in_sku_separator_spelling(catalog, monkeypatch, refresh, spelling):
    monkeypatch.setenv("APP_ENV", "local")
    current = {
        "manufacturer": "SKF",
        "manufacturer_reference": "",
        "pdm_class_id": None,
        "attributes": {},
        "original_description_long": f"ROL {spelling} SKF",
    }
    cached = {**evidence("25MM"), "attribute_name": "DIAMETRO INTERNO"}
    client = Client(content=b"SKF 6205-2RSH/C3 Bore diameter 25 mm")
    result = module.Enrichment(Repository(rows=[cached], current=current), research(catalog, client)).run(
        "20866024", ["DIAMETRO INTERNO"], refresh=refresh
    )
    assert result.status == "EVIDENCE_FOUND" and result.pending_reason is None
    assert all(row.valor == "25MM" for row in result.attributes)
    assert any(row.persisted is True for row in result.attributes)
    assert bool(client.calls) is refresh


@pytest.mark.parametrize("code", sorted(REAL_PRODUCTS))
@pytest.mark.parametrize(("prefix", "suffix"), [("X-", ""), ("", ".EM")])
def test_extracted_reference_cannot_bypass_whole_sku_identity(catalog, code, prefix, suffix):
    product = REAL_PRODUCTS[code]
    attribute = "REFERENCIA" if product.pdm_class_id == "PDM020" else "REFERENCIA FABRICANTE"
    current = {
        "manufacturer": product.manufacturer,
        "manufacturer_reference": "",
        "pdm_class_id": product.pdm_class_id,
        "attributes": {},
        "original_description_long": f"PECA {product.manufacturer} {prefix}{product.reference}{suffix}",
    }
    cached = {**evidence(product.reference), "attribute_name": attribute}
    client = Client()
    result = module.Enrichment(Repository(rows=[cached], current=current), research(catalog, client)).run(
        code, [attribute]
    )
    assert result.status == "PENDING", code
    assert result.pending_reason == "CURRENT_PRODUCT_IDENTITY_CHANGED", code
    assert len(result.attributes) == 1 and result.attributes[0].persisted is True
    assert client.calls == []
