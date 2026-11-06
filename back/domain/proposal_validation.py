"""Validação PDM que a aprovação aplica, compartilhada pelo batch, pela fila e pela API.

Por padrão, uma proposta só é aprovável se o resultado (`after`) atende ao PDM, unidade incluída, e se cada
membro de uma unificação atende ao PDM por si. Se o batch e a fila não usassem a mesma regra, a
fila ofereceria como aprovável o que a aprovação recusa com `PDM_INVALID`.
Enriquecimento parcial pode admitir lacunas no resultado de forma explícita, sem
admitir valores inválidos nem liberar membros incompletos de unificações.
"""

from collections.abc import Iterable, Mapping

from domain.contracts import PdmCatalog, PdmValidationResult, ValidationStatus
from domain.pdm_validator import validate_pdm

# Prefixo dos conflitos gravados pelo batch e exibidos na fila.
PDM_INVALID = "PDM_INVALIDO"


def is_approvable(validation: PdmValidationResult, *, allow_incomplete: bool = False) -> bool:
    """PDM completo por padrão; enriquecimento parcial admite lacunas, nunca valores inválidos."""
    accepted = validation.status is ValidationStatus.VALID or (
        allow_incomplete and validation.status is ValidationStatus.INCOMPLETE
    )
    return accepted and not validation.not_applicable_attributes


def _reasons(validation: PdmValidationResult) -> str:
    if validation.status is ValidationStatus.OUT_OF_SCOPE:
        return "classe fora do PDM"
    parts = []
    if validation.missing_attributes:
        parts.append("faltam " + ", ".join(item.name for item in validation.missing_attributes))
    for item in validation.invalid_attributes:
        parts.append(f"{item.name} inválido ({item.reason_code})")
    if validation.not_applicable_attributes:
        parts.append("não se aplicam " + ", ".join(validation.not_applicable_attributes))
    return "; ".join(parts) or validation.status.value


def _validate(catalog: PdmCatalog, data: Mapping, unit: str | None = None) -> PdmValidationResult:
    return validate_pdm(
        catalog, data.get("pdm_class_id"), data.get("attributes") or {}, item_name=data.get("item_name"), unit=unit
    )


def approval_blockers(
    catalog: PdmCatalog,
    after: Mapping,
    members: Iterable[Mapping] = (),
    *,
    check_unit: bool = True,
    allow_incomplete: bool = False,
) -> list[str]:
    """Motivos pelos quais a aprovação recusaria a proposta por PDM, prontos para a lista de conflitos.

    `after` e cada membro trazem `pdm_class_id`, `item_name` e `attributes`; o `after` traz também
    `unit`. Membros só contam em unificações (mais de um), como na aprovação.
    """
    blockers = []
    result = _validate(catalog, after, after.get("unit") if check_unit else None)
    if not is_approvable(result, allow_incomplete=allow_incomplete):
        blockers.append(f"{PDM_INVALID}: resultado não atende ao PDM ({_reasons(result)})")
    members = list(members)
    if len(members) > 1:
        for member in members:
            checked = _validate(catalog, member)
            if not is_approvable(checked):
                code = member.get("material_code", "?")
                blockers.append(f"{PDM_INVALID}: membro {code} não atende ao PDM ({_reasons(checked)})")
    return blockers
