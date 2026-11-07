"""Ator do serviço de aplicação: não representa um usuário nem concede papel humano."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class AutomaticActor:
    tenant_id: UUID
    center_codes: frozenset[str]
    execution: dict = field(default_factory=dict)
    user_id: None = None
    roles: tuple[str, ...] = ()
