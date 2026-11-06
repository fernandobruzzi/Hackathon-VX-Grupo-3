"""Autorização do Agent e do MCP: token interno emitido pela API e visão de estoque."""

import json
import os
from dataclasses import dataclass
from uuid import UUID

import jwt

FINANCIAL_PERMISSION = "metrics:financial"
INVENTORY_PERMISSION = "inventory:read"

INVENTORY_VIEW = "mcp_inventory"
INVENTORY_FINANCIAL_VIEW = "mcp_inventory_financial"

# A API inicia o servidor por sessão e passa aqui a identidade já validada. Ver #17.
CALLER_VARIABLE = "VX_CALLER"


@dataclass(frozen=True)
class Caller:
    """Identidade vinculada à execução pela API. Nunca vem de parâmetros disponíveis ao LLM."""

    user_id: str
    tenant_id: str
    permissions: frozenset[str]
    center_codes: frozenset[str] = frozenset()

    def __post_init__(self):
        try:
            UUID(self.tenant_id)
        except (ValueError, TypeError, AttributeError) as error:
            raise InvalidInternalToken("tenant_id invalido") from error


def inventory_view(caller: Caller) -> str:
    """Escolhe a view de estoque: preço e valor só para quem tem a permissão financeira.

    O banco não conhece o usuário, porque o MCP usa uma única credencial, então esta função é a
    barreira. Tools que leem estoque devem sempre obter o nome da view por aqui.
    """
    return INVENTORY_FINANCIAL_VIEW if FINANCIAL_PERMISSION in caller.permissions else INVENTORY_VIEW


INTERNAL_TOKEN_SECRET_VARIABLE = "AGENT_INTERNAL_TOKEN_SECRET"
INTERNAL_TOKEN_ISSUER = "vx-api"
INTERNAL_TOKEN_AUDIENCE = "vx-agent"
_ALGORITHM = "HS256"


class InvalidInternalToken(Exception):
    """Token interno ausente, expirado ou emitido para outro destino."""


def verify_internal_token(token: str, secret: str) -> Caller:
    """Valida o JWT curto emitido pela API. Nunca aceita token de usuário nem outro audience."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=INTERNAL_TOKEN_AUDIENCE,
            issuer=INTERNAL_TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "tenant_id"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidInternalToken(str(error)) from error
    permissions = _string_list(claims, "permissions")
    center_codes = _string_list(claims, "center_codes")
    return Caller(
        user_id=claims["sub"],
        tenant_id=claims["tenant_id"],
        permissions=frozenset(permissions),
        center_codes=frozenset(center_codes),
    )


def _string_list(claims: dict, name: str) -> list[str]:
    value = claims.get(name, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InvalidInternalToken(f"{name} inválido")
    return value


def caller_to_environment(caller: Caller) -> str:
    """Serializa a identidade validada para `VX_CALLER`, lida pelo servidor MCP."""
    return json.dumps(
        {
            "user_id": caller.user_id,
            "tenant_id": caller.tenant_id,
            "permissions": sorted(caller.permissions),
            "center_codes": sorted(caller.center_codes),
        }
    )


def caller_from_environment() -> Caller | None:
    """Sem identidade, nenhuma tool devolve estoque."""
    raw = os.environ.get(CALLER_VARIABLE)
    if not raw:
        return None
    data = json.loads(raw)
    return Caller(
        user_id=data["user_id"],
        tenant_id=data.get("tenant_id"),
        permissions=frozenset(data.get("permissions", [])),
        center_codes=frozenset(data.get("center_codes", [])),
    )
