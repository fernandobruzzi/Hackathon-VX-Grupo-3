"""Decisão de identidade compartilhada: nenhuma chave ou nota vence evidência contraditória."""

from dataclasses import dataclass
from typing import Literal

from domain.contracts import AnalyzedMaterial, IdentityMode, PdmCatalog
from domain.identity import (
    compare_attributes,
    material_manufacturer,
    material_review_reasons,
    partial_identity_key,
    reference_spelling_key,
)
from domain.pdm_validator import validate_pdm


@dataclass(frozen=True)
class IdentityDecision:
    status: Literal["SAME_MATERIAL", "DIFFERENT_MATERIAL", "REVIEW_REQUIRED"]
    reasons: tuple[str, ...] = ()


def decide_identity(catalog: PdmCatalog, left: AnalyzedMaterial, right: AnalyzedMaterial) -> IdentityDecision:
    """Compara evidência de dois materiais, revalidando a identidade em vez de confiar no índice."""
    pdm_class = catalog.classes.get(left.pdm_class_id)
    if pdm_class is None or right.pdm_class_id not in catalog.classes:
        return IdentityDecision("REVIEW_REQUIRED", ("CLASSE_NAO_CONFIRMADA",))
    if right.pdm_class_id != pdm_class.id:
        return IdentityDecision("DIFFERENT_MATERIAL", ("CLASSES_DIFERENTES",))
    reasons = tuple(dict.fromkeys(material_review_reasons(left, pdm_class) + material_review_reasons(right, pdm_class)))
    if reasons:
        return IdentityDecision("REVIEW_REQUIRED", reasons)

    manufacturers = material_manufacturer(left), material_manufacturer(right)
    if all(manufacturers) and manufacturers[0] != manufacturers[1]:
        return IdentityDecision("DIFFERENT_MATERIAL", ("FABRICANTES_DIFERENTES",))
    if manufacturers[0] != manufacturers[1]:
        return IdentityDecision("REVIEW_REQUIRED", ("FABRICANTE_NAO_CONFIRMADO",))

    keys = []
    for material in (left, right):
        validation = validate_pdm(catalog, pdm_class.id, material.attributes, item_name=material.item_name)
        # A regra do PDM permite PN genuíno mesmo com outros campos em falta. Valores inválidos
        # conhecidos continuam sendo contradições; uma chave antiga não os torna válidos.
        if validation.invalid_attributes:
            return IdentityDecision("REVIEW_REQUIRED", ("ATRIBUTOS_INVALIDOS",))
        keys.append(validation.identity_key or partial_identity_key(pdm_class, material.attributes))
    same_key = bool(keys[0]) and keys[0] == keys[1]
    reference_mode = pdm_class.identity_mode is IdentityMode.MANUFACTURER_REFERENCE
    if (
        reference_mode
        and same_key
        and reference_spelling_key(left.attributes["REFERENCIA FABRICANTE"])
        != reference_spelling_key(right.attributes["REFERENCIA FABRICANTE"])
    ):
        return IdentityDecision("REVIEW_REQUIRED", ("SUFIXO_REFERENCIA_NAO_CONFIRMADO",))
    conflicts, _ = compare_attributes(pdm_class, left.attributes, right.attributes)
    if conflicts:
        reason = "ATRIBUTOS_CONTRADIZEM_REFERENCIA" if same_key else "ATRIBUTOS_DIFERENTES"
        return IdentityDecision("REVIEW_REQUIRED" if same_key else "DIFFERENT_MATERIAL", (reason, *conflicts))
    if left.item_name != right.item_name:
        if not left.item_name or not right.item_name:
            return IdentityDecision("REVIEW_REQUIRED", ("SUBSTANTIVO_NAO_CONFIRMADO",))
        if reference_mode and same_key:
            return IdentityDecision("REVIEW_REQUIRED", ("SUBSTANTIVO_CONTRADIZ_REFERENCIA",))
        return IdentityDecision("DIFFERENT_MATERIAL", ("SUBSTANTIVOS_DIFERENTES",))
    if same_key:
        return IdentityDecision("SAME_MATERIAL")
    return IdentityDecision("REVIEW_REQUIRED", ("IDENTIDADE_NAO_CONFIRMADA",))
