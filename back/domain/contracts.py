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


class ConditionOperator(StrEnum):
    ALWAYS = "ALWAYS"
    EQUALS = "EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"


# Sujeito de condicoes que dependem do nome do item (ex.: FLANGE), nao de um atributo.
ITEM_NAME_SUBJECT = "SUBSTANTIVO"


@dataclass(frozen=True)
class Condition:
    """Condicao controlada: nunca uma expressao livre vinda do arquivo."""

    operator: ConditionOperator = ConditionOperator.ALWAYS
    subject: str | None = None
    values: tuple[str, ...] = ()


class IdentityMode(StrEnum):
    TECHNICAL_ATTRIBUTES = "TECHNICAL_ATTRIBUTES"
    MANUFACTURER_REFERENCE = "MANUFACTURER_REFERENCE"


@dataclass(frozen=True)
class PdmAttribute:
    name: str
    order: int
    required: bool
    applies_when: Condition
    format: str
    allowed_values: tuple[str, ...] | None


@dataclass(frozen=True)
class NcmReference:
    codes: tuple[str, ...]
    rule: str


@dataclass(frozen=True)
class PdmClass:
    id: str
    noun: str | None  # None quando o nome vem de uma aba de substantivos
    qualifiers: tuple[str, ...]
    item_names: tuple[str, ...]
    group: str
    default_unit: str
    identity_mode: IdentityMode
    attributes: tuple[PdmAttribute, ...]
    ncm_references: tuple[NcmReference, ...]


@dataclass(frozen=True)
class PdmCatalog:
    version: str
    source_sha256: str
    classes: dict[str, PdmClass]
