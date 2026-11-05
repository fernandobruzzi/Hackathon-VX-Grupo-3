"""Busca sem banco: um índice exato não pode contornar a revisão de fabricante ou referência."""

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


def search(pdm, class_id, query, attributes, *, manufacturer="", reference="", description=""):
    # A chave simulada coincide até nos casos inseguros: a verificação precisa conferir a evidência.
    from domain.pdm_validator import validate_pdm

    key = validate_pdm(pdm, class_id, attributes).identity_key or partial_identity_key(
        pdm.classes[class_id], attributes
    )
    row = {
        "id": "row-1",
        "material_code": "123",
        "status": "ATIVO",
        "original_description_long": description or query,
        "pdm_description": None,
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
    assert "FABRICANTE_DIFERENTE_OU_NAO_CONFIRMADO" in result["candidates"][0]["pending_checks"]


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
