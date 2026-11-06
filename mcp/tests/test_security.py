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
