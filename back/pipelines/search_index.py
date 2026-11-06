"""Índice de busca: classe, atributos, identidade e texto normalizado de cada material.

A versão do índice reúne o PDM e os algoritmos usados. A busca recusa consultar um índice de outra
versão, porque tokens e identidades só são comparáveis quando gerados pelas mesmas regras.

O rótulo do PDM pode ficar igual com outro conteúdo, então a versão leva também o hash da planilha.
Nome de algoritmo não muda quando suas regras mudam, então cada um declara uma revisão.
Mudanças em `search_text` ou nos tokens pedem um novo `INDEX_FORMAT`.
"""

import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from sqlalchemy import create_engine, text

from domain.contracts import AnalyzedMaterial, ClassificationRepository, ExtractionRepository, PdmCatalog
from domain.identity import partial_identity_key
from domain.pdm_validator import validate_pdm
from pipelines.sanitize import _REDIRECT_PREFIX, _catalog, analysis_signature, analyze_material
from repositories.batch_repository import (
    SearchSource,
    index_coverage,
    read_search_sources,
    single_tenant,
    write_search_index,
)
from repositories.candidates.tokens_v1 import tokens
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.extraction import get_extraction_repository

INDEX_FORMAT = "search-index-v2"


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


def analyze_source(source: SearchSource, catalog, classifier, extractor) -> AnalyzedMaterial:
    """Atributos aprovados prevalecem sobre qualquer interpretação extraída do texto original."""
    analyzed = analyze_material(source.record, catalog, classifier, extractor)
    if source.approved_class_id is None and not source.approved_attributes:
        return analyzed
    class_id = source.approved_class_id or analyzed.pdm_class_id
    if class_id not in catalog.classes:
        return replace(analyzed, pdm_class_id=None, identity_key=None)
    cls = catalog.classes[class_id]
    # Uma classe aprovada diferente também muda quais atributos podem ser extraídos.
    if class_id != analyzed.pdm_class_id:
        extracted = extractor.extract(cls, source.record.description)
        attributes = {name: value.value for name, value in extracted.attributes.items()}
    else:
        attributes = dict(analyzed.attributes)
    for name, value in source.approved_attributes.items():
        if value is None:
            attributes.pop(name, None)
        else:
            attributes[name] = value
    item = next(
        (name for name in sorted(cls.item_names, key=len, reverse=True) if source.record.description.startswith(name)),
        analyzed.item_name,
    )
    if item not in cls.item_names:
        item = cls.item_names[0] if len(cls.item_names) == 1 else None
    validation = validate_pdm(catalog, class_id, attributes, item_name=item)
    identity = validation.identity_key or partial_identity_key(cls, attributes)
    return AnalyzedMaterial(source.record, class_id, item, attributes, identity)


@contextmanager
def _index_lock(engine, tenant_id, *, wait=False):
    with engine.connect() as lease:
        key = {"key": f"search-index:{tenant_id}"}
        if wait:
            lease.execute(text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"), key)
            locked = True
        else:
            locked = lease.scalar(text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), key)
        try:
            yield locked
        finally:
            if locked:
                lease.execute(text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), key)


def run_index(pdm_workbook: str | None = None, database_url: str | None = None, *, if_stale: bool = False) -> dict:
    """Reconstrói o índice da versão atual.

    Com `if_stale`, só reanalisa fontes ausentes ou cuja revisão mudou. Valores aprovados
    prevalecem sobre extrações sugeridas; originais permanecem preservados na master.
    """
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
        with _index_lock(engine, tenant_id, wait=not if_stale) as locked:
            if not locked:
                return {"written": 0, "busy": True, "index_version": version}
            materials, indexed = index_coverage(engine, tenant_id, version)
            if if_stale:
                if materials and indexed == materials:
                    return {
                        "index_version": version,
                        "materials": materials,
                        "written": 0,
                        "skipped": "índice já está na versão atual",
                        "embeddings": signature,
                        "simulated": bool(embedder and embedder.simulated),
                    }
            sources = read_search_sources(engine, tenant_id, version, only_stale=if_stale)
            analyzed = [analyze_source(source, catalog, classifier, extractor) for source in sources]
            vectors = embedder.embed([embedding_text(m) for m in analyzed], query=False) if embedder else None
            rows = [
                {
                    "material_id": material.record.database_id,
                    "source_version": material.record.version,
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
            materials, indexed = index_coverage(engine, tenant_id, version)
    finally:
        engine.dispose()
    return {
        "index_version": version,
        "materials": materials,
        "written": written,
        "pending": materials - indexed,
        "embeddings": signature,
        "simulated": bool(embedder and embedder.simulated),
    }


def watch_index(pdm_workbook=None, *, poll_seconds=2):
    """Mantém o serviço index existente atualizado; falhas ficam visíveis e são retomadas no próximo ciclo."""
    if not 1 <= poll_seconds <= 60:
        raise ValueError("O intervalo de indexação deve ficar entre 1 e 60 segundos")
    ready = Path("/tmp/vx-index-ready")
    ready.unlink(missing_ok=True)
    while True:
        try:
            result = run_index(pdm_workbook, if_stale=True)
            if not result.get("busy") and not result.get("pending"):
                ready.touch()
            if result.get("written") or result.get("pending"):
                print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as error:
            ready.unlink(missing_ok=True)
            print(
                f"INDEX_REFRESH_FAILED ({type(error).__name__}): nova tentativa no próximo ciclo",
                file=sys.stderr,
                flush=True,
            )
        time.sleep(poll_seconds)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"
