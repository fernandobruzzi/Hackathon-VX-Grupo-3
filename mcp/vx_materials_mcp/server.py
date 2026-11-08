"""Servidor MCP por stdio. Stdout é do protocolo: nada aqui escreve nele."""

import os

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from sqlalchemy import create_engine

from domain.contracts import PdmCatalog
from domain.pdm_loader import load_pdm
from domain.runtime import check_simulated_clients
from vx_materials_mcp.chatbot.prompts import register_prompts
from vx_materials_mcp.repositories.resource_repository import ResourceRepository
from vx_materials_mcp.resources.catalog import register_resources
from vx_materials_mcp.schemas.rag import RagContext
from vx_materials_mcp.schemas.tools import NcmConsistency, PdmTemplate, PdmValidation, SimilarMaterials
from vx_materials_mcp.security import caller_from_environment
from vx_materials_mcp.tools import check_ncm_consistency as check_ncm_consistency_tool
from vx_materials_mcp.tools import get_pdm_template as get_pdm_template_tool
from vx_materials_mcp.tools import validate_and_format_pdm as validate_and_format_pdm_tool
from vx_materials_mcp.tools.enrich_from_trusted_source import Enrichment, EnrichmentResult, TrustedSourceResearch
from vx_materials_mcp.tools.retrieve_context import ContextRetrieval
from vx_materials_mcp.tools.search_similar_materials import SimilarMaterialsSearch

PDM_PATH_VARIABLE = "PDM_WORKBOOK_PATH"
DEFAULT_PDM_PATH = "data/desafio01/03_padrao_cadastro_PDM.xlsx"
_READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


def build_server(
    catalog: PdmCatalog,
    search: SimilarMaterialsSearch | None = None,
    resources: ResourceRepository | None = None,
    context: ContextRetrieval | None = None,
) -> MCPServer:
    """Registra as tools. Parâmetros nunca incluem usuário, papel ou tenant: a identidade vem da API."""
    server = MCPServer(name="vx-materials")

    context = context or ContextRetrieval(catalog, None, None)

    @server.tool(annotations=_READ_ONLY)
    def retrieve_material_context(query: str, pdm_class_id: str | None = None, limit: int = 5) -> RagContext:
        """Recupera exemplos, regras PDM e NCM oficial, com citações e orçamento máximo de 12 mil caracteres.

        Contexto é referência, não prova de identidade, nem autorização para cadastrar ou corrigir NCM.
        Tenant, centros e permissões vêm exclusivamente da sessão autenticada.
        """
        try:
            return RagContext.model_validate(context.run(query, pdm_class_id, limit))
        except ValueError as error:
            raise ToolError(str(error)) from error

    @server.tool(annotations=_READ_ONLY)
    def get_pdm_template(pdm_class_id: str, pdm_version: str) -> PdmTemplate:
        """Retorna o modelo de uma classe do PDM: itens, identidade, atributos, condições, unidade e NCM."""
        return get_pdm_template_tool.run(catalog, pdm_class_id, pdm_version)

    @server.tool(annotations=_READ_ONLY)
    def validate_and_format_pdm(
        pdm_class_id: str,
        pdm_version: str,
        attributes: dict[str, str | None],
        item_name: str | None = None,
        unit: str | None = None,
    ) -> PdmValidation:
        """Valida atributos contra o PDM. Retorna campos ausentes e inválidos, e a descrição padrão quando válido.

        Informe `item_name` em classes com vários itens, e `unit` para conferir a unidade da classe.
        """
        return validate_and_format_pdm_tool.run(catalog, pdm_class_id, pdm_version, attributes, item_name, unit)

    search = search or SimilarMaterialsSearch(catalog, None, None)

    @server.tool(annotations=_READ_ONLY)
    def search_similar_materials(
        query: str,
        pdm_class_id: str | None = None,
        attributes: dict[str, str] | None = None,
        limit: int = 5,
        item_name: str | None = None,
    ) -> SimilarMaterials:
        """Busca materiais já cadastrados parecidos com o pedido: identidade exata e texto.

        `identity_verified` diz se é o mesmo item pela regra do PDM; `ranking_score` só ordena.
        Bloqueados indicam o código ativo a usar; obsoletos não devem ser reutilizados.
        """
        return search.run(query, pdm_class_id, attributes, limit, item_name)

    @server.tool(annotations=_READ_ONLY)
    def check_ncm_consistency(
        pdm_class_id: str,
        attributes: dict[str, str | None],
        ncm: str | None,
        pdm_version: str | None = None,
        item_name: str | None = None,
        ncm_version: str | None = None,
    ) -> NcmConsistency:
        """Avalia o NCM pelo PDM e indica revisão fiscal; não aprova nem altera materiais.

        Sem snapshot configurado, existência e vigência são desconhecidas. Informe item_name
        nas classes com vários substantivos. Alterar atributos exige nova avaliação.
        """
        return check_ncm_consistency_tool.run(
            catalog, pdm_class_id, attributes, ncm, pdm_version, item_name, ncm_version
        )

    resources = resources or ResourceRepository(None, None)
    enrichment = Enrichment(resources, TrustedSourceResearch(catalog))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True))
    def enrich_from_trusted_source(
        material_code: str, attributes_requested: list[str], refresh: bool = False
    ) -> EnrichmentResult:
        """Consulta cache e fontes revisadas dos 15 produtos reais autorizados pelo manifesto vigente.

        Pesquisa sem evidência ou com prazo excedido retorna PENDING, preservando o cache.
        Preview não persistido é proposta; não publica atributos nem autoriza aprovação.
        """
        try:
            return enrichment.run(material_code, attributes_requested, refresh)
        except ValueError as error:
            raise ToolError(str(error)) from error

    register_resources(server, catalog, resources)
    register_prompts(server)
    return server


def main() -> None:
    check_simulated_clients()
    catalog = load_pdm(os.environ.get(PDM_PATH_VARIABLE, DEFAULT_PDM_PATH))
    search = SimilarMaterialsSearch(catalog, os.environ.get("DATABASE_URL"), caller_from_environment())
    database_url = os.environ.get("DATABASE_URL")
    engine = create_engine(database_url) if database_url else None
    resources = ResourceRepository(engine, caller_from_environment())
    context = ContextRetrieval(catalog, database_url, caller_from_environment())
    try:
        build_server(catalog, search, resources, context).run("stdio")
    finally:
        if engine is not None:
            engine.dispose()
        if context.engine is not None:
            context.engine.dispose()


if __name__ == "__main__":
    main()
