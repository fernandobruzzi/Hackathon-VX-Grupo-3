"""Identidade autenticada que as rotas recebem. Vem sempre da sessão, nunca do payload."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    roles: tuple[str, ...]
    permissions: frozenset[str]
