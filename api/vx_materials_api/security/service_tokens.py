"""Tokens internos para o Agent: curtos, com audience exclusiva e sem o token do usuário."""

import time
import uuid

import jwt

ISSUER = "vx-api"
AGENT_AUDIENCE = "vx-agent"
TTL_SECONDS = 60


def issue_agent_token(
    user_id: uuid.UUID, permissions: frozenset[str], center_codes: frozenset[str], secret: str
) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AGENT_AUDIENCE,
        "sub": str(user_id),
        "iat": now,
        "exp": now + TTL_SECONDS,
        "jti": str(uuid.uuid4()),
        "permissions": sorted(permissions),
        "center_codes": sorted(center_codes),
    }
    return jwt.encode(claims, secret, algorithm="HS256")
