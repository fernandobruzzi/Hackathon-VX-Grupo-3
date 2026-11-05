"""Servidor MCP por stdio. Stdout é do protocolo: nada aqui escreve nele."""

import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from domain.contracts import PdmCatalog
from domain.pdm_loader import load_pdm
from vx_materials_mcp.schemas.tools import PdmTemplate, PdmValidation
from vx_materials_mcp.tools import get_pdm_template as get_pdm_template_tool
from vx_materials_mcp.tools import validate_and_format_pdm as validate_and_format_pdm_tool

PDM_PATH_VARIABLE = "PDM_WORKBOOK_PATH"
DEFAULT_PDM_PATH = "data/desafio01/03_padrao_cadastro_PDM.xlsx"
_READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


def build_server(catalog: PdmCatalog) -> MCPServer:
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

    return server


def main() -> None:
    catalog = load_pdm(os.environ.get(PDM_PATH_VARIABLE, DEFAULT_PDM_PATH))
    build_server(catalog).run("stdio")


if __name__ == "__main__":
    main()
