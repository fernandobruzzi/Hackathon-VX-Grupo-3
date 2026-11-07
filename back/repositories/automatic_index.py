"""Reindexação recuperável usando as mesmas fontes, revisão e travas do indexador contínuo."""

from sqlalchemy import bindparam, create_engine, text

from pipelines.search_index import (
    _index_lock,
    _vector_literal,
    analyze_source,
    embedding_text,
    index_version,
    search_text,
)
from repositories.batch_repository import read_search_sources, write_search_index
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.extraction import get_extraction_repository


def refresh_automatic_materials(database_url: str, tenant_id: str, material_ids: list[str], catalog) -> dict:
    engine = create_engine(database_url)
    wanted = set(material_ids)
    try:
        classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
        embedder = get_embedding_repository()
        version = index_version(catalog, classifier, extractor, embedder.signature if embedder else None)
        query = text("""SELECT m.id, i.source_version, m.version FROM materials_master m
            LEFT JOIN material_search_index i ON i.material_id=m.id AND i.tenant_id=m.tenant_id
              AND i.normalization_version=:version
            WHERE m.tenant_id=CAST(:tenant AS uuid) AND m.id::text IN :ids""").bindparams(
            bindparam("ids", expanding=True)
        )
        with _index_lock(engine, tenant_id, wait=True):
            with engine.connect() as connection:
                if len(
                    connection.execute(query, {"tenant": tenant_id, "ids": material_ids, "version": version}).all()
                ) != len(wanted):
                    raise ValueError("INDEX_MATERIAL_OUT_OF_SCOPE")
            # O indexador contínuo pode já ter concluído estes materiais; não repete fontes atuais.
            sources = [
                source
                for source in read_search_sources(engine, tenant_id, version, only_stale=True)
                if source.record.database_id in wanted
            ]
            analyzed = [analyze_source(source, catalog, classifier, extractor) for source in sources]
            vectors = embedder.embed([embedding_text(item) for item in analyzed], query=False) if embedder else None
            rows = [
                {
                    "material_id": item.record.database_id,
                    "source_version": item.record.version,
                    "proposed_class_id": item.pdm_class_id,
                    "extracted_attributes": item.attributes,
                    "search_text": search_text(item),
                    "candidate_identity_key": item.identity_key,
                    "embedding": _vector_literal(vectors[index]) if vectors else None,
                    "embedding_model": embedder.signature if embedder else None,
                }
                for index, item in enumerate(analyzed)
            ]
            written = write_search_index(engine, tenant_id, version, rows)
            with engine.connect() as connection:
                current = connection.execute(
                    query, {"tenant": tenant_id, "ids": material_ids, "version": version}
                ).all()
                if any(row.source_version != row.version for row in current) or len(current) != len(wanted):
                    raise ValueError("INDEX_SOURCE_CHANGED")
        return {"index_version": version, "materials": len(wanted), "written": written}
    finally:
        engine.dispose()
