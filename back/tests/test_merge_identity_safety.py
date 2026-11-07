"""Regressões reais da #73 e contratos de segurança para todos os candidatos registrados."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from clients.storage import LocalObjectStore
from domain.contracts import CandidateGroup, MatchType
from domain.identity import build_identity_key, material_review_reasons, partial_identity_key
from domain.pdm_loader import load_pdm
from pipelines.identity_review import identity_review_report, store_identity_review
from pipelines.measure_merge_identity import evaluate
from pipelines.sanitize import analyze_material, build_proposal, merge_proposals, read_csv_records
from repositories.candidates import REPOSITORIES, get_candidate_repository
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository

KIT = Path(__file__).parents[2] / "data/desafio01"
SAMPLE = Path(__file__).parent / "fixtures/merge_identity_review_73.json"
OILS = ("17590309", "27863373")
PARTS = ("19547027", "22125549")
REVISIONS = ("23858996", "29993231", "27417776")
# Grupos que mudaram depois da coorte congelada, revisados lendo descrição, fabricante e referência
# durante o desenvolvimento. A coorte não é reescrita: a revisão fica aqui, com o motivo.
CHANGED_GROUPS_REVIEWED = {
    # #204: os três são FILTRO AR da FRAM com referência CA94051; mesmo item pela regra 10 do PDM.
    ("10860647", "19076688", "21440355"): True,
}


@pytest.fixture(scope="module")
def context():
    catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    analyzed = [
        analyze_material(r, catalog, classifier, extractor) for r in read_csv_records(KIT / "01_base_materiais.csv")
    ]
    return catalog, {a.record.code: a for a in analyzed}


def find(repository, context, codes):
    catalog, materials = context
    return REPOSITORIES[repository]().find([materials[c] for c in codes], catalog)


@pytest.mark.parametrize("repository", sorted(REPOSITORIES))
def test_real_oils_from_different_manufacturers_never_merge(context, repository):
    _, materials = context
    assert {materials[c].record.manufacturer for c in OILS} == {"PETRONAS", "MOBIL"}
    assert materials[OILS[0]].identity_key == materials[OILS[1]].identity_key
    assert find(repository, context, OILS) == []


@pytest.mark.parametrize("repository", sorted(REPOSITORIES))
def test_real_excavator_model_never_identifies_bushing_or_idler(context, repository):
    _, materials = context
    assert {materials[c].item_name for c in PARTS} == {"BUCHA", "RODA GUIA"}
    for code in PARTS:
        assert materials[code].record.description.endswith("6030 CATERPILLAR")
        assert materials[code].attributes["MODELO EQUIPAMENTO"] == "6030"
        assert "REFERENCIA FABRICANTE" not in materials[code].attributes
        assert materials[code].identity_key is None
    assert find(repository, context, PARTS) == []


@pytest.mark.parametrize("repository", sorted(REPOSITORIES))
def test_revision_members_from_the_reviewed_sample_go_to_manual_review(context, repository):
    catalog, materials = context
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    codes = {code for item in sample["reviewed"] if "REV A" in item["note"] for code in item["codes"]}
    groups = find(repository, context, codes)
    assert not any(set(REVISIONS) & set(group.codes) for group in groups)
    report = identity_review_report([materials[code] for code in codes], catalog)
    pending = {item["evidence"]["material_code"]: item for item in report["manual_review"]}
    for code in REVISIONS:
        assert "REVISAO_DE_PECA_NAO_CONFIRMADA" in pending[code]["reasons"]
        assert materials[code].identity_key is None
        assert "REV A" in str(pending[code]["evidence"])


@pytest.mark.parametrize("reference", ["6030", "CH660", "hp300", "N123 REV A", "N123 REVISÃO A", "N123 REV. 01"])
def test_shared_identity_rules_refuse_models_even_in_explicit_reference_fields(context, reference):
    catalog, _ = context
    pdm_class = catalog.classes["PDM110"]
    attributes = {"FABRICANTE": "CATERPILLAR", "REFERENCIA FABRICANTE": reference}
    assert build_identity_key(pdm_class, "BUCHA", attributes) is None
    assert partial_identity_key(pdm_class, attributes) is None


def test_numeric_part_number_outside_model_catalog_stays_usable(context):
    catalog, _ = context
    assert partial_identity_key(
        catalog.classes["PDM110"], {"FABRICANTE": "HITACHI", "REFERENCIA FABRICANTE": "7557293"}
    )


@pytest.mark.parametrize("missing", ["FABRICANTE", "REFERENCIA FABRICANTE"])
def test_blank_reference_identity_fields_do_not_identify_a_material(context, missing):
    catalog, _ = context
    assert (
        partial_identity_key(
            catalog.classes["PDM110"], {"FABRICANTE": "METSO", "REFERENCIA FABRICANTE": "N123", missing: "  "}
        )
        is None
    )


def test_revision_marker_does_not_match_the_beginning_of_revestimento(context):
    catalog, materials = context
    material = materials["15041329"]
    assert material.item_name == "REVESTIMENTO VOLUTA"
    assert not material_review_reasons(material, catalog.classes["PDM110"])
    assert material.identity_key


@pytest.mark.parametrize("repository", sorted(REPOSITORIES))
def test_unknown_manufacturer_cannot_bridge_known_manufacturers(context, repository):
    catalog, materials = context
    first = materials[OILS[0]]
    unknown = replace(first, record=replace(first.record, code="unknown", manufacturer=""))
    normalized = replace(first, record=replace(first.record, code="same", manufacturer="  petrônas  "))
    groups = REPOSITORIES[repository]().find([first, unknown, normalized, materials[OILS[1]]], catalog)
    assert groups
    assert all(set(g.codes) == {first.record.code, "same"} for g in groups)


@pytest.mark.parametrize("codes", [OILS, PARTS, ("17947145", "29993231")])
@pytest.mark.parametrize("verified", [True, False])
def test_proposal_builder_rejects_unsafe_groups_even_from_another_algorithm(context, codes, verified):
    catalog, materials = context
    group = CandidateGroup(codes, MatchType.EXACT_IDENTITY, verified, 1.0)
    with pytest.raises(ValueError, match="MERGE recusado"):
        build_proposal(group, materials, catalog, get_normalization_repository())


def test_equivalence_is_recorded_with_originals_separately_from_applicable_proposals(context, tmp_path):
    catalog, materials = context
    report = identity_review_report([materials[c] for c in OILS], catalog)
    assert report["master_data_modified"] is False
    assert report["pdm_source_sha256"] == catalog.source_sha256
    equivalent = report["equivalence_candidates"]
    assert len(equivalent) == 1
    assert equivalent[0]["status"] == "REVIEW_REQUIRED"
    assert equivalent[0]["identity_verified"] is False
    assert {m["original_manufacturer"] for m in equivalent[0]["members"]} == {"PETRONAS", "MOBIL"}
    assert all(m["original_description"] and m["observed_version"] == 1 for m in equivalent[0]["members"])
    store = LocalObjectStore(tmp_path)
    key = store_identity_review(report, store, "tenant-test")
    assert store_identity_review(report, store, "tenant-test") == key
    assert json.loads(store.get(key)) == report
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_fixed_reviewed_cohort_eliminates_false_merges_and_explains_held_revisions(context):
    catalog, materials = context
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    analyzed = list(materials.values())
    proposals = merge_proposals(analyzed, catalog, get_candidate_repository(), get_normalization_repository())
    result = evaluate(sample, proposals, identity_review_report(analyzed, catalog))
    assert (result["baseline_groups"], result["baseline_true"], result["baseline_false"]) == (40, 38, 2)
    assert result["retained_false_groups"] == 0
    # Dois positivos históricos adicionais ficam retidos por sufixo sem confirmação.
    # Seus rótulos e os dois erros históricos permanecem no mesmo arquivo.
    # A #133 também retém 16490712/25536305: ACO ZINCADO não informa CARBONO.
    # A #204 reconhece FILT como FILTRO: 19076688 (FILT AR, FRAM, CA94051) entra no grupo revisado
    # 10860647/21440355 e o grupo ampliado deixa de ser subconjunto da coorte congelada.
    # A #263 também retém 15845002/22045268: o primeiro traz 82649616 no texto
    # e 82649616-00 na coluna; a leitura independente exige confirmar esse sufixo.
    assert result["retained_true_groups"] == 29
    assert result["retained_precision"] == 1.0
    assert [tuple(codes) for codes in result["unreviewed_changed_groups"]] == list(CHANGED_GROUPS_REVIEWED)
    removed_codes = {tuple(item["original_codes"]) for item in result["removed"]}
    assert set(OILS) in [set(codes) for codes in removed_codes]
    assert set(PARTS) in [set(codes) for codes in removed_codes]
    assert ("16490712", "25536305") in removed_codes
    assert ("15845002", "22045268") in removed_codes
    pending = {item["evidence"]["material_code"]: item for item in result["cohort_manual_review"]}
    assert set(REVISIONS) <= pending.keys()
    assert "OBSERVATION_CONFLICT:REFERENCIA FABRICANTE" in pending["15845002"]["reasons"]
    for material in materials.values():
        if material.record.code in REVISIONS:
            assert material_review_reasons(material, catalog.classes[material.pdm_class_id])
