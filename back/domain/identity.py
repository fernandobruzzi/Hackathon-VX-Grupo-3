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


def reference_key(reference: str) -> str:
    """Forma de comparar referências: ignora separadores e o sufixo neutro `-00`."""
    return _REFERENCE_SEPARATORS.sub("", _REFERENCE_NEUTRAL_SUFFIX.sub("", reference))


def compare_attributes(
    pdm_class: PdmClass, first: Mapping[str, str], second: Mapping[str, str]
) -> tuple[list[str], int]:
    """Compara valores conhecidos dos dois lados. Devolve os obrigatórios em conflito e quantos coincidem."""
    conflicts, matching = [], 0
    for attribute in pdm_class.attributes:
        if not attribute.required or attribute.name not in first or attribute.name not in second:
            continue
        left, right = first[attribute.name], second[attribute.name]
        if attribute.name == _REFERENCE:
            left, right = reference_key(left), reference_key(right)
        if left == right:
            matching += 1
        else:
            conflicts.append(attribute.name)
    return conflicts, matching


def partial_identity_key(pdm_class: PdmClass, attributes: Mapping[str, str]) -> str | None:
    """Chave das classes de referência mesmo com outros campos em falta: pela regra geral 10,
    fabricante e referência bastam para dizer que é o mesmo item."""
    if pdm_class.identity_mode is not IdentityMode.MANUFACTURER_REFERENCE:
        return None
    if _MANUFACTURER not in attributes or _REFERENCE not in attributes:
        return None
    return build_identity_key(pdm_class, "", attributes)


def build_identity_key(pdm_class: PdmClass, item_name: str, required_values: Mapping[str, str]) -> str:
    """Itens com a mesma chave são o mesmo item. Atributos opcionais nunca entram nela."""
    if pdm_class.identity_mode is IdentityMode.MANUFACTURER_REFERENCE:
        reference = reference_key(required_values[_REFERENCE])
        return f"{pdm_class.id}|{required_values[_MANUFACTURER]}|{reference}"
    values = [f"{a.name}={required_values[a.name]}" for a in pdm_class.attributes if a.name in required_values]
    return "|".join([pdm_class.id, item_name, *values])
