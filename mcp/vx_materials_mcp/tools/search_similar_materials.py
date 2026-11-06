"""Tool search_similar_materials: conecta o servidor ao banco e ao algoritmo de busca escolhido."""

from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import create_engine

from domain.contracts import PdmCatalog
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.embeddings import get_embedding_repository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.repositories.catalog_repository import CatalogRepository
from vx_materials_mcp.repositories.search import get_search_repository
from vx_materials_mcp.repositories.search.hybrid_v1 import SearchQuery
from vx_materials_mcp.schemas.tools import SimilarMaterials
from vx_materials_mcp.security import Caller


class SimilarMaterialsSearch:
    def __init__(self, pdm_catalog: PdmCatalog, database_url: str | None, caller: Caller | None) -> None:
        self._pdm = pdm_catalog
        self._caller = caller
        self._engine = create_engine(database_url) if database_url else None

    def _ready(self, connection=None):
        if self._caller is None:
            raise ToolError("Tenant autenticado ausente")
        if self._engine is None:
            raise ToolError("Catalogo indisponivel: defina DATABASE_URL com a credencial mcp_reader")
        classifier = get_classification_repository(self._pdm)
        extractor = get_extraction_repository()
        embedder = get_embedding_repository()
        version = index_version(self._pdm, classifier, extractor, embedder.signature if embedder else None)
        catalog = CatalogRepository(connection if connection is not None else self._engine, self._caller.tenant_id)
        total, current = catalog.index_state(version)
        if not total or current != total:
            raise ToolError(
                f"INDEX_UPDATING: índice pendente na versão {version} ({current}/{total}). "
                "Aguarde a atualização automática e tente novamente. Não é possível concluir ausência de duplicados."
            )
        return get_search_repository(
            pdm_catalog=self._pdm,
            catalog=catalog,
            classifier=classifier,
            extractor=extractor,
            index_version=version,
            caller=self._caller,
            embedder=embedder,
        )

    def run(
        self,
        query: str,
        pdm_class_id: str | None,
        attributes: dict[str, str] | None,
        limit: int,
        item_name: str | None = None,
    ):
        if self._engine is None or self._caller is None:
            self._ready()
        with self._engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            with connection.begin():
                result = self._ready(connection).search(
                    SearchQuery(query, pdm_class_id, attributes or {}, limit, item_name)
                )
                return SimilarMaterials.model_validate(result)
