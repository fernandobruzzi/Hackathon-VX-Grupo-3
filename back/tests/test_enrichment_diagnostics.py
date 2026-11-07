"""Lacunas explicam o limite da evidência sem declarar ausências como fatos."""

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


def material(catalog, text):
    return analyze_material(
        MaterialRecord("t", "ATIVO", text), catalog, get_classification_repository(catalog), get_extraction_repository()
    )


def test_unclassified_has_classifier_status_and_targeted_question(catalog):
    from pipelines.internal_enrichment import internal_report

    item = internal_report([material(catalog, "ITEM SEM IDENTIFICACAO")], [], catalog, "d")["results"][0]
    assert item["classification"]["status"] in {"UNRESOLVED", "OUT_OF_SCOPE"}
    assert item["gaps"][0]["attribute"] is None
    assert item["gaps"][0]["question"]


def test_gap_reason_is_evidence_limit_and_has_pdm_question(catalog):
    from pipelines.internal_enrichment import internal_report

    target = material(catalog, "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9009")
    item = internal_report([target], [], catalog, "d")["results"][0]
    optional = [g for g in item["gaps"] if g["attribute"] == "ALTURA"]
    assert optional and optional[0]["reason"] == "NO_SUPPORTED_EVIDENCE"
    assert optional[0]["question"]


def test_record_conflicts_count_separately(catalog):
    from pipelines.internal_enrichment import internal_report

    target = material(
        catalog,
        "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9009; ALTURA: 100MM; ALTURA: 200MM",
    )
    target = replace(target, identity_key=None)
    report = internal_report([target], [], catalog, "d")
    assert report["summary"]["materials_with_record_conflicts"] == 1
    assert report["summary"]["materials_with_source_conflicts"] == 0
    assert any(g["reason"] == "CONTRADICTORY_OBSERVATIONS" for g in report["results"][0]["gaps"])


def test_assisted_candidates_never_become_publishable_suggestions(catalog):
    from pipelines.internal_enrichment import internal_report

    class Assistant:
        usage = {"calls": {}, "input_tokens": 0, "output_tokens": 0, "cost_usd": None}

        def suggest(self, class_id, missing_attributes, documents):
            return {
                "status": "CANDIDATES",
                "candidates": [
                    {"attribute": "ALTURA", "value": "100MM", "source_field": "description", "excerpt": "100MM"}
                ],
                "rejected": [],
            }

    target = material(catalog, "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9009")
    item = internal_report([target], [], catalog, "d", assistant=Assistant())["results"][0]
    assert item["assisted_candidates"]
    assert not item["suggestions"] and not item["evidence"]


def test_truncated_short_reference_is_not_a_contradictory_observation(catalog):
    from pipelines.internal_enrichment import observation_conflicts

    record = MaterialRecord(
        "t",
        "ATIVO",
        "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; PN LF9009XXXXXXX",
        short_description="FILTRO OLEO LUBRIFICANTE PN LF9009XXXXXXX"[:40],
    )
    target = analyze_material(record, catalog, get_classification_repository(catalog), get_extraction_repository())
    assert target.identity_key
    assert not observation_conflicts(target, catalog)
