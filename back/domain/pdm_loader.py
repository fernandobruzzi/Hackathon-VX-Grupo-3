"""Compila o Excel do PDM em regras tipadas e falha ao encontrar algo que nao reconhece."""

import hashlib
import io
import re
from collections import defaultdict
from os import PathLike

from openpyxl import load_workbook

from domain.contracts import (
    ITEM_NAME_SUBJECT,
    Condition,
    ConditionOperator,
    IdentityMode,
    NcmReference,
    PdmAttribute,
    PdmCatalog,
    PdmClass,
)

DEFAULT_PDM_VERSION = "pdm-kit-v1"

_ALWAYS = Condition()
_ALWAYS_TEXTS = frozenset({"sempre", "quando informado pelo fabricante"})


def _equals(subject: str, value: str) -> Condition:
    return Condition(ConditionOperator.EQUALS, subject, (value,))


def _in(subject: str, *values: str) -> Condition:
    return Condition(ConditionOperator.IN, subject, values)


def _not_in(subject: str, *values: str) -> Condition:
    return Condition(ConditionOperator.NOT_IN, subject, values)


# Mapa explicito da coluna QUANDO_SE_APLICA: texto novo no Excel exige decisao humana.
_CONDITIONS: dict[tuple[str, str], Condition] = {
    ("PDM050", "somente FLANGE"): _equals(ITEM_NAME_SUBJECT, "FLANGE"),
    ("PDM050", "somente TE REDUCAO, LUVA REDUCAO e BUCHA REDUCAO"): _in(
        ITEM_NAME_SUBJECT, "TE REDUCAO", "LUVA REDUCAO", "BUCHA REDUCAO"
    ),
    ("PDM050", "todas, exceto FLANGE"): _not_in(ITEM_NAME_SUBJECT, "FLANGE"),
    ("PDM050", "todas, exceto conexões para solda de topo (BW)"): _not_in("CONEXAO", "SOLDA TOPO BW"),
    ("PDM050", "somente conexões para solda de topo (BW)"): _equals("CONEXAO", "SOLDA TOPO BW"),
    ("PDM060", "somente cabos de 1 condutor"): _equals("NUMERO CONDUTORES", "1"),
    ("PDM061", "somente terminais de OLHAL e FORQUILHA"): _in(
        "TIPO", "COMPRESSAO OLHAL", "PRE-ISOLADO OLHAL", "PRE-ISOLADO FORQUILHA"
    ),
    ("PDM062", "somente MINIDISJUNTOR DIN e CAIXA MOLDADA"): _in("TIPO", "MINIDISJUNTOR DIN", "CAIXA MOLDADA"),
    ("PDM062", "somente MINIDISJUNTOR DIN"): _equals("TIPO", "MINIDISJUNTOR DIN"),
    ("PDM062", "somente disjuntor MOTOR"): _equals("TIPO", "MOTOR"),
    ("PDM070", "somente VAQUETA e RASPA"): _in("MATERIAL", "VAQUETA", "RASPA"),
    ("PDM081", "somente CORTE e DESBASTE"): _in("TIPO", "CORTE", "DESBASTE"),
    ("PDM081", "somente FLAP"): _equals("TIPO", "FLAP"),
}

_IDENTITY_MODES = {
    "ESPECIFICACAO TECNICA (ATRIBUTOS OBRIGATORIOS)": IdentityMode.TECHNICAL_ATTRIBUTES,
    "REFERENCIA DO FABRICANTE (FABRICANTE + PART NUMBER)": IdentityMode.MANUFACTURER_REFERENCE,
}

_REQUIRED_FLAGS = {"S": True, "N": False}
_NOUN_SHEET = re.compile(r"\(ver aba (SUBSTANTIVOS_\w+)\)")
_NCM_CODE = re.compile(r"\d{4}\.\d{2}\.\d{2}")


class PdmLoadError(ValueError):
    """O arquivo do PDM nao corresponde ao formato esperado."""


def load_pdm(path: str | PathLike[str], version: str = DEFAULT_PDM_VERSION) -> PdmCatalog:
    with open(path, "rb") as source:
        content = source.read()
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        attributes = _read_attributes(workbook)
        ncm_references = _read_ncm_references(workbook)
        groups = {row["GRUPO_MERCADORIA"] for row in _rows(workbook, "GRUPOS_MERCADORIA", ["GRUPO_MERCADORIA"])}
        units = {row["UNIDADE"] for row in _rows(workbook, "UNIDADES", ["UNIDADE"])}
        classes = {}
        columns = ["ID_PDM", "SUBSTANTIVO", "QUALIFICADOR", "GRUPO_MERCADORIA", "UNIDADE_PADRAO", "CRITERIO_IDENTIDADE"]
        for row in _rows(workbook, "CLASSES", columns):
            pdm_class = _build_class(row, workbook, attributes, ncm_references, groups, units)
            if pdm_class.id in classes:
                raise PdmLoadError(f"Classe duplicada: {pdm_class.id}")
            classes[pdm_class.id] = pdm_class
    finally:
        workbook.close()

    orphans = (attributes.keys() | ncm_references.keys()) - classes.keys()
    if orphans:
        raise PdmLoadError(f"Regras de classes inexistentes: {sorted(orphans)}")
    return PdmCatalog(version, hashlib.sha256(content).hexdigest(), classes)


def _rows(workbook, sheet: str, columns: list[str]) -> list[dict[str, str | int | None]]:
    if sheet not in workbook.sheetnames:
        raise PdmLoadError(f"Aba ausente: {sheet}")
    rows = workbook[sheet].iter_rows(values_only=True)
    header = next(rows, ())
    missing = [column for column in columns if column not in header]
    if missing:
        raise PdmLoadError(f"Aba {sheet} sem as colunas: {missing}")
    parsed = []
    for values in rows:
        if any(value is not None for value in values):
            row = dict(zip(header, values, strict=False))
            parsed.append({k: v.strip() if isinstance(v, str) else v for k, v in row.items()})
    return parsed


def _read_attributes(workbook) -> dict[str, list[PdmAttribute]]:
    columns = ["ID_PDM", "ORDEM", "ATRIBUTO", "OBRIGATORIO", "QUANDO_SE_APLICA", "FORMATO", "VALORES_PERMITIDOS"]
    attributes: dict[str, list[PdmAttribute]] = defaultdict(list)
    for row in _rows(workbook, "ATRIBUTOS", columns):
        class_id = row["ID_PDM"]
        if row["OBRIGATORIO"] not in _REQUIRED_FLAGS:
            raise PdmLoadError(f"{class_id}/{row['ATRIBUTO']}: OBRIGATORIO invalido: {row['OBRIGATORIO']!r}")
        attributes[class_id].append(
            PdmAttribute(
                name=row["ATRIBUTO"],
                order=row["ORDEM"],
                required=_REQUIRED_FLAGS[row["OBRIGATORIO"]],
                applies_when=_parse_condition(class_id, row["ATRIBUTO"], row["QUANDO_SE_APLICA"]),
                format=row["FORMATO"],
                allowed_values=_split_values(row["VALORES_PERMITIDOS"]),
            )
        )
    return attributes


def _parse_condition(class_id: str, attribute: str, text: str | None) -> Condition:
    if text in _ALWAYS_TEXTS:
        return _ALWAYS
    try:
        return _CONDITIONS[(class_id, text)]
    except KeyError:
        raise PdmLoadError(f"{class_id}/{attribute}: condicao nao mapeada: {text!r}") from None


def _split_values(raw: str | None) -> tuple[str, ...] | None:
    return tuple(value.strip() for value in raw.split("|")) if raw else None


def _read_ncm_references(workbook) -> dict[str, list[NcmReference]]:
    references: dict[str, list[NcmReference]] = defaultdict(list)
    for row in _rows(workbook, "NCM_REFERENCIA", ["ID_PDM", "NCM", "REGRA"]):
        codes = tuple(code.strip() for code in row["NCM"].split(","))
        invalid = [code for code in codes if not _NCM_CODE.fullmatch(code)]
        if invalid:
            raise PdmLoadError(f"{row['ID_PDM']}: NCM invalido: {invalid}")
        references[row["ID_PDM"]].append(NcmReference(codes, row["REGRA"]))
    return references


def _build_class(row, workbook, attributes, ncm_references, groups, units) -> PdmClass:
    class_id = row["ID_PDM"]
    if row["GRUPO_MERCADORIA"] not in groups:
        raise PdmLoadError(f"{class_id}: grupo desconhecido: {row['GRUPO_MERCADORIA']!r}")
    if row["UNIDADE_PADRAO"] not in units:
        raise PdmLoadError(f"{class_id}: unidade desconhecida: {row['UNIDADE_PADRAO']!r}")
    if row["CRITERIO_IDENTIDADE"] not in _IDENTITY_MODES:
        raise PdmLoadError(f"{class_id}: criterio de identidade desconhecido: {row['CRITERIO_IDENTIDADE']!r}")
    if not attributes.get(class_id):
        raise PdmLoadError(f"{class_id}: classe sem atributos")
    if not ncm_references.get(class_id):
        raise PdmLoadError(f"{class_id}: classe sem NCM de referencia")

    noun, qualifiers, item_names = _parse_names(row["SUBSTANTIVO"], row["QUALIFICADOR"], workbook)
    ordered = tuple(sorted(attributes[class_id], key=lambda attribute: attribute.order))
    if len({attribute.order for attribute in ordered}) != len(ordered):
        raise PdmLoadError(f"{class_id}: ORDEM repetida nos atributos")
    if len({attribute.name for attribute in ordered}) != len(ordered):
        raise PdmLoadError(f"{class_id}: atributo repetido")
    _check_conditions(class_id, ordered, item_names)

    return PdmClass(
        id=class_id,
        noun=noun,
        qualifiers=qualifiers,
        item_names=item_names,
        group=row["GRUPO_MERCADORIA"],
        default_unit=row["UNIDADE_PADRAO"],
        identity_mode=_IDENTITY_MODES[row["CRITERIO_IDENTIDADE"]],
        attributes=ordered,
        ncm_references=tuple(ncm_references[class_id]),
    )


def _parse_names(noun: str, qualifier: str | None, workbook) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    sheet = _NOUN_SHEET.fullmatch(noun)
    if sheet:
        names = _rows(workbook, sheet[1], ["SUBSTANTIVO_E_QUALIFICADOR"])
        return None, (), tuple(row["SUBSTANTIVO_E_QUALIFICADOR"] for row in names)
    qualifiers = _split_values(qualifier) or ()
    return noun, qualifiers, tuple(f"{noun} {value}" for value in qualifiers) or (noun,)


def _check_conditions(class_id: str, attributes: tuple[PdmAttribute, ...], item_names: tuple[str, ...]) -> None:
    by_name = {attribute.name: attribute for attribute in attributes}
    for attribute in attributes:
        condition = attribute.applies_when
        if condition.operator is ConditionOperator.ALWAYS:
            continue
        if condition.subject == ITEM_NAME_SUBJECT:
            known = item_names
        elif condition.subject in by_name:
            known = by_name[condition.subject].allowed_values
        else:
            raise PdmLoadError(f"{class_id}/{attribute.name}: condicao usa atributo inexistente: {condition.subject}")
        unknown = [value for value in condition.values if known is not None and value not in known]
        if unknown:
            raise PdmLoadError(f"{class_id}/{attribute.name}: condicao usa valores inexistentes: {unknown}")
