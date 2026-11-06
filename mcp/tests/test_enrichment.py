"""Cache de evidências: autorização, elegibilidade e pendência sem pesquisa inventada."""

import pytest

from vx_materials_mcp.tools.enrich_from_trusted_source import Enrichment


class Repository:
    def __init__(self, eligible=True, rows=()):
        self.eligible = eligible
        self.rows = list(rows)
        self.reads = 0

    def require_real_material(self, code):
        if not self.eligible:
            raise ValueError("Codigo fora dos 15 produtos reais")

    def evidence_for_material(self, code, attributes):
        self.reads += 1
        return [r for r in self.rows if r["attribute_name"] in attributes]


def evidence(value="DONALDSON", source_id="source-1"):
    return {
        "id": source_id,
        "attribute_name": "FABRICANTE",
        "proposed_value": value,
        "source_url": "https://example.invalid/catalog",
        "source_title": "Exemplo de teste",
        "source_excerpt": "Trecho de teste",
        "source_page": None,
        "confidence_level": "HIGH",
        "confidence_basis": ["EXACT_PART_NUMBER"],
        "status": "PENDING",
    }


def test_synthetic_code_never_reads_the_cache():
    repository = Repository(eligible=False)
    with pytest.raises(ValueError, match="15 produtos"):
        Enrichment(repository).run("synthetic", ["FABRICANTE"])
    assert repository.reads == 0


def test_no_evidence_reports_service_unavailable_without_fabricated_values():
    result = Enrichment(Repository()).run("real", ["FABRICANTE"])
    assert result.status == "PENDING"
    assert result.attributes == []
    assert result.pending_attributes == ["FABRICANTE"]
    assert result.pending_reason == "TRUSTED_SOURCE_SERVICE_UNAVAILABLE"


def test_cache_preserves_source_confidence_and_approval_status():
    result = Enrichment(Repository(rows=[evidence()])).run("real", ["FABRICANTE"])
    assert result.status == "EVIDENCE_FOUND"
    assert result.pending_reason is None
    item = result.attributes[0]
    assert item.valor == "DONALDSON"
    assert item.fonte.source_id == "source-1"
    assert item.confianca.basis == ["EXACT_PART_NUMBER"]
    assert item.approval_status == "PENDING"


def test_refresh_returns_cached_values_and_explicit_pending_refresh():
    result = Enrichment(Repository(rows=[evidence()])).run("real", ["FABRICANTE"], refresh=True)
    assert result.status == "PENDING"
    assert result.attributes[0].valor == "DONALDSON"
    assert result.pending_attributes == ["FABRICANTE"]
    assert result.pending_reason == "TRUSTED_SOURCE_SERVICE_UNAVAILABLE"


def test_partial_cache_and_divergent_sources_require_review():
    result = Enrichment(Repository(rows=[evidence(), evidence("OUTRO", "source-2")])).run(
        "real", ["FABRICANTE", "REFERENCIA"]
    )
    assert result.status == "PENDING"
    assert result.pending_attributes == ["REFERENCIA"]
    assert result.conflicts == ["FABRICANTE"]
    assert len(result.attributes) == 2


def test_empty_or_excessive_requests_fail_before_cache_lookup():
    repository = Repository()
    for names in ([], [""], ["FABRICANTE"] * 51):
        with pytest.raises(ValueError):
            Enrichment(repository).run("real", names)
    assert repository.reads == 0
