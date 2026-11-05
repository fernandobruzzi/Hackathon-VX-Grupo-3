"""Índice de busca: classe, atributos, identidade e texto normalizado de cada material.

A versão do índice reúne os algoritmos usados. A busca recusa consultar um índice de outra versão,
porque tokens e identidades só são comparáveis quando gerados pelas mesmas regras.
"""

import os

from sqlalchemy import create_engine

from domain.contracts import AnalyzedMaterial, PdmCatalog
from pipelines.sanitize import _catalog, analyze_material
from repositories.batch_repository import read_materials, single_tenant, write_search_index
from repositories.candidates.tokens_v1 import tokens
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository

INDEX_FORMAT = "search-index-v1"


def index_version(catalog: PdmCatalog, classifier_name: str, extractor_name: str) -> str:
    return f"{INDEX_FORMAT}|{catalog.version}|{classifier_name}|{extractor_name}"


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
        version = index_version(catalog, classifier.name, extractor.name)
        tenant_id = single_tenant(engine)
        records = read_materials(engine, tenant_id)
        analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
        rows = [
            {
                "material_id": material.record.database_id,
                "proposed_class_id": material.pdm_class_id,
                "extracted_attributes": material.attributes,
                "search_text": search_text(material),
                "candidate_identity_key": material.identity_key,
            }
            for material in analyzed
        ]
        written = write_search_index(engine, tenant_id, version, rows)
    finally:
        engine.dispose()
    return {"index_version": version, "materials": len(rows), "written": written}
