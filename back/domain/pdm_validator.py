"""Validação de atributos contra o PDM, compartilhada entre batch e chat."""

import re
from collections.abc import Mapping

from domain.contracts import (
    ITEM_NAME_SUBJECT,
    Condition,
    ConditionOperator,
    InvalidAttribute,
    MissingAttribute,
    PdmAttribute,
    PdmCatalog,
    PdmClass,
    PdmValidationResult,
    ValidationStatus,
)
from domain.identity import build_identity_key
from domain.pdm_formatter import format_description

_DECIMAL = r"\d+(?:,\d+)?"
_INCHES = r"(?:\d+\.\d+/\d+|\d+/\d+|\d+)POL"
_BEARING_REFERENCE = r"\d+(?:-(?:2RS|ZZ))?(?:/C3)?"

# Mapa explícito da coluna FORMATO para atributos sem lista de valores. None indica um código
# informado pelo fabricante, sem padrão a conferir. Texto novo no Excel exige decisão humana.
_FORMATS: dict[str, re.Pattern[str] | None] = {
    text: re.compile(pattern) if pattern else None
    for text, pattern in {
        "número + MM, decimal com vírgula (ex.: 16,25MM)": rf"{_DECIMAL}MM",
        "número + MM, decimal com vírgula": rf"{_DECIMAL}MM",
        "rosca métrica: número + MM (50MM); rosca em polegada: fração + POL (2.1/4POL)": rf"{_DECIMAL}MM|{_INCHES}",
        "polegada em fração + POL (ex.: 1.1/4POL)": _INCHES,
        "número + M": rf"{_DECIMAL}M",
        "número + BAR": rf"{_DECIMAL}BAR",
        "número + MM2": rf"{_DECIMAL}MM2",
        "número + A": rf"{_DECIMAL}A",
        "número + W": rf"{_DECIMAL}W",
        "inteiro": r"\d+",
        "faixa de medição: 0- seguido do valor máximo e BAR (0-16BAR)": rf"0-{_DECIMAL}BAR",
        "número do Certificado de Aprovação do Ministério do Trabalho, 5 dígitos": r"\d{5}",
        "série + sufixo de proteção + folga: 2RS = vedação de borracha nos dois lados, ZZ = proteção metálica nos "
        "dois lados, sem sufixo = aberto; /C3 = folga C3 (ex.: 6205-2RS/C3, 6310-ZZ/C3)": _BEARING_REFERENCE,
        "designação ISO do rolamento, com sufixos de furo e folga (22212EK/C3)": r"\d+[A-Z]*(?:/C3)?",
        "perfil + comprimento: clássicas pelo comprimento interno em polegadas (B54); SP pelo comprimento primitivo "
        "em mm (SPB 2000)": r"[A-E]X?\d+|5V\d+|SP[ZABC] \d+",
        "código da peça no catálogo do fabricante, como ele informa": None,
        "rosca de fixação como o fabricante informa (1.1/2-16 UN)": None,
    }.items()
}


class PdmFormatError(ValueError):
    """O PDM traz um FORMATO sem regra definida."""


def validate_pdm(
    catalog: PdmCatalog,
    pdm_class_id: str | None,
    attributes: Mapping[str, str | None],
    *,
    item_name: str | None = None,
    unit: str | None = None,
) -> PdmValidationResult:
    """Valida os valores como recebidos: normalização e extração acontecem antes desta etapa.

    `item_name` é obrigatório em classes com vários itens, como conexões e filtros. `unit` só é
    conferida quando informada. Valores vazios contam como ausentes.
    """
    pdm_class = catalog.classes.get(pdm_class_id) if pdm_class_id else None
    if pdm_class is None:
        return PdmValidationResult(ValidationStatus.OUT_OF_SCOPE)

    known = {a.name: a for a in pdm_class.attributes}
    values = {name: value for name, value in attributes.items() if value is not None and value.strip()}
    missing: list[MissingAttribute] = []
    invalid: list[InvalidAttribute] = []

    item = _resolve_item(pdm_class, item_name, missing, invalid)
    invalid += [InvalidAttribute(name, "UNKNOWN_ATTRIBUTE", values[name]) for name in values if name not in known]
    if unit is not None and unit != pdm_class.default_unit:
        invalid.append(InvalidAttribute("UNIDADE", "UNIT_NOT_CLASS_DEFAULT", unit, pdm_class.default_unit))

    applicable: dict[str, str] = {}
    required: dict[str, str] = {}
    not_applicable: list[str] = []
    for attribute in pdm_class.attributes:
        applies = _applies(attribute, known, values, item)
        value = values.get(attribute.name)
        if applies is False:
            if value is not None:
                not_applicable.append(attribute.name)
            continue
        if value is None:
            if applies and attribute.required:
                missing.append(_missing(attribute.name, "REQUIRED_ATTRIBUTE_MISSING"))
            continue
        problem = _check_value(attribute, value)
        if problem:
            invalid.append(problem)
        applicable[attribute.name] = value
        if attribute.required:
            required[attribute.name] = value

    if invalid:
        status = ValidationStatus.INVALID
    elif missing:
        status = ValidationStatus.INCOMPLETE
    else:
        status = ValidationStatus.VALID
    is_valid = status is ValidationStatus.VALID
    return PdmValidationResult(
        status=status,
        missing_attributes=tuple(missing),
        invalid_attributes=tuple(invalid),
        not_applicable_attributes=tuple(not_applicable),
        formatted_description=format_description(pdm_class, item, applicable) if is_valid else None,
        identity_key=build_identity_key(pdm_class, item, required) if is_valid else None,
        can_submit=is_valid,
    )


def _resolve_item(
    pdm_class: PdmClass, item_name: str | None, missing: list[MissingAttribute], invalid: list[InvalidAttribute]
) -> str | None:
    if item_name is None:
        if len(pdm_class.item_names) == 1:
            return pdm_class.item_names[0]
        missing.append(_missing(ITEM_NAME_SUBJECT, "ITEM_NAME_MISSING"))
        return None
    if item_name not in pdm_class.item_names:
        invalid.append(InvalidAttribute(ITEM_NAME_SUBJECT, "UNKNOWN_ITEM_NAME", item_name))
        return None
    return item_name


def _applies(
    attribute: PdmAttribute, known: Mapping[str, PdmAttribute], values: Mapping[str, str], item: str | None
) -> bool | None:
    """Diz se o atributo vale para este item. None: ainda depende de um campo não informado."""
    condition = attribute.applies_when
    if condition.operator is ConditionOperator.ALWAYS:
        return True
    actual = item if condition.subject == ITEM_NAME_SUBJECT else values.get(condition.subject)
    if actual is not None:
        return _matches(condition, actual)
    if condition.subject != ITEM_NAME_SUBJECT and _applies(known[condition.subject], known, values, item) is False:
        # O sujeito não existe neste item: um flange não tem CONEXAO, logo não é solda de topo.
        return condition.operator is ConditionOperator.NOT_IN
    return None


def _matches(condition: Condition, actual: str) -> bool:
    if condition.operator is ConditionOperator.NOT_IN:
        return actual not in condition.values
    return actual in condition.values


def _check_value(attribute: PdmAttribute, value: str) -> InvalidAttribute | None:
    if attribute.allowed_values is not None:
        if value not in attribute.allowed_values:
            return InvalidAttribute(attribute.name, "VALUE_NOT_ALLOWED", value, " | ".join(attribute.allowed_values))
        return None
    if attribute.format not in _FORMATS:
        raise PdmFormatError(f"{attribute.name}: FORMATO sem regra definida: {attribute.format!r}")
    pattern = _FORMATS[attribute.format]
    if pattern is not None and not pattern.fullmatch(value):
        return InvalidAttribute(attribute.name, "INVALID_FORMAT", value, attribute.format)
    return None


def _missing(name: str, reason_code: str) -> MissingAttribute:
    # Pergunta genérica: o agente reformula para a conversa.
    return MissingAttribute(name, reason_code, f"Qual é o valor de {name}?")
