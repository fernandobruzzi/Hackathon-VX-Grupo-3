"""Chave de identidade de um material (regra geral 10).

Não normaliza grafias como `LF 9009` e `LF9009`: isso acontece antes, na extração de atributos.
"""

from collections.abc import Mapping

from domain.contracts import IdentityMode, PdmClass

_MANUFACTURER = "FABRICANTE"
_REFERENCE = "REFERENCIA FABRICANTE"


def build_identity_key(pdm_class: PdmClass, item_name: str, required_values: Mapping[str, str]) -> str:
    """Itens com a mesma chave são o mesmo item. Atributos opcionais nunca entram nela."""
    if pdm_class.identity_mode is IdentityMode.MANUFACTURER_REFERENCE:
        return f"{pdm_class.id}|{required_values[_MANUFACTURER]}|{required_values[_REFERENCE]}"
    values = [f"{a.name}={required_values[a.name]}" for a in pdm_class.attributes if a.name in required_values]
    return "|".join([pdm_class.id, item_name, *values])
