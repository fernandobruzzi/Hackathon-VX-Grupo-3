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
    assert inventory_view(Caller("u", frozenset(permissions))) == view
