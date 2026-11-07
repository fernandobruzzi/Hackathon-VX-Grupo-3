"""Fontes internas não completam identidade por semelhança ou vencem contradições."""

from dataclasses import replace
from pathlib import Path

import pytest

from domain.contracts import MaterialRecord
from domain.pdm_loader import load_pdm
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


def analyzed(catalog, code, text, **kwargs):
    return analyze_material(
        MaterialRecord(code, "ATIVO", text, unit="PC", **kwargs),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )


def source(catalog, code, text):
    from pipelines.internal_enrichment import InternalSource

    return InternalSource(analyzed(catalog, code, text), "01_base_materiais.csv", "a" * 64, "raw/base.csv")


FILTER = "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9009"


def test_missing_attribute_gets_exact_internal_evidence(catalog):
    from pipelines.internal_enrichment import internal_report

    target = analyzed(catalog, "target", FILTER)
    report = internal_report([target], [source(catalog, "donor", FILTER + "; ALTURA: 100MM")], catalog, "dataset")
    item = report["results"][0]
    assert item["suggestions"] == {"ALTURA": "100MM"}
    assert item["evidence"][0]["source_url"].endswith("#donor")
    assert "ALTURA: 100MM" in item["evidence"][0]["source_excerpt"]
    assert item["evidence"][0]["source_sha256"] == "a" * 64
    assert report["summary"]["suggested_attributes"] == 1
    assert "ALTURA" not in target.attributes


def test_conflicting_donors_are_held_without_choosing_a_value(catalog):
    from pipelines.internal_enrichment import internal_report

    sources = [source(catalog, str(n), FILTER + f"; ALTURA: {n}MM") for n in (100, 200)]
    item = internal_report([analyzed(catalog, "t", FILTER)], sources, catalog, "d")["results"][0]
    assert item["suggestions"] == {}
    assert item["conflicts"]["ALTURA"] == ["100MM", "200MM"]
    assert len(item["evidence"]) == 2


@pytest.mark.parametrize(
    "text",
    [
        FILTER.replace("FLEETGUARD", "DONALDSON"),
        FILTER.replace("LF9009", "LF9009-01"),
        "FILTRO OLEO LUBRIFICANTE; REFERENCIA FABRICANTE: LF9009",
        FILTER.replace("OLEO LUBRIFICANTE", "COMBUSTIVEL"),
    ],
)
def test_different_or_unknown_identity_never_supplies_values(catalog, text):
    from pipelines.internal_enrichment import internal_report

    report = internal_report(
        [analyzed(catalog, "t", FILTER)], [source(catalog, "s", text + "; ALTURA: 100MM")], catalog, "d"
    )
    assert report["results"][0]["suggestions"] == {}


def test_known_conflict_blocks_other_attributes_from_the_same_source(catalog):
    from pipelines.internal_enrichment import internal_report

    target = analyzed(catalog, "t", FILTER + "; ALTURA: 100MM")
    donor = source(catalog, "s", FILTER + "; ALTURA: 200MM; DIAMETRO EXTERNO: 50MM")
    item = internal_report([target], [donor], catalog, "d")["results"][0]
    assert item["suggestions"] == {}
    assert item["conflicts"]["ALTURA"] == ["100MM", "200MM"]


def test_incomplete_technical_identity_remains_a_request_for_information(catalog):
    from pipelines.internal_enrichment import internal_report

    target = analyzed(catalog, "t", "PARAFUSO SEXTAVADO M12X50 8.8")
    donor = source(catalog, "s", "PARAFUSO SEXTAVADO M12X50 8.8 ACO CARBONO ZINCADO BRANCO DIN 933")
    item = internal_report([target], [donor], catalog, "d")["results"][0]
    assert item["suggestions"] == {}
    assert "MATERIAL" in item["before"]["missing_required"]
    assert item["after_suggestions"]["missing_required"] == item["before"]["missing_required"]


def test_approved_attributes_survive_analysis_and_original_conflicts_are_visible(catalog):
    record = MaterialRecord("t", "ATIVO", FILTER, attributes={"ALTURA": "100MM"})
    result = analyze_material(record, catalog, get_classification_repository(catalog), get_extraction_repository())
    assert result.attributes["ALTURA"] == "100MM"
    conflict = analyze_material(
        replace(record, description=FILTER + "; ALTURA: 200MM"),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    assert conflict.identity_key is None
    assert "PERSISTED_ATTRIBUTE_CONFLICT:ALTURA" in conflict.review_reasons


def test_internal_plan_uses_partial_enrichment_without_external_product_allowlist(catalog):
    from repositories.enrichment_repository import plan_internal_enrichment

    target = {
        "id": "material",
        "material_code": "synthetic",
        "dataset_id": "dataset",
        "version": 1,
        "original_description_long": FILTER,
        "manufacturer": "FLEETGUARD",
        "manufacturer_reference": "LF9009",
        "attributes": {},
        "unit": "PC",
        "ncm": "84212300",
    }
    item = {
        "material_code": "synthetic",
        "pdm_class_id": "PDM100",
        "evidence": [{"attribute": "ALTURA", "proposed_value": "100MM", "source_url": "dataset://dataset/base#s"}],
    }
    changes, baseline = plan_internal_enrichment(target, item, catalog, "a" * 64, "runs/internal/r.json")
    assert changes["enrichment_context"]["schema_version"] == "internal-enrichment-v1"
    assert changes["after"]["attributes"]["ALTURA"] == "100MM"
    assert "ALTURA" not in baseline
    assert changes["after"]["unit"] == target["unit"] and changes["after"]["ncm"] == target["ncm"]


def test_source_bytes_must_match_dataset_hash(catalog):
    from pipelines.internal_enrichment import read_sources

    class Store:
        def get(self, key):
            return b"alterado"

    with pytest.raises(ValueError, match="Hash"):
        read_sources(
            [{"name": "01_base_materiais.csv", "object_key": "raw/base.csv", "sha256": "0" * 64}], Store(), catalog
        )


def test_missing_sources_are_explicit(catalog):
    from pipelines.internal_enrichment import read_sources

    sources, missing = read_sources([], None, catalog)
    assert sources == []
    assert set(missing) == {"01_base_materiais.csv", "02_pedidos_cadastro.csv"}


def test_unknown_condition_is_not_counted_as_optional_or_complete(catalog):
    from pipelines.internal_enrichment import completeness

    target = analyzed(catalog, "t", "CONEXAO")
    target = replace(target, pdm_class_id="PDM050", item_name=None, attributes={})
    result = completeness(target, catalog)
    assert result["conditional_pending"]
    assert result["status"] == "INCOMPLETE"


@pytest.mark.parametrize("error_code", ["NoSuchKey", "AccessDenied"])
def test_missing_s3_source_is_pending_but_access_errors_propagate(catalog, error_code):
    from botocore.exceptions import ClientError

    from pipelines.internal_enrichment import read_sources

    class Store:
        def get(self, key):
            raise ClientError({"Error": {"Code": error_code}}, "GetObject")

    entry = {"name": "01_base_materiais.csv", "object_key": "raw/base.csv", "sha256": "0" * 64}
    if error_code == "NoSuchKey":
        sources, missing = read_sources([entry], Store(), catalog)
        assert not sources and "01_base_materiais.csv" in missing
    else:
        with pytest.raises(ClientError):
            read_sources([entry], Store(), catalog)


@pytest.mark.parametrize(
    "suffix",
    [
        "\n" + FILTER.replace("LF9009", "LF7000") + "; ALTURA: 200MM",
        "; ALTURA: 100MM; ALTURA: 200MM",
    ],
)
def test_contradictions_inside_a_single_source_cannot_supply_attributes(catalog, suffix):
    from pipelines.internal_enrichment import internal_report

    report = internal_report([analyzed(catalog, "t", FILTER)], [source(catalog, "s", FILTER + suffix)], catalog, "d")
    item = report["results"][0]
    assert not item["suggestions"]
    assert item["rejected_sources"] or report["unusable_sources"]


def test_ambiguous_target_cannot_receive_values(catalog):
    from pipelines.internal_enrichment import internal_report

    target = analyzed(catalog, "t", FILTER + "; REFERENCIA FABRICANTE: LF7000")
    item = internal_report([target], [source(catalog, "s", FILTER + "; ALTURA: 100MM")], catalog, "d")["results"][0]
    assert not item["suggestions"]
    assert item["record_conflicts"]


def test_inline_reference_aliases_cannot_hide_another_product(catalog):
    from pipelines.internal_enrichment import internal_report

    text = "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; PN LF9009 PN LF7000; ALTURA: 200MM"
    item = internal_report([analyzed(catalog, "t", FILTER)], [source(catalog, "s", text)], catalog, "d")["results"][0]
    assert not item["suggestions"]
