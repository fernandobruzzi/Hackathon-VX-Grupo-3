"""Contexto para chat/auditor: identidade do chamador vem do processo, nunca da ferramenta."""

from sqlalchemy import create_engine

from clients.ncm_snapshot_store import load_configured_ncm_snapshot
from domain.contracts import RagScope
from domain.ncm_snapshot import NcmSnapshotError
from domain.rag_context import build_context
from domain.runtime import check_simulated_clients
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.extraction import get_extraction_repository
from repositories.rag import get_rag_repository
from vx_materials_mcp.repositories.catalog_repository import CatalogRepository
from vx_materials_mcp.repositories.rag_repository import RagRepository
from vx_materials_mcp.repositories.resource_repository import ResourceRepository
from vx_materials_mcp.security import INVENTORY_PERMISSION


class ContextRetrieval:
    def __init__(self, catalog, database_url, caller):
        self.catalog, self.caller = catalog, caller
        self.engine = create_engine(database_url) if database_url else None

    def run(self, query: str, pdm_class_id: str | None = None, limit: int = 5) -> dict:
        ResourceRepository(self.engine, self.caller).require_read_access()
        check_simulated_clients()
        centers = self.caller.center_codes if INVENTORY_PERMISSION in self.caller.permissions else frozenset()
        embedder = get_embedding_repository() if centers else None
        version = index_version(
            self.catalog,
            get_classification_repository(self.catalog),
            get_extraction_repository(),
            embedder.signature if embedder else None,
        )
        try:
            snapshot = load_configured_ncm_snapshot()
        except NcmSnapshotError:
            snapshot = None
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            with connection.begin():
                if centers:
                    CatalogRepository(connection, self.caller.tenant_id).indexed(version)
                repository = get_rag_repository(
                    source=RagRepository(connection, self.caller, version), embedder=embedder
                )
                return build_context(
                    self.catalog,
                    repository,
                    RagScope(self.caller.tenant_id, centers),
                    query,
                    class_id=pdm_class_id,
                    snapshot=snapshot,
                    limit=limit,
                )
