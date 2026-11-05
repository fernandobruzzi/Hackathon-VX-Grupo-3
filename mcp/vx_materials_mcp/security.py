"""Autorização do MCP. A validação do token interno emitido pela API entra aqui: ver #17."""

from dataclasses import dataclass

FINANCIAL_PERMISSION = "metrics:financial"

INVENTORY_VIEW = "mcp_inventory"
INVENTORY_FINANCIAL_VIEW = "mcp_inventory_financial"


@dataclass(frozen=True)
class Caller:
    """Identidade vinculada à execução pela API. Nunca vem de parâmetros disponíveis ao LLM."""

    user_id: str
    permissions: frozenset[str]


def inventory_view(caller: Caller) -> str:
    """Escolhe a view de estoque: preço e valor só para quem tem a permissão financeira.

    O banco não conhece o usuário, porque o MCP usa uma única credencial, então esta função é a
    barreira. Tools que leem estoque devem sempre obter o nome da view por aqui.
    """
    return INVENTORY_FINANCIAL_VIEW if FINANCIAL_PERMISSION in caller.permissions else INVENTORY_VIEW
