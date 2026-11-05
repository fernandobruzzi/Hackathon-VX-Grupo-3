"""Servidor MCP por stdio. Stdout é do protocolo: nada aqui escreve nele."""

import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from domain.contracts import PdmCatalog
from domain.pdm_loader import load_pdm
from domain.runtime import check_simulated_clients
from vx_materials_mcp.schemas.tools import NcmConsistency, PdmTemplate, PdmValidation, SimilarMaterials
from vx_materials_mcp.security import caller_from_environment
from vx_materials_mcp.tools import check_ncm_consistency as check_ncm_consistency_tool
from vx_materials_mcp.tools import get_pdm_template as get_pdm_template_tool
from vx_materials_mcp.tools import validate_and_format_pdm as validate_and_format_pdm_tool
from vx_materials_mcp.tools.search_similar_materials import SimilarMaterialsSearch

PDM_PATH_VARIABLE = "PDM_WORKBOOK_PATH"
DEFAULT_PDM_PATH = "data/desafio01/03_padrao_cadastro_PDM.xlsx"
_READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


def build_server(catalog: PdmCatalog, search: SimilarMaterialsSearch | None = None) -> MCPServer:
    """Registra as tools. Parâmetros nunca incluem usuário, papel ou tenant: a identidade vem da API."""
    server = MCPServer(name="vx-materials")

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
    ) -> SimilarMaterials:
        """Busca materiais já cadastrados parecidos com o pedido: identidade exata e texto.

        `identity_verified` diz se é o mesmo item pela regra do PDM; `ranking_score` só ordena.
        Bloqueados indicam o código ativo a usar; obsoletos não devem ser reutilizados.
        """
        return search.run(query, pdm_class_id, attributes, limit)

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

        Sem snapshot oficial, existência e vigência são desconhecidas. Informe item_name
        nas classes com vários substantivos. Alterar atributos exige nova avaliação.
        """
        return check_ncm_consistency_tool.run(
            catalog, pdm_class_id, attributes, ncm, pdm_version, item_name, ncm_version
        )

    return server


def main() -> None:
    check_simulated_clients()
    catalog = load_pdm(os.environ.get(PDM_PATH_VARIABLE, DEFAULT_PDM_PATH))
    search = SimilarMaterialsSearch(catalog, os.environ.get("DATABASE_URL"), caller_from_environment())
    build_server(catalog, search).run("stdio")


if __name__ == "__main__":
    main()
