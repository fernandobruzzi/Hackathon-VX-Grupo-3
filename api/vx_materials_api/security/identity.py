"""Identidade autenticada que as rotas recebem. Vem sempre da sessão, nunca do payload."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    roles: tuple[str, ...]
    permissions: frozenset[str]
    # Centros cujo estoque o usuário pode ver. Configuração do backend, nunca do payload.
    center_codes: frozenset[str] = frozenset()
    display_name: str = ""
    csrf_token: str = ""
    persona: str | None = None
    authentication_method: str = "cookie"
