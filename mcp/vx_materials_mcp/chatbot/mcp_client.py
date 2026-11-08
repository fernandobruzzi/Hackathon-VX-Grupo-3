"""Cliente MCP: inicia o servidor como subprocesso e fala com ele por stdio."""

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from mcp.types import Tool

from mcp import ClientSession
from vx_materials_mcp.security import CALLER_VARIABLE
from vx_materials_mcp.server import PDM_PATH_VARIABLE

# Somente configuração/credenciais do próprio Agent; segredos da API não atravessam o stdio.
INHERITED_VARIABLES = (
    "APP_ENV",
    "AWS_ACCESS_KEY_ID",
    "AWS_CA_BUNDLE",
    "AWS_CONFIG_FILE",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_DEFAULT_REGION",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_ROLE_ARN",
    "AWS_ROLE_SESSION_NAME",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "CLASSIFICATION_REPOSITORY",
    "EXTRACTION_REPOSITORY",
    "ENRICHMENT_REPOSITORY",
    "NCM_SNAPSHOT_VERSION",
    "NORMALIZATION_REPOSITORY",
    "RAG_REPOSITORY",
    "REQUESTS_CA_BUNDLE",
    "S3_BUCKET",
    "SSL_CERT_FILE",
    "STORAGE_BACKEND",
    "STORAGE_LOCAL_DIR",
)


class McpToolError(RuntimeError):
    """A tool foi chamada, mas devolveu um erro."""


class McpClient:
    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_tools(self) -> list[Tool]:
        return (await self._session.list_tools()).tools

    async def list_resource_templates(self):
        return (await self._session.list_resource_templates()).resource_templates

    async def read_resource(self, uri: str) -> dict[str, Any]:
        try:
            result = await self._session.read_resource(uri)
        except MCPError as error:
            raise McpToolError(str(error)) from error
        return json.loads(result.contents[0].text)

    async def list_prompts(self):
        return (await self._session.list_prompts()).prompts

    async def get_prompt(self, name: str, arguments: dict[str, str]):
        try:
            return await self._session.get_prompt(name, arguments)
        except MCPError as error:
            raise McpToolError(str(error)) from error

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
async def connect(
    pdm_path: str | None = None, database_url: str | None = None, caller: str | None = None
) -> AsyncIterator[McpClient]:
    """Abre uma sessão com um servidor exclusivo, encerrado ao final.

    `caller` é a identidade já validada pela API, em JSON. Ela vai para o processo do servidor, nunca
    para os parâmetros das tools.
    """
    env = {name: os.environ[name] for name in INHERITED_VARIABLES if name in os.environ}
    for variable, value in (
        (PDM_PATH_VARIABLE, pdm_path or os.environ.get(PDM_PATH_VARIABLE)),
        ("DATABASE_URL", database_url or os.environ.get("DATABASE_URL")),
        (CALLER_VARIABLE, caller or os.environ.get(CALLER_VARIABLE)),
        ("SEARCH_REPOSITORY", os.environ.get("SEARCH_REPOSITORY")),
        ("EMBEDDING_REPOSITORY", os.environ.get("EMBEDDING_REPOSITORY")),
        ("OLLAMA_URL", os.environ.get("OLLAMA_URL")),
    ):
        if value:
            env[variable] = value
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
