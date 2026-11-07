"""O stdio preserva o provider AWS do Agent e continua sem os segredos da API."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from vx_materials_mcp.chatbot import mcp_client


def test_aws_region_and_task_credentials_reach_stdio_without_api_secrets(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "/v2/credentials/example")
    monkeypatch.setenv("DATABASE_URL", "mcp-reader-only")
    monkeypatch.setenv("ENRICHMENT_REPOSITORY", "catalog_labels_v1")
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", "internal-secret")
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", "session-secret")
    monkeypatch.setenv("API_DB_PASSWORD", "api-secret")
    captured = []

    @asynccontextmanager
    async def transport(parameters):
        captured.append(parameters.env)
        yield (None, None)

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

    async def connect():
        with patch.object(mcp_client, "stdio_client", transport), patch.object(mcp_client, "ClientSession", Session):
            async with mcp_client.connect(caller='{"user_id":"caller"}'):
                pass

    asyncio.run(connect())
    env = captured[0]
    assert env["AWS_REGION"] == env["AWS_DEFAULT_REGION"] == "us-east-1"
    assert env["AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"] == "/v2/credentials/example"
    assert env["DATABASE_URL"] == "mcp-reader-only"
    assert env["ENRICHMENT_REPOSITORY"] == "catalog_labels_v1"
    assert env["VX_CALLER"] == '{"user_id":"caller"}'
    assert not {"AGENT_INTERNAL_TOKEN_SECRET", "SESSION_ENCRYPTION_KEY", "API_DB_PASSWORD"} & env.keys()


def test_agent_rejects_simulation_before_loading_any_reference(monkeypatch):
    from vx_materials_mcp.app import main

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "simulated_v1")
    monkeypatch.setenv("PDM_WORKBOOK_PATH", "/missing-reference")
    with pytest.raises(RuntimeError, match="simulated_v1"):
        main()


def test_standalone_stdio_rejects_simulation_at_startup(monkeypatch):
    from vx_materials_mcp.server import main

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "simulated_v1")
    with pytest.raises(RuntimeError, match="simulated_v1"):
        main()
