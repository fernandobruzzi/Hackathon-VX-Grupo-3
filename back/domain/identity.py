"""Chave de identidade de um material (regra geral 10).

A referência do fabricante fica como ele informa, então `LF 9009` e `LF-9009` só se igualam aqui.
"""

import re
import unicodedata
from collections.abc import Mapping
from functools import lru_cache

from domain.contracts import AnalyzedMaterial, IdentityMode, PdmClass

# Mude ao alterar as regras de identidade: a revisão entra na versão do índice de busca.
IDENTITY_RULES_VERSION = "identity-v2"
_MANUFACTURER = "FABRICANTE"
_REFERENCE = "REFERENCIA FABRICANTE"
_REFERENCE_SEPARATORS = re.compile(r"[\s.\-/]")
# A própria base trata N80767044-00 e N80767044 como a mesma peça.
_REFERENCE_NEUTRAL_SUFFIX = re.compile(r"-00$")
_REVISION = re.compile(r"\bREV(?:IS[AÃ]O|ISION)?(?:\s*[:.\-]\s*|\s+)[A-Z0-9]+\b", re.IGNORECASE)


def manufacturer_key(value: str) -> str:
    """Normaliza grafia, sem inventar equivalência entre marcas ou grupos econômicos."""
    folded = unicodedata.normalize("NFKD", value)
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).upper().split())


def material_manufacturer(material: AnalyzedMaterial) -> str:
    return manufacturer_key(material.record.manufacturer) or manufacturer_key(
        material.attributes.get(_MANUFACTURER, "")
    )


@lru_cache(maxsize=128)
def _model_keys(pdm_class: PdmClass) -> frozenset[str]:
    models = next((a.allowed_values or () for a in pdm_class.attributes if a.name == "MODELO EQUIPAMENTO"), ())
    return frozenset(reference_key(model) for model in models)


def reference_review_reasons(pdm_class: PdmClass, attributes: Mapping[str, str], *originals: str) -> tuple[str, ...]:
    """Modelo e revisão não comprovam o PN nem a intercambiabilidade de uma peça."""
    if pdm_class.identity_mode is not IdentityMode.MANUFACTURER_REFERENCE:
        return ()
    reference = attributes.get(_REFERENCE, "")
    reasons = []
    if any(_REVISION.search(value) for value in (reference, *originals)):
        reasons.append("REVISAO_DE_PECA_NAO_CONFIRMADA")
    if reference and reference_key(reference.upper()) in _model_keys(pdm_class):
        reasons.append("MODELO_NAO_E_REFERENCIA")
    elif not reference and attributes.get("MODELO EQUIPAMENTO"):
        reasons.append("REFERENCIA_DE_PECA_AUSENTE")
    return tuple(reasons)


def material_review_reasons(material: AnalyzedMaterial, pdm_class: PdmClass) -> tuple[str, ...]:
    reasons = list(
        reference_review_reasons(pdm_class, material.attributes, material.record.description, material.record.reference)
    )
    structured = manufacturer_key(material.record.manufacturer)
    extracted = manufacturer_key(material.attributes.get(_MANUFACTURER, ""))
    if structured and extracted and structured != extracted:
        reasons.append("FABRICANTE_CONFLITANTE")
    return tuple(reasons)


def merge_partition(material: AnalyzedMaterial) -> tuple[str | None, str, str | None]:
    """Fabricante desconhecido não liga dois fabricantes distintos; nomes de peças também não."""
    return material.identity_key, material_manufacturer(material), material.item_name


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
    if not attributes.get(_MANUFACTURER, "").strip() or not attributes.get(_REFERENCE, "").strip():
        return None
    return build_identity_key(pdm_class, "", attributes)


def build_identity_key(pdm_class: PdmClass, item_name: str, required_values: Mapping[str, str]) -> str | None:
    """Chave do PDM, ainda sujeita à revisão de fabricante, nome da peça e evidência original."""
    if pdm_class.identity_mode is IdentityMode.MANUFACTURER_REFERENCE:
        if reference_review_reasons(pdm_class, required_values):
            return None
        reference = reference_key(required_values[_REFERENCE])
        return f"{pdm_class.id}|{required_values[_MANUFACTURER]}|{reference}"
    values = [f"{a.name}={required_values[a.name]}" for a in pdm_class.attributes if a.name in required_values]
    return "|".join([pdm_class.id, item_name, *values])
