"""Índice de busca: classe, atributos, identidade e texto normalizado de cada material.

A versão do índice reúne o PDM e os algoritmos usados. A busca recusa consultar um índice de outra
versão, porque tokens e identidades só são comparáveis quando gerados pelas mesmas regras.

O rótulo do PDM pode ficar igual com outro conteúdo, então a versão leva também o hash da planilha.
Nome de algoritmo não muda quando suas regras mudam, então cada um declara uma revisão.
Mudanças em `search_text` ou nos tokens pedem um novo `INDEX_FORMAT`.
"""

import os

from sqlalchemy import create_engine

from domain.contracts import AnalyzedMaterial, ClassificationRepository, ExtractionRepository, PdmCatalog
from pipelines.sanitize import _REDIRECT_PREFIX, _catalog, analysis_signature, analyze_material
from repositories.batch_repository import read_materials, single_tenant, write_search_index
from repositories.candidates.tokens_v1 import tokens
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.extraction import get_extraction_repository

INDEX_FORMAT = "search-index-v1"


def index_version(
    catalog: PdmCatalog,
    classifier: ClassificationRepository,
    extractor: ExtractionRepository,
    embedding_signature: str | None = None,
) -> str:
    """Assinatura comum a batch e consulta. Qualquer parte diferente torna o índice incompatível."""
    parts = [INDEX_FORMAT, analysis_signature(catalog, classifier, extractor)]
    if embedding_signature:
        parts.append(embedding_signature)
    return "|".join(parts)


def embedding_text(material: AnalyzedMaterial) -> str:
    """Texto entregue ao modelo: descrição limpa e atributos extraídos."""
    description = _REDIRECT_PREFIX.sub("", material.record.description)
    attributes = "; ".join(f"{name}: {value}" for name, value in material.attributes.items())
    return f"{description} | {attributes}" if attributes else description


def search_text(material: AnalyzedMaterial) -> str:
    """Tokens que entram no full-text: descrição, atributos extraídos e referência sem separadores."""
    values = [material.record.description, *material.attributes.values()]
    return " ".join(tokens(" ".join(values)))


def run_index(pdm_workbook: str | None = None, database_url: str | None = None) -> dict:
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Defina DATABASE_URL com a credencial batch_user")
    engine = create_engine(url)
    try:
        catalog = _catalog(pdm_workbook)
        classifier = get_classification_repository(catalog)
        extractor = get_extraction_repository()
        embedder = get_embedding_repository()
        signature = embedder.signature if embedder else None
        version = index_version(catalog, classifier, extractor, signature)
        tenant_id = single_tenant(engine)
        records = read_materials(engine, tenant_id)
        analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
        vectors = embedder.embed([embedding_text(m) for m in analyzed], query=False) if embedder else None
        rows = [
            {
                "material_id": material.record.database_id,
                "proposed_class_id": material.pdm_class_id,
                "extracted_attributes": material.attributes,
                "search_text": search_text(material),
                "candidate_identity_key": material.identity_key,
                "embedding": _vector_literal(vectors[index]) if vectors else None,
                "embedding_model": signature,
            }
            for index, material in enumerate(analyzed)
        ]
        written = write_search_index(engine, tenant_id, version, rows)
    finally:
        engine.dispose()
    return {
        "index_version": version,
        "materials": len(rows),
        "written": written,
        "embeddings": signature,
        "simulated": bool(embedder and embedder.simulated),
    }


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"
