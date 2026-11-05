"""Compara algoritmos de busca nos pares que a própria base declara iguais (`USAR COD x`).

Consulta com a descrição do bloqueado e verifica em que posição aparece o código ativo indicado.
Mede duplicidades encontradas, não junções erradas.

Rodar em mcp/, com DATABASE_URL de leitura e o índice da versão correspondente já construído:
`uv run python -m vx_materials_mcp.evaluation --repository hybrid_v1`.
"""

import argparse
import json
import os
import re
import time

from sqlalchemy import create_engine, text

from domain.pdm_loader import load_pdm
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.repositories.catalog_repository import CatalogRepository
from vx_materials_mcp.repositories.search import get_search_repository
from vx_materials_mcp.repositories.search.hybrid_v1 import SearchQuery

_PREFIX = re.compile(r"^NAO UTILIZAR - USAR COD \d+\s*-\s*")
_PAIRS = text(
    """
    SELECT b.material_code AS blocked, b.original_description_long AS description, a.material_code AS target
    FROM mcp_catalog b JOIN mcp_catalog a ON a.id = b.active_code_target
    WHERE b.status = 'BLOQUEADO' AND a.status = 'ATIVO' ORDER BY b.material_code
    """
)


def evaluate(database_url: str, pdm_workbook: str, repository_name: str, limit: int = 10) -> dict:
    engine = create_engine(database_url)
    catalog = load_pdm(pdm_workbook)
    classifier = get_classification_repository(catalog)
    extractor = get_extraction_repository()
    embedder = get_embedding_repository()
    version = index_version(catalog, classifier.name, extractor.name, embedder.signature if embedder else None)
    repository = get_search_repository(
        repository_name,
        catalog=CatalogRepository(engine),
        pdm_catalog=catalog,
        classifier=classifier,
        extractor=extractor,
        index_version=version,
        caller=None,
        embedder=embedder,
    )
    with engine.connect() as connection:
        pairs = connection.execute(_PAIRS).all()
    hits = {1: 0, 5: 0, 10: 0}
    started = time.time()
    for blocked, description, target in pairs:
        result = repository.search(SearchQuery(_PREFIX.sub("", description), limit=limit + 1))
        codes = [c["material_code"] for c in result["candidates"] if c["material_code"] != blocked][:limit]
        if target in codes:
            position = codes.index(target) + 1
            for k in hits:
                hits[k] += position <= k
    engine.dispose()
    return {
        "repository": repository_name,
        "index_version": version,
        "simulated_embeddings": bool(embedder and embedder.simulated),
        "pairs": len(pairs),
        "found_at": {f"top_{k}": value for k, value in hits.items()},
        "seconds": round(time.time() - started, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara buscas nos pares declarados pela base")
    parser.add_argument("--repository", default="hybrid_v1")
    parser.add_argument("--pdm-workbook", default=os.environ.get("PDM_WORKBOOK_PATH"))
    args = parser.parse_args()
    report = evaluate(os.environ["DATABASE_URL"], args.pdm_workbook, args.repository)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
