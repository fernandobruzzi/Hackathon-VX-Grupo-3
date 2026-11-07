"""Política do batch para propor NCM: mais restrita que a coerência do PDM, nunca mais solta.

A coerência (`check_ncm_consistency`) segue o PDM ao pé da letra e continua igual para chat e
aprovação. Propor exige a matéria provada e deixa anéis/vedações de sobressalente para revisão.
"""

from pathlib import Path

import pytest

from domain.contracts import MaterialRecord
from domain.ncm_rules import check_ncm_consistency, ncm_proposal_blockers
from domain.pdm_loader import load_pdm
from pipelines.ncm_corrections import propose_ncm_corrections
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository

KIT = Path(__file__).parents[2] / "data/desafio01"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


def analyze(catalog, description, ncm="", status="ATIVO"):
    record = MaterialRecord("x", status, description, unit="PC", ncm=ncm)
    classifier = get_classification_repository(catalog, "aliases_v2")
    return analyze_material(record, catalog, classifier, get_extraction_repository())


@pytest.mark.parametrize(
    ("attributes", "blocked"),
    [
        ({}, True),
        ({"MATERIAL": "ACO CARBONO"}, False),
        # Classe de resistência de fixador só existe para aço (ISO 898-1, SAE J429, ISO 3506).
        ({"CLASSE RESISTENCIA": "8.8"}, False),
        ({"CLASSE RESISTENCIA": "SAE GRAU 5"}, False),
        # Valor fora do PDM não prova a matéria.
        ({"MATERIAL": "LATAO"}, True),
    ],
)
def test_unique_code_requires_admitted_matter(catalog, attributes, blocked):
    reasons = ncm_proposal_blockers(catalog.classes["PDM001"], attributes, "PARAFUSO SEXTAVADO")
    assert ("NCM_MATTER_UNPROVEN" in reasons) is blocked
    # A coerência literal do PDM não muda: o código único continua coerente.
    assert check_ncm_consistency(catalog, "PDM001", attributes, "7318.15.00").technical_consistency == "CONSISTENT"


@pytest.mark.parametrize(
    ("item", "blocked"),
    [("ANEL DESGASTE", True), ("ANEL EXPULSOR", True), ("VEDACAO EIXO", True), ("BUCHA", False)],
)
def test_spare_part_rings_and_seals_go_to_manual_review(catalog, item, blocked):
    attributes = {"APLICACAO": "BOMBA CENTRIFUGA"}
    assert ("NCM_SEAL_FUNCTION_UNRESOLVED" in ncm_proposal_blockers(catalog.classes["PDM110"], attributes, item)) is (
        blocked
    )


def test_abbreviated_bolt_with_grade_gets_ncm_even_with_incomplete_pdm(catalog):
    # Sem bitola e sem acabamento no PDM, mas o código da classe é único e 8.8 prova o aço.
    material = analyze(catalog, "PARAF CAB SEXTAVADA, ROSCA:MA, COMP:90MM, 8.8, DIN 933", ncm="7318.19.00")
    assert material.pdm_class_id == "PDM001"
    proposals = propose_ncm_corrections([material], catalog)
    assert [p.changeset["after"]["ncm"] for p in proposals] == ["7318.15.00"]
    assert proposals[0].fiscal_review_required
    assert "ncm-proposal-v1" in proposals[0].changeset["changes"][0]["source"]


def test_bolt_without_matter_is_not_proposed(catalog):
    # Real do benchmark: sem material e sem classe de resistência, a posição 7318 não está provada.
    material = analyze(catalog, "PARAFUSO SEXTAVADO;ROSCA:ROSCA GROSSA;BITOLA:M30;COMP:140MM;TRATAMENTO:ZINCADO BRANCO")
    assert material.pdm_class_id == "PDM001"
    assert propose_ncm_corrections([material], catalog) == []


def test_o_ring_without_elastomer_is_not_proposed(catalog):
    material = analyze(catalog, "ANEL O-RING 25X2,5 70 SHORE A", ncm="8484.90.00")
    assert material.pdm_class_id == "PDM031"
    assert propose_ncm_corrections([material], catalog) == []
