import pytest

from vx_materials_mcp.security import Caller, inventory_view

# Permissões de leitura de cada papel, conforme a matriz RBAC da arquitetura.
SOLICITANTE = {"chat:use", "materials:read", "inventory:read"}
GOVERNANCA = SOLICITANTE | {"queue:read", "metrics:quality"}
FISCAL = SOLICITANTE | {"metrics:quality", "metrics:financial"}


@pytest.mark.parametrize(
    ("permissions", "view"),
    [
        (FISCAL, "mcp_inventory_financial"),
        (GOVERNANCA, "mcp_inventory"),
        (SOLICITANTE, "mcp_inventory"),
        (set(), "mcp_inventory"),
    ],
)
def test_only_financial_permission_reaches_prices(permissions, view):
    assert inventory_view(Caller("u", "11111111-1111-4111-8111-111111111111", frozenset(permissions))) == view


@pytest.mark.parametrize("tenant", [None, "", "invalid"])
def test_caller_rejects_missing_or_invalid_tenant(tenant):
    from vx_materials_mcp.security import InvalidInternalToken

    with pytest.raises(InvalidInternalToken, match="tenant_id"):
        Caller("u", tenant, frozenset())


def test_signed_tenant_survives_the_mcp_environment(monkeypatch):
    import time

    import jwt

    from vx_materials_mcp.security import (
        CALLER_VARIABLE,
        caller_from_environment,
        caller_to_environment,
        verify_internal_token,
    )

    tenant = "22222222-2222-4222-8222-222222222222"
    secret = "internal-test-secret-with-at-least-32-bytes"
    token = jwt.encode(
        {
            "sub": "u",
            "iss": "vx-api",
            "aud": "vx-agent",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
            "tenant_id": tenant,
        },
        secret,
        algorithm="HS256",
    )
    caller = verify_internal_token(token, secret)
    monkeypatch.setenv(CALLER_VARIABLE, caller_to_environment(caller))
    assert caller_from_environment() == caller
    assert caller.tenant_id == tenant


def test_concurrency_probe_token_reaches_the_authenticated_agent(monkeypatch):
    import importlib.util
    from contextlib import asynccontextmanager
    from pathlib import Path

    from fastapi.testclient import TestClient

    from domain.pdm_loader import load_pdm
    from vx_materials_api.bootstrap import TENANT_ID
    from vx_materials_mcp.app import create_app
    from vx_materials_mcp.security import verify_internal_token

    path = Path(__file__).parents[2] / "scripts/measure_agent.py"
    spec = importlib.util.spec_from_file_location("measure_agent", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    secret = "probe-test-secret-with-at-least-32-bytes"
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", secret)
    headers = probe.headers(1)
    caller = verify_internal_token(headers["Authorization"].removeprefix("Bearer "), secret)
    assert caller.tenant_id == str(TENANT_ID)
    assert caller.center_codes == frozenset({"1200"})
    reached = []

    @asynccontextmanager
    async def connect(identity):
        reached.append(identity)

        # O teste verifica o handoff autenticado; uma falha de tool não vira401.
        class Tools:
            async def call_tool(self, name, arguments):
                raise RuntimeError("catalog unavailable in probe authorization test")

        yield Tools()

    catalog = load_pdm(path.parents[1] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
    with TestClient(create_app(catalog, secret, connect)) as client:
        response = client.post("/internal/v1/chat/run", json=probe.payload(1), headers=headers)
    assert response.status_code == 200
    assert reached == [caller]
