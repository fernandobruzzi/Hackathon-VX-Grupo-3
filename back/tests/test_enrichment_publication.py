"""Publicação usa documentos preservados e nunca resolve dúvidas por suposição."""

import csv
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

import pytest
from test_enrichment import KIT, SimulatedClient
from test_enrichment import catalog as catalog
from test_enrichment import stored_input as stored_input

from domain.enrichment_rules import evidence_hash, original_item_name
from enrichment.catalog import LF9009
from pipelines.enrich_real_products import run_enrichment
from repositories.enrichment import get_enrichment_repository
from repositories.enrichment_repository import plan_enrichment, replay_report


def material(code="27841570"):
    with (KIT / "01_base_materiais.csv").open(encoding="utf-8-sig", newline="") as source:
        row = next(row for row in csv.DictReader(source) if row["CODIGO_MATERIAL"] == code)
    return {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "dataset_id": "88888888-8888-4888-8888-888888888888",
        "material_code": code,
        "original_description_long": row["DESCRICAO_LONGA"],
        "manufacturer": row["FABRICANTE"],
        "manufacturer_reference": row["REFERENCIA_FABRICANTE"],
        "attributes": {},
        "pdm_class_id": None,
        "unit": row["UNIDADE_MEDIDA"],
        "ncm": row["NCM"],
        "version": 1,
    }


def test_publication_replays_frozen_bytes_and_preserves_originals(stored_input, catalog, monkeypatch):
    store, _ = stored_input
    report = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setattr(
        "enrichment.trusted_sources.TrustedSourceClient.fetch", lambda *_: pytest.fail("Rede no replay")
    )
    manifest, replay = replay_report(store, report["report_key"], catalog)
    before = material()
    changes, baseline = plan_enrichment(
        before, replay["results"][0], catalog, report["input_manifest_sha256"], report["report_key"]
    )
    assert changes["after"]["attributes"]["ALTURA"] == "300MM"
    assert changes["after"]["attributes"]["DIAMETRO EXTERNO"] == "118,87MM"
    assert changes["after"]["ncm"] == before["ncm"]
    assert changes["after"]["unit"] == before["unit"]
    assert "ALTURA" not in baseline
    assert before == material()
    assert changes["enrichment_context"]["manifest_sha256"] == report["input_manifest_sha256"]
    assert manifest["dataset_id"] == before["dataset_id"]


def test_tampered_report_cannot_be_published(stored_input, catalog):
    store, _ = stored_input
    report = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])
    raw = json.loads(store.get(report["report_key"]))
    raw["results"][0]["evidence"][0]["proposed_value"] = "inventado"
    store.objects[report["report_key"]] = json.dumps(raw).encode()
    with pytest.raises(ValueError, match="Hash"):
        replay_report(store, report["report_key"], catalog)


def test_simulated_report_refuses_production(stored_input, catalog, monkeypatch):
    store, _ = stored_input
    report = run_enrichment(store, "raw/manifest.json", catalog, client=SimulatedClient(), material_codes=["27841570"])
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="simulada"):
        replay_report(store, report["report_key"], catalog)


def test_divergent_and_invalid_values_stay_outside_approval(catalog):
    item = {
        "material_code": "28490077",
        "evidence": [
            {"attribute": "DIAMETRO INTERNO", "proposed_value": "25MM", "source_url": LF9009.url},
            {"attribute": "DIAMETRO INTERNO", "proposed_value": "26MM", "source_url": LF9009.url},
            {"attribute": "LARGURA", "proposed_value": "15MM", "source_url": LF9009.url},
            {"attribute": "REFERENCIA", "proposed_value": "6205DDUC3", "source_url": LF9009.url},
        ],
    }
    changes, _ = plan_enrichment(material("28490077"), item, catalog, "a" * 64, "report")
    assert "DIAMETRO INTERNO" in changes["enrichment_context"]["divergent_attributes"]
    assert "REFERENCIA" in changes["enrichment_context"]["blocked_attributes"]
    assert "DIAMETRO INTERNO" not in changes["after"]["attributes"]
    assert changes["after"]["attributes"]["LARGURA"] == "15MM"


def test_identity_and_synthetic_codes_are_refused(catalog):
    with pytest.raises(ValueError, match="15 produtos"):
        plan_enrichment(
            material() | {"material_code": "synthetic"}, {"material_code": "synthetic"}, catalog, "a" * 64, "r"
        )
    with pytest.raises(ValueError, match="identidade"):
        plan_enrichment(material(), {"material_code": "28490077"}, catalog, "a" * 64, "r")


def test_filter_name_is_read_from_original_instead_of_first_option(catalog):
    assert (
        original_item_name(catalog, "PDM100", material() | {"original_description_long": "FILTRO COMBUSTIVEL LF9009"})
        == "FILTRO COMBUSTIVEL"
    )
    assert original_item_name(catalog, "PDM100", material() | {"original_description_long": "FILTRO LF9009"}) is None
    assert (
        original_item_name(
            catalog, "PDM100", material() | {"original_description_long": "FILTRO COMBUSTIVEL E FILTRO AR LF9009"}
        )
        is None
    )


@pytest.mark.parametrize("class_id,description,group", [("PDM110", "BUCHA", "SOB01"), ("PDM050", "CAP", "TUB01")])
def test_original_group_resolves_an_ambiguous_item_without_using_a_revised_group(catalog, class_id, description, group):
    original = material() | {"original_description_long": description, "original_merchandise_group": group}
    assert original_item_name(catalog, class_id, original) == description
    assert original_item_name(catalog, class_id, original | {"original_merchandise_group": None}) is None
    assert (
        original_item_name(
            catalog, class_id, original | {"original_merchandise_group": None, "merchandise_group": group}
        )
        is None
    )


@pytest.mark.parametrize(
    "field",
    ["source_excerpt", "source_sha256", "confidence_level", "confidence_basis", "s3_object_key", "proposed_value"],
)
def test_evidence_hash_binds_provenance_and_confidence(field):
    source = {
        "proposed_value": "25MM",
        "source_excerpt": "Bore diameter 25 mm",
        "source_sha256": "a" * 64,
        "confidence_level": "LOW",
        "confidence_basis": ["SIMULATED"],
        "s3_object_key": "evidence/raw",
        "retrieved_at": datetime(2026, 11, 6, tzinfo=UTC),
    }
    changed = deepcopy(source)
    changed[field] = ["MANUFACTURER_DOMAIN"] if field == "confidence_basis" else "alterado"
    assert evidence_hash(changed) != evidence_hash(source)
    assert evidence_hash(
        source | {"retrieved_at": source["retrieved_at"].astimezone(timezone(timedelta(hours=-3)))}
    ) == evidence_hash(source)


def test_decimal_dimensions_follow_pdm_spelling(catalog):
    claims = get_enrichment_repository().extract(
        catalog.classes["PDM100"],
        "FLEETGUARD",
        "LF9009",
        ("HTML_PRODUCT_TITLE: LF9009\nSpecification\nHeight 118.87 mm",),
    )
    assert any(claim.value == "118,87MM" and claim.excerpt == "Height 118.87 mm" for claim in claims)
