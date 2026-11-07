"""Busca sem banco: um índice exato não pode contornar a revisão de fabricante ou referência."""

import csv
from pathlib import Path

import pytest

from domain.identity import partial_identity_key
from domain.pdm_loader import load_pdm
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.repositories.search.hybrid_v1 import HybridV1SearchRepository, SearchQuery

KIT = Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx"


class Catalog:
    def __init__(self, row):
        self.row = row

    def by_identity(self, key, version):
        return [self.row]

    def full_text(self, *args):
        return [self.row]


@pytest.fixture(scope="module")
def pdm():
    return load_pdm(KIT)


def search(
    pdm,
    class_id,
    query,
    attributes,
    *,
    manufacturer="",
    reference="",
    description="",
    candidate_item=None,
    current_description=None,
    approved_attributes=None,
):
    # A chave simulada coincide até nos casos inseguros: a verificação precisa conferir a evidência.
    from domain.pdm_validator import validate_pdm

    key = validate_pdm(pdm, class_id, attributes, item_name=candidate_item).identity_key or partial_identity_key(
        pdm.classes[class_id], attributes
    )
    row = {
        "id": "row-1",
        "material_code": "123",
        "status": "ATIVO",
        "original_description_long": description or query,
        "pdm_description": current_description,
        "approved_class_id": class_id if approved_attributes is not None else None,
        "approved_attributes": approved_attributes,
        "manufacturer": manufacturer,
        "manufacturer_reference": reference,
        "candidate_identity_key": key,
        "proposed_class_id": class_id,
        "extracted_attributes": attributes,
        "rank": 1.0,
    }
    repository = HybridV1SearchRepository(
        Catalog(row), pdm, get_classification_repository(pdm), get_extraction_repository(), "test-version", None
    )
    return repository.search(SearchQuery(query, class_id, attributes))


def test_unknown_manufacturer_is_not_treated_as_the_same_as_a_named_oil(pdm):
    attributes = {"APLICACAO": "MOTOR DIESEL", "VISCOSIDADE": "SAE 5W40", "EMBALAGEM": "CONTAINER 1000L"}
    result = search(pdm, "PDM090", "OLEO LUBRIFICANTE", attributes, manufacturer="MOBIL")
    assert result["match_status"] == "REVIEW_REQUIRED"
    assert result["candidates"][0]["identity_verified"] is False
    assert "FABRICANTE_NAO_CONFIRMADO" in result["candidates"][0]["pending_checks"]


def test_an_unambiguous_reference_still_finds_the_existing_filter(pdm):
    attributes = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009"}
    result = search(
        pdm, "PDM100", "filtro Fleetguard LF9009", attributes, manufacturer="FLEETGUARD", reference="LF9009"
    )
    assert result["match_status"] == "EXISTING_FOUND"
    assert result["candidates"][0]["identity_verified"] is True


@pytest.mark.parametrize("revision_in", ["query", "candidate_reference", "candidate_description"])
def test_revision_requires_review_even_when_a_stale_index_key_matches(pdm, revision_in):
    attributes = {"FABRICANTE": "METSO", "REFERENCIA FABRICANTE": "N1234567"}
    result = search(
        pdm,
        "PDM110",
        "MANTO METSO N1234567" + (" REV A" if revision_in == "query" else ""),
        attributes,
        manufacturer="METSO",
        reference="N1234567" + (" REV A" if revision_in == "candidate_reference" else ""),
        description="MANTO METSO N1234567" + (" REV A" if revision_in == "candidate_description" else ""),
    )
    assert result["match_status"] == "REVIEW_REQUIRED"
    assert result["candidates"][0]["identity_verified"] is False
    assert "REVISAO_DE_PECA_NAO_CONFIRMADA" in result["candidates"][0]["pending_checks"]


def test_real_sulzer_covers_with_equal_pn_and_different_nouns_require_review(pdm):
    with (KIT.parent / "01_base_materiais.csv").open(encoding="utf-8-sig") as stream:
        records = {
            r["CODIGO_MATERIAL"]: r for r in csv.DictReader(stream) if r["CODIGO_MATERIAL"] in {"25187467", "21290535"}
        }
    requested, candidate = records["25187467"], records["21290535"]
    attributes = {
        name: item.value
        for name, item in get_extraction_repository()
        .extract(pdm.classes["PDM110"], requested["DESCRICAO_LONGA"])
        .attributes.items()
    }
    result = search(
        pdm,
        "PDM110",
        requested["DESCRICAO_LONGA"],
        attributes,
        manufacturer=candidate["FABRICANTE"],
        reference=candidate["REFERENCIA_FABRICANTE"],
        description=candidate["DESCRICAO_LONGA"],
    )
    item = result["candidates"][0]
    assert item["identity_verified"] is False
    assert result["match_status"] == "REVIEW_REQUIRED"
    assert item["pending_checks"]


def test_identical_niple_is_verified_when_the_query_names_the_item(pdm):
    attributes = {
        "DIAMETRO NOMINAL": "1/2POL",
        "CLASSE PRESSAO": "6000#",
        "MATERIAL": "ACO CARBONO FORJADO A105",
        "CONEXAO": "ROSCA NPT",
    }
    result = search(pdm, "PDM050", "NIPLE", attributes, candidate_item="NIPLE")
    assert result["match_status"] == "EXISTING_FOUND"
    assert result["candidates"][0]["identity_verified"] is True


def test_stale_index_does_not_hide_a_known_current_dimension_conflict(pdm):
    attributes = {
        "ROSCA": "METRICA GROSSA",
        "BITOLA": "M12",
        "COMPRIMENTO": "50MM",
        "MATERIAL": "ACO CARBONO",
        "CLASSE RESISTENCIA": "8.8",
        "ACABAMENTO": "ZINCADO BRANCO",
        "NORMA": "DIN 933",
    }
    result = search(
        pdm,
        "PDM001",
        "PARAFUSO SEXTAVADO M12X50",
        attributes,
        description="PARAFUSO SEXTAVADO M16X50",
        candidate_item="PARAFUSO SEXTAVADO",
    )
    assert result["candidates"][0]["identity_verified"] is False
    assert "BITOLA" in result["candidates"][0]["conflicts"]


def test_requested_class_does_not_override_a_contradictory_current_noun(pdm):
    attributes = {
        "ROSCA": "METRICA GROSSA",
        "BITOLA": "M12",
        "COMPRIMENTO": "50MM",
        "MATERIAL": "ACO CARBONO",
        "CLASSE RESISTENCIA": "8.8",
        "ACABAMENTO": "ZINCADO BRANCO",
        "NORMA": "DIN 933",
    }
    result = search(
        pdm,
        "PDM001",
        "ARRUELA LISA",
        attributes,
        description="PARAFUSO SEXTAVADO M12X50",
        candidate_item="PARAFUSO SEXTAVADO",
    )
    assert result["candidates"][0]["identity_verified"] is False
    assert "CLASSES_DIFERENTES" in result["candidates"][0]["pending_checks"]


def test_structured_reference_cannot_hide_a_contradictory_original_pn(pdm):
    attributes = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009"}
    result = search(
        pdm,
        "PDM100",
        "filtro Fleetguard LF9009",
        attributes,
        manufacturer="FLEETGUARD",
        reference="LF9009",
        description="FILTRO FLEETGUARD LF9999",
    )
    assert result["candidates"][0]["identity_verified"] is False
    assert result["match_status"] == "REVIEW_REQUIRED"
    assert result["candidates"][0]["pending_checks"]


@pytest.mark.parametrize("ambiguous_side", ["query", "candidate"])
def test_explicitly_ambiguous_names_are_not_generic_missing_names(pdm, ambiguous_side):
    attributes = {"FABRICANTE": "METSO", "REFERENCIA FABRICANTE": "N1234567"}
    generic, ambiguous = "METSO N1234567", "MANTO EIXO METSO N1234567"
    result = search(
        pdm,
        "PDM110",
        ambiguous if ambiguous_side == "query" else generic,
        attributes,
        manufacturer="METSO",
        reference="N1234567",
        description=ambiguous if ambiguous_side == "candidate" else generic,
    )
    candidate = result["candidates"][0]
    assert candidate["identity_verified"] is False
    assert "SUBSTANTIVO_AMBIGUO" in candidate["pending_checks"]
    assert result["match_status"] == "REVIEW_REQUIRED"


def test_current_approved_noun_and_attributes_precede_original_inference(pdm):
    attributes = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9999"}
    result = search(
        pdm,
        "PDM100",
        "FILTRO COMBUSTIVEL FLEETGUARD LF9999",
        attributes,
        manufacturer="FLEETGUARD",
        reference="LF9999",
        description="FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009",
        current_description="FILTRO COMBUSTIVEL; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9999",
        approved_attributes=attributes,
    )
    assert result["candidates"][0]["identity_verified"]
    assert result["match_status"] == "EXISTING_FOUND"


def test_original_revision_evidence_is_kept_with_approved_current_values(pdm):
    attributes = {"FABRICANTE": "METSO", "REFERENCIA FABRICANTE": "N1234567"}
    result = search(
        pdm,
        "PDM110",
        "MANTO METSO N1234567",
        attributes,
        manufacturer="METSO",
        reference="N1234567",
        description="MANTO METSO N1234567 REV A",
        current_description="MANTO; FABRICANTE: METSO; REFERENCIA FABRICANTE: N1234567",
        approved_attributes=attributes,
    )
    candidate = result["candidates"][0]
    assert not candidate["identity_verified"]
    assert "REVISAO_DE_PECA_NAO_CONFIRMADA" in candidate["pending_checks"]


def test_approved_values_do_not_hide_a_current_structured_reference_conflict(pdm):
    attributes = {"FABRICANTE": "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9999"}
    result = search(
        pdm,
        "PDM100",
        "FILTRO COMBUSTIVEL FLEETGUARD LF9999",
        attributes,
        manufacturer="FLEETGUARD",
        reference="LF9009",
        description="FILTRO FLEETGUARD LF9009",
        current_description="FILTRO COMBUSTIVEL; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9999",
        approved_attributes=attributes,
    )
    candidate = result["candidates"][0]
    assert not candidate["identity_verified"]
    assert "REFERENCIA_CONFLITANTE" in candidate["pending_checks"]
