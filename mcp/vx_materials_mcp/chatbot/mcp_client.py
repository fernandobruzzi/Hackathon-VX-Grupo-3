"""Cliente MCP: inicia o servidor como subprocesso e fala com ele por stdio."""

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool

from mcp import ClientSession
from vx_materials_mcp.server import PDM_PATH_VARIABLE


class McpToolError(RuntimeError):
    """A tool foi chamada, mas devolveu um erro."""


class McpClient:
    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_tools(self) -> list[Tool]:
        return (await self._session.list_tools()).tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._session.call_tool(name, arguments)
        if result.is_error:
            message = " ".join(getattr(block, "text", "") for block in result.content)
            raise McpToolError(message)
        if result.structured_content is None:
            raise McpToolError(f"{name} nao devolveu conteudo estruturado")
        return result.structured_content


def _find_tool_error(group: BaseExceptionGroup) -> McpToolError | None:
    for error in group.exceptions:
        if isinstance(error, McpToolError):
            return error
        if isinstance(error, BaseExceptionGroup) and (found := _find_tool_error(error)):
            return found
    return None


@asynccontextmanager
async def connect(pdm_path: str | None = None) -> AsyncIterator[McpClient]:
    """Abre uma sessão com um servidor exclusivo, encerrado ao final."""
    env = {}
    path = pdm_path or os.environ.get(PDM_PATH_VARIABLE)
    if path:
        env[PDM_PATH_VARIABLE] = path
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "vx_materials_mcp.server"], env=env)
    try:
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield McpClient(session)
    except BaseExceptionGroup as group:
        # O SDK agrupa exceções ao fechar a sessão: quem chama recebe o erro da tool diretamente.
        tool_error = _find_tool_error(group)
        if tool_error is None:
            raise
        raise tool_error from group
