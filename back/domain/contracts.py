"""Contratos do dominio compartilhados por batch e MCP."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class FieldStatus(StrEnum):
    CANONICAL = "CANONICAL"  # ja estava no padrao
    NORMALIZED = "NORMALIZED"  # corrigido por uma regra
    MISSING = "MISSING"  # campo vazio
    UNRESOLVED = "UNRESOLVED"  # exige revisao: nenhuma regra segura se aplica


@dataclass(frozen=True)
class NormalizedField:
    """Valor normalizado, sempre com o original e a regra aplicada (Arquitetura, Fluxo 1)."""

    original: str
    value: str | None
    status: FieldStatus
    rule: str


class NormalizationRepository(Protocol):
    """Um algoritmo de pre-processamento. Para testar outro, crie um novo repositorio
    em repositories/normalization e registre-o; os existentes permanecem no codigo."""

    name: str

    def normalize_ncm(self, raw: str | None) -> NormalizedField: ...

    def normalize_unit(self, raw: str | None) -> NormalizedField: ...

    def normalize_text(self, raw: str | None) -> NormalizedField: ...
