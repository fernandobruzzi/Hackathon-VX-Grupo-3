"""Conferência da versão do PDM pedida pelas tools."""

from mcp.server.mcpserver.exceptions import ToolError

from domain.contracts import PdmCatalog


def require_version(catalog: PdmCatalog, pdm_version: str) -> None:
    if pdm_version != catalog.version:
        raise ToolError(f"Versao do PDM indisponivel: {pdm_version}. Disponivel: {catalog.version}")
