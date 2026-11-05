"""Autorização do Agent e do MCP: token interno emitido pela API e visão de estoque."""

from dataclasses import dataclass

import jwt

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
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidInternalToken(str(error)) from error
    permissions = claims.get("permissions", [])
    if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
        raise InvalidInternalToken("permissions inválidas")
    return Caller(user_id=claims["sub"], permissions=frozenset(permissions))
