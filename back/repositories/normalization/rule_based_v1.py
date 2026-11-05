"""Normalizacao deterministica baseada nas regras gerais do PDM (pdm-kit-v1).

Cobre apenas o que o padrao define sem ambiguidade: formato do NCM (regra 12), texto em
maiusculas sem acentos (regra 3) e aliases de unidade (aba UNIDADES). Nao verifica se o
NCM existe na tabela oficial nem se a unidade e a padrao da classe (regra 11).
"""

import re
import unicodedata

from domain.contracts import FieldStatus, NormalizedField

CANONICAL_UNITS = frozenset({"PC", "M", "PR", "KG", "L"})

UNIT_ALIASES = {
    "PÇ": "PC",
    "PCA": "PC",
    "UN": "PC",
    "MT": "M",
    "MTS": "M",
    "PAR": "PR",
    "LT": "L",
}

# Embalagem sem fator conhecido nao pode virar unidade canonica automaticamente:
# converter CX para PC, por exemplo, distorceria a consolidacao de estoque.
PACKAGING_UNITS = frozenset({"CX", "CT", "JG", "BR", "RL", "GL", "BD"})

_NCM_SEPARATORS = re.compile(r"[.\s-]")
_NCM_CANONICAL = re.compile(r"\d{4}\.\d{2}\.\d{2}")
_NCM_DIGITS = re.compile(r"\d{8}")
_WHITESPACE = re.compile(r"\s+")


class RuleBasedV1NormalizationRepository:
    name = "rule_based_v1"

    def normalize_ncm(self, raw: str | None) -> NormalizedField:
        original = raw or ""
        trimmed = original.strip()
        if not trimmed:
            return self._field(original, None, FieldStatus.MISSING, "ncm.missing")
        if _NCM_CANONICAL.fullmatch(trimmed):
            status = FieldStatus.CANONICAL if trimmed == original else FieldStatus.NORMALIZED
            return self._field(original, trimmed, status, "ncm.format")
        digits = _NCM_SEPARATORS.sub("", trimmed)
        if _NCM_DIGITS.fullmatch(digits):
            value = f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"
            return self._field(original, value, FieldStatus.NORMALIZED, "ncm.format")
        return self._field(original, None, FieldStatus.UNRESOLVED, "ncm.invalid_format")

    def normalize_unit(self, raw: str | None) -> NormalizedField:
        original = raw or ""
        unit = original.strip().upper()
        if not unit:
            return self._field(original, None, FieldStatus.MISSING, "unit.missing")
        if unit in CANONICAL_UNITS:
            status = FieldStatus.CANONICAL if unit == original else FieldStatus.NORMALIZED
            return self._field(original, unit, status, "unit.canonical")
        if unit in UNIT_ALIASES:
            return self._field(original, UNIT_ALIASES[unit], FieldStatus.NORMALIZED, "unit.alias")
        if unit in PACKAGING_UNITS:
            return self._field(original, None, FieldStatus.UNRESOLVED, "unit.packaging_without_factor")
        return self._field(original, None, FieldStatus.UNRESOLVED, "unit.unknown")

    def normalize_text(self, raw: str | None) -> NormalizedField:
        original = raw or ""
        # NFKD separa acentos e converte compatibilidades como o "²" de MM² em "2".
        decomposed = unicodedata.normalize("NFKD", original)
        ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
        value = _WHITESPACE.sub(" ", ascii_only).strip().upper()
        if not value:
            return self._field(original, None, FieldStatus.MISSING, "text.missing")
        status = FieldStatus.CANONICAL if value == original else FieldStatus.NORMALIZED
        return self._field(original, value, status, "text.format")

    def _field(self, original: str, value: str | None, status: FieldStatus, rule: str) -> NormalizedField:
        return NormalizedField(original, value, status, f"{self.name}/{rule}")
