"""Compara algoritmos de busca nos pares que a própria base declara iguais (`USAR COD x`).

Consulta com a descrição do bloqueado e verifica em que posição aparece o código ativo indicado.
Mede duplicidades encontradas, não junções erradas.

Rodar em mcp/, com DATABASE_URL de leitura e o índice da versão correspondente já construído:
`uv run python -m vx_materials_mcp.evaluation --repository hybrid_v1`.
"""

import argparse
import hashlib
import json
import math
import os
import re
import time
from statistics import median

from sqlalchemy import create_engine, text

from domain.pdm_loader import load_pdm
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.embeddings.bedrock_titan_v1 import BedrockTitanV1EmbeddingRepository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.repositories.catalog_repository import CatalogRepository
from vx_materials_mcp.repositories.search import get_search_repository
from vx_materials_mcp.repositories.search.hybrid_v1 import SearchQuery

_PREFIX = re.compile(r"^NAO UTILIZAR - USAR COD \d+\s*-\s*")
_PAIRS = text(
    """
    SELECT b.material_code AS blocked, b.original_description_long AS description, a.material_code AS target
    FROM mcp_catalog b JOIN mcp_catalog a ON a.id = b.active_code_target AND a.tenant_id = b.tenant_id
    WHERE b.tenant_id = CAST(:tenant_id AS uuid) AND b.status = 'BLOQUEADO' AND a.status = 'ATIVO'
    ORDER BY b.material_code
    """
)


def evaluate(database_url: str, pdm_workbook: str, repository_name: str, tenant_id: str, limit: int = 10) -> dict:
    engine = create_engine(database_url)
    catalog = load_pdm(pdm_workbook)
    classifier = get_classification_repository(catalog)
    extractor = get_extraction_repository()
    embedder = get_embedding_repository()
    version = index_version(catalog, classifier, extractor, embedder.signature if embedder else None)
    hits = {1: 0, 5: 0, 10: 0}
    latencies = []
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            db_catalog = CatalogRepository(connection, tenant_id)
            total, current = db_catalog.index_state(version)
            if not total or current != total:
                raise RuntimeError(f"INDEX_UPDATING: índice incompleto na versão {version} ({current}/{total})")
            repository = get_search_repository(
                repository_name,
                catalog=db_catalog,
                pdm_catalog=catalog,
                classifier=classifier,
                extractor=extractor,
                index_version=version,
                caller=None,
                embedder=embedder,
            )
            pairs = connection.execute(_PAIRS, {"tenant_id": tenant_id}).all()
            if not pairs:
                raise ValueError("Nenhum par declarado no tenant avaliado")
            cohort = hashlib.sha256(json.dumps([tuple(row) for row in pairs], ensure_ascii=False).encode()).hexdigest()
            started = time.perf_counter()
            for blocked, description, target in pairs:
                query_started = time.perf_counter()
                result = repository.search(SearchQuery(_PREFIX.sub("", description), limit=limit + 1))
                latencies.append((time.perf_counter() - query_started) * 1000)
                codes = [c["material_code"] for c in result["candidates"] if c["material_code"] != blocked][:limit]
                if target in codes:
                    position = codes.index(target) + 1
                    for k in hits:
                        hits[k] += position <= k
            seconds = time.perf_counter() - started
    finally:
        engine.dispose()
    p95 = sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1]
    return {
        "repository": repository_name,
        "index_version": version,
        "embedding_input_tokens": embedder.input_tokens
        if isinstance(embedder, BedrockTitanV1EmbeddingRepository)
        else None,
        "simulated_embeddings": bool(embedder and embedder.simulated),
        "materials": total,
        "pairs": len(pairs),
        "cohort_sha256": cohort,
        "found_at": {f"top_{k}": value for k, value in hits.items()},
        "seconds": round(seconds, 3),
        "latency_ms": {"p50": round(median(latencies), 1), "p95": round(p95, 1)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara buscas nos pares declarados pela base")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--repository", default="hybrid_v1")
    parser.add_argument("--pdm-workbook", default=os.environ.get("PDM_WORKBOOK_PATH"))
    args = parser.parse_args()
    report = evaluate(os.environ["DATABASE_URL"], args.pdm_workbook, args.repository, args.tenant_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
