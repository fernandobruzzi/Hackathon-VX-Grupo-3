"""Decisões de identidade conservam dúvida e não equiparam similaridade à peça."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from domain import identity
from domain.contracts import AnalyzedMaterial, MaterialRecord
from domain.identity_decision import decide_identity
from domain.pdm_loader import load_pdm
from pipelines.full_run import _decode, _encode
from pipelines.identity_review import identity_review_report
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository

KIT = Path(__file__).parents[2] / "data/desafio01"


@pytest.fixture(scope="module")
def context():
    catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    codes = {"25187467", "21290535", "17590309", "27863373", "19547027", "22125549", "23858996"}
    materials = {
        r.code: analyze_material(r, catalog, classifier, extractor)
        for r in read_csv_records(KIT / "01_base_materiais.csv")
        if r.code in codes
    }
    return catalog, materials


def test_real_tampas_with_matching_pn_require_review(context):
    catalog, materials = context
    left, right = (materials[c] for c in ("25187467", "21290535"))
    assert left.identity_key == right.identity_key
    result = decide_identity(catalog, left, right)
    assert result.status == "REVIEW_REQUIRED"
    assert "SUBSTANTIVO_CONTRADIZ_REFERENCIA" in result.reasons


def test_real_tampas_have_actionable_review_evidence(context):
    catalog, materials = context
    tampas = [materials[c] for c in ("25187467", "21290535")]
    pending = identity_review_report(tampas, catalog)["manual_review"]
    assert {row["evidence"]["material_code"] for row in pending} == {"25187467", "21290535"}
    assert all("SUBSTANTIVO_CONTRADIZ_REFERENCIA" in row["reasons"] for row in pending)


def test_real_manufacturers_remain_separate(context):
    catalog, materials = context
    left, right = (materials[c] for c in ("17590309", "27863373"))
    result = decide_identity(catalog, left, right)
    assert result.status == "DIFFERENT_MATERIAL"
    assert "FABRICANTES_DIFERENTES" in result.reasons


@pytest.mark.parametrize("code", ["19547027", "22125549", "23858996"])
def test_model_or_unconfirmed_revision_cannot_identify_even_an_identical_copy(context, code):
    catalog, materials = context
    material = materials[code]
    result = decide_identity(catalog, material, material)
    assert result.status == "REVIEW_REQUIRED"
    assert result.reasons


def filter_material(name=None, reference="LF9009"):
    attributes = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": reference}
    return AnalyzedMaterial(
        MaterialRecord("filter", "ATIVO", "FILTRO FLEETGUARD " + reference, manufacturer="FLEETGUARD"),
        "PDM100",
        name,
        attributes,
        "PDM100|FLEETGUARD|LF9009",
    )


def test_genuine_reference_preserves_known_spelling_variants(context):
    catalog, _ = context
    result = decide_identity(catalog, filter_material(), filter_material(reference="LF 9009"))
    assert result.status == "SAME_MATERIAL"
    assert result.reasons == ()


def test_unconfirmed_suffix_is_not_a_spelling_variant(context):
    catalog, _ = context
    result = decide_identity(catalog, filter_material(), filter_material(reference="LF9009-00"))
    assert result.status == "REVIEW_REQUIRED"
    assert "SUFIXO_REFERENCIA_NAO_CONFIRMADO" in result.reasons


def test_original_suffix_cannot_be_hidden_by_the_interpretation(context):
    catalog, _ = context
    left = filter_material()
    right = replace(left, record=replace(left.record, reference="LF9009-00"))
    assert decide_identity(catalog, left, right).status == "REVIEW_REQUIRED"


def test_original_reference_cannot_be_replaced_by_an_index_key(context):
    catalog, _ = context
    left = filter_material()
    right = replace(left, record=replace(left.record, reference="LF9999"))
    result = decide_identity(catalog, left, right)
    assert result.status == "REVIEW_REQUIRED"
    assert "REFERENCIA_CONFLITANTE" in result.reasons


def test_disjoint_names_do_not_choose_a_piece_arbitrarily(context):
    catalog, _ = context
    assert identity.resolve_item_name(catalog.classes["PDM050"], ["NIPLE", "COTOVELO 90 GRAUS"]) is None
    assert identity.resolve_item_name(catalog.classes["PDM110"], ["TAMPA", "TAMPA PRESSAO"]) == "TAMPA PRESSAO"


def test_missing_noun_does_not_bridge_distinct_known_pieces(context):
    catalog, _ = context
    result = decide_identity(catalog, filter_material(), filter_material("FILTRO AR"))
    assert result.status == "REVIEW_REQUIRED"
    assert "SUBSTANTIVO_NAO_CONFIRMADO" in result.reasons


def test_matching_stale_index_key_does_not_override_conflicting_attributes(context):
    catalog, _ = context
    left = filter_material()
    right = replace(
        left, attributes=left.attributes | {"FABRICANTE": "FRAM"}, record=replace(left.record, manufacturer="FRAM")
    )
    assert decide_identity(catalog, left, right).status != "SAME_MATERIAL"


def test_noun_is_part_of_shared_signature():
    attributes = {"DIAMETRO NOMINAL": "2POL"}
    assert identity.identity_signature("PDM050", "NIPLE", attributes) != identity.identity_signature(
        "PDM050", "COTOVELO 90 GRAUS", attributes
    )


def test_checkpoint_keeps_explicit_ambiguity(context):
    catalog, _ = context
    material = replace(filter_material(), review_reasons=("SUBSTANTIVO_AMBIGUO",))
    restored = _decode(json.loads(json.dumps(_encode(material))))
    result = decide_identity(catalog, restored, restored)
    assert result.status == "REVIEW_REQUIRED"
    assert "SUBSTANTIVO_AMBIGUO" in result.reasons
