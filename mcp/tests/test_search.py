"""search_similar_materials de ponta a ponta: banco real, índice do batch e protocolo MCP."""

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from pipelines.search_index import run_index
from vx_materials_mcp.chatbot.mcp_client import McpToolError, connect

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")
CENTERS = ["1100", "1200", "1300", "2100", "2200", "9000"]
REQUESTER = {"user_id": "u1", "permissions": ["inventory:read"], "center_codes": CENTERS}
FISCAL = {**REQUESTER, "permissions": ["inventory:read", "metrics:financial"]}


def search(database, caller=None, **arguments):
    async def run():
        identity = json.dumps(caller) if caller else None
        async with connect(PDM, database["reader"], identity) as client:
            return await client.call_tool("search_similar_materials", arguments)

    return asyncio.run(run())


def first_code(database, query):
    with database["admin"].connect() as connection:
        return connection.execute(text(query)).one()


def test_index_covers_the_whole_base(database):
    assert database["indexed"]["materials"] == 23554
    assert database["indexed"]["index_version"].startswith("search-index-v1|pdm-kit-v1|")


def test_briefing_filter_request_finds_the_existing_item(database):
    result = search(database, REQUESTER, query="filtro Fleetguard LF 9009")
    assert result["match_status"] == "EXISTING_FOUND"
    top = result["candidates"][0]
    assert top["material_code"] == "16031971"
    assert top["identity_verified"] is True
    assert top["match_type"] == "EXACT_MANUFACTURER_REFERENCE"
    assert top["inventory"]
    assert "unit_price" not in top["inventory"][0] or top["inventory"][0]["unit_price"] is None


def test_blocked_item_points_to_its_active_code(database):
    blocked, target, description = first_code(
        database,
        "SELECT m.material_code, t.material_code, m.original_description_long FROM materials_master m "
        "JOIN materials_master t ON t.id = m.active_code_target ORDER BY m.material_code LIMIT 1",
    )
    result = search(database, REQUESTER, query=description.split(" - ", 2)[-1], limit=20)
    found = next(c for c in result["candidates"] if c["material_code"] == blocked)
    assert found["status"] == "BLOQUEADO"
    assert found["active_code_target"] == target


def test_obsolete_item_is_never_offered_for_reuse(database):
    (code, description) = first_code(
        database,
        "SELECT material_code, original_description_long FROM materials_master WHERE status = 'OBSOLETO' "
        "AND original_description_long LIKE 'FILTRO%' ORDER BY material_code LIMIT 1",
    )
    result = search(database, REQUESTER, query=description, limit=20)
    found = next(c for c in result["candidates"] if c["material_code"] == code)
    assert "OBSOLETO_NAO_REUTILIZAR" in found["pending_checks"]
    assert found["active_code_target"] is None


def test_ranking_score_does_not_authorize_a_merge(database):
    result = search(database, REQUESTER, query="parafuso sextavado M12")
    assert result["candidates"]
    assert result["match_status"] == "REVIEW_REQUIRED"
    for candidate in result["candidates"]:
        assert candidate["identity_verified"] is False
        assert candidate["match_type"] == "TEXT_SIMILARITY"
        assert candidate["ranking_score"] < 1.0


@pytest.mark.parametrize(
    ("caller", "has_stock", "has_prices"),
    [(None, False, False), (REQUESTER, True, False), (FISCAL, True, True)],
)
def test_stock_respects_caller_permissions(database, caller, has_stock, has_prices):
    top = search(database, caller, query="filtro Fleetguard LF 9009")["candidates"][0]
    assert bool(top["inventory"]) is has_stock
    assert any(item.get("unit_price") for item in top["inventory"]) is has_prices
    if caller is None:
        assert "ESTOQUE_NAO_AUTORIZADO" in top["pending_checks"]


def test_stock_only_from_the_callers_centers(database):
    outside = {**REQUESTER, "center_codes": ["9999"]}
    assert search(database, outside, query="filtro Fleetguard LF 9009")["candidates"][0]["inventory"] == []


def test_query_and_index_must_share_the_same_version(database):
    with database["admin"].begin() as connection:
        connection.execute(text("UPDATE material_search_index SET normalization_version = 'versao-antiga'"))
    try:
        with pytest.raises(McpToolError, match="versao"):
            search(database, REQUESTER, query="filtro Fleetguard LF 9009")
    finally:
        with database["admin"].begin() as connection:
            connection.execute(
                text("UPDATE material_search_index SET normalization_version = :v"),
                {"v": database["indexed"]["index_version"]},
            )


def test_embedding_search_needs_an_index_with_the_same_signature(database, monkeypatch):
    """Índice sem embeddings não serve para consulta com embeddings: modelo, dimensão e versão precisam casar."""
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "simulated_v1")
    monkeypatch.setenv("SEARCH_REPOSITORY", "hybrid_embeddings_v1")
    with pytest.raises(McpToolError, match="simulated_v1:hashing-trigrams-v1:512"):
        search(database, REQUESTER, query="filtro Fleetguard LF 9009")


def test_embedding_search_finds_the_existing_item(database, monkeypatch):
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "simulated_v1")
    run_index(PDM, database_url=database["batch"])
    monkeypatch.setenv("SEARCH_REPOSITORY", "hybrid_embeddings_v1")
    result = search(database, REQUESTER, query="filtro Fleetguard LF 9009")
    assert result["index_version"].endswith("simulated_v1:hashing-trigrams-v1:512")
    assert result["candidates"][0]["material_code"] == "16031971"
    assert result["candidates"][0]["identity_verified"] is True
    assert all(c["ranking_score"] < 1.0 for c in result["candidates"] if not c["identity_verified"])
