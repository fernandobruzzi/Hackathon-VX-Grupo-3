"""O limite de apresentação nunca esconde uma identidade que pode ser reutilizada."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from repositories.classification import get_classification_repository
from repositories.embeddings.bedrock_titan_v1 import TitanEmbeddingError
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.chatbot.candidates import verified_existing
from vx_materials_mcp.repositories.search import get_search_repository
from vx_materials_mcp.repositories.search.hybrid_v1 import SearchQuery

ATTRIBUTES = {
    "CLASSE RESISTENCIA": "8.8",
    "ROSCA": "METRICA GROSSA",
    "BITOLA": "M12",
    "COMPRIMENTO": "50MM",
    "MATERIAL": "ACO CARBONO",
    "ACABAMENTO": "ZINCADO BRANCO",
    "NORMA": "DIN 933",
}


@pytest.fixture(scope="module")
def pdm():
    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


@pytest.mark.parametrize("repository", ["hybrid_v1", "hybrid_embeddings_v1"])
@pytest.mark.parametrize("limit", [1, 2, 5, 20])
@pytest.mark.parametrize("status", ["ATIVO", "BLOQUEADO"])
@pytest.mark.parametrize("reverse", [False, True])
def test_reusable_identity_survives_the_display_limit(pdm, repository, limit, status, reverse):
    key = validate_pdm(pdm, "PDM001", ATTRIBUTES, item_name="PARAFUSO SEXTAVADO").identity_key
    assert key
    rows = [
        {
            "id": str(i),
            "material_code": str(10000 + i),
            "status": "OBSOLETO",
            "target_code": None,
            "target_status": None,
            "target_id": None,
            "pdm_description": "PARAFUSO",
            "original_description_long": "PARAFUSO",
            "proposed_class_id": "PDM001",
            "extracted_attributes": ATTRIBUTES,
            "candidate_identity_key": key,
            "rank": 1.0,
        }
        for i in range(7)
    ]
    # Código posterior aos obsoletos; os bloqueados sem destino também não são reutilizáveis.
    rows[0]["status"] = "BLOQUEADO"
    rows[-1]["status"] = status
    if status == "BLOQUEADO":
        rows[-1].update(target_code="99999", target_status="ATIVO", target_id="target")
    if reverse:
        rows.reverse()
    catalog = SimpleNamespace(by_identity=lambda *args: rows, full_text=lambda *args: [], nearest=lambda *args: [])
    search = get_search_repository(
        repository,
        catalog=catalog,
        pdm_catalog=pdm,
        classifier=get_classification_repository(pdm),
        extractor=get_extraction_repository(),
        index_version="test",
        caller=None,
        embedder=SimpleNamespace(embed=lambda *args, **kwargs: [[0.0] * 512]),
    )
    result = search.search(SearchQuery("", "PDM001", ATTRIBUTES, limit))
    assert result["match_status"] == "EXISTING_FOUND"
    assert len(result["candidates"]) <= limit
    existing = verified_existing(result)
    assert existing is not None
    assert existing.material_code == ("99999" if status == "BLOQUEADO" else "10006")
    if status == "BLOQUEADO":
        assert "10006" in existing.reason and "99999" in existing.reason


def test_unavailable_titan_blocks_the_search_without_returning_no_match(pdm):
    def unavailable(*args, **kwargs):
        raise TitanEmbeddingError("Indisponível")

    search = get_search_repository(
        "hybrid_embeddings_v1",
        catalog=SimpleNamespace(full_text=lambda *args: []),
        pdm_catalog=pdm,
        classifier=get_classification_repository(pdm),
        extractor=get_extraction_repository(),
        index_version="test",
        caller=None,
        embedder=SimpleNamespace(embed=unavailable),
    )
    with pytest.raises(ToolError, match="INDEX_UPDATING"):
        search.search(SearchQuery("XYZ"))
