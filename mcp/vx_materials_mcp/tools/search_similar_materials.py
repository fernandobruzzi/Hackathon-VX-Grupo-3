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
        self._repository = None

    def _ready(self):
        if self._engine is None:
            raise ToolError("Catalogo indisponivel: defina DATABASE_URL com a credencial mcp_reader")
        if self._repository is None:
            classifier = get_classification_repository(self._pdm)
            extractor = get_extraction_repository()
            embedder = get_embedding_repository()
            version = index_version(self._pdm, classifier, extractor, embedder.signature if embedder else None)
            catalog = CatalogRepository(self._engine)
            # Indexação e consulta precisam usar as mesmas regras, ou os tokens não se comparam.
            if catalog.indexed(version) == 0:
                raise ToolError(f"Indice de busca ausente na versao {version}: reconstrua com `vx-back index`")
            self._repository = get_search_repository(
                pdm_catalog=self._pdm,
                catalog=catalog,
                classifier=classifier,
                extractor=extractor,
                index_version=version,
                caller=self._caller,
                embedder=embedder,
            )
        return self._repository

    def run(self, query: str, pdm_class_id: str | None, attributes: dict[str, str] | None, limit: int):
        result = self._ready().search(SearchQuery(query, pdm_class_id, attributes or {}, limit))
        return SimilarMaterials.model_validate(result)
