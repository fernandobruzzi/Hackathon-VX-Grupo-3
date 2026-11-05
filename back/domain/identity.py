"""Chave de identidade de um material (regra geral 10).

A referência do fabricante fica como ele informa, então `LF 9009` e `LF-9009` só se igualam aqui.
"""

import re
from collections.abc import Mapping

from domain.contracts import IdentityMode, PdmClass

_MANUFACTURER = "FABRICANTE"
_REFERENCE = "REFERENCIA FABRICANTE"
_REFERENCE_SEPARATORS = re.compile(r"[\s.\-/]")
# A própria base trata N80767044-00 e N80767044 como a mesma peça.
_REFERENCE_NEUTRAL_SUFFIX = re.compile(r"-00$")


def build_identity_key(pdm_class: PdmClass, item_name: str, required_values: Mapping[str, str]) -> str:
    """Itens com a mesma chave são o mesmo item. Atributos opcionais nunca entram nela."""
    if pdm_class.identity_mode is IdentityMode.MANUFACTURER_REFERENCE:
        reference = _REFERENCE_NEUTRAL_SUFFIX.sub("", required_values[_REFERENCE])
        reference = _REFERENCE_SEPARATORS.sub("", reference)
        return f"{pdm_class.id}|{required_values[_MANUFACTURER]}|{reference}"
    values = [f"{a.name}={required_values[a.name]}" for a in pdm_class.attributes if a.name in required_values]
    return "|".join([pdm_class.id, item_name, *values])
