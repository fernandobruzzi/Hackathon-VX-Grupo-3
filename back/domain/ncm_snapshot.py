"""Tabela NCM versionada, independente das regras de coerência técnica do PDM (#22)."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType

from repositories.normalization import get_normalization_repository

OFFICIAL_NCM_URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"
# O endereço publicado responde 307 para o mesmo recurso com o perfil público (verificado em
# 08/11/2026). Só esse destino exato é seguido; qualquer outro redirecionamento é recusado.
OFFICIAL_NCM_REDIRECT_URL = f"{OFFICIAL_NCM_URL}?perfil=PUBLICO"
MAX_SNAPSHOT_BYTES = 20 * 1024 * 1024


class NcmSnapshotError(ValueError):
    """Arquivo ou registro de snapshot inválido; não há resultado fiscal seguro."""


class NcmSourceKind(StrEnum):
    OFFICIAL_DOWNLOAD = "OFFICIAL_DOWNLOAD"
    IMPORTED_UNVERIFIED = "IMPORTED_UNVERIFIED"
    SIMULATED = "SIMULATED"


@dataclass(frozen=True)
class NcmRecord:
    code: str
    description: str
    valid_from: date
    valid_until: date


@dataclass(frozen=True)
class NcmSnapshot:
    version: str
    source_sha256: str
    snapshot_date: date
    source_kind: NcmSourceKind
    source_last_update: str
    records: Mapping[str, NcmRecord]
    hierarchy: Mapping[str, NcmRecord] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class NcmSnapshotCheck:
    input_ncm: str | None
    normalized_ncm: str | None
    syntax_valid: bool
    exists_in_snapshot: bool
    valid_in_snapshot: bool
    requires_fiscal_review: bool
    reasons: tuple[str, ...]
    ncm_version: str
    source_sha256: str
    snapshot_date: date
    source_kind: NcmSourceKind
    rule_id: str = "ncm_snapshot_v1/existence_and_validity"


def validate_ncm_version(version: str) -> None:
    if not isinstance(version, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}", version):
        raise NcmSnapshotError("Versao NCM invalida")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NcmSnapshotError(f"Campo {field} ausente ou invalido")
    return value.strip()


def _date(value: object, field: str) -> date:
    text = _text(value, field)
    if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", text):
        raise NcmSnapshotError(f"Data invalida em {field}: {text}")
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError as error:
        raise NcmSnapshotError(f"Data invalida em {field}: {text}") from error


def load_ncm_snapshot(
    raw: bytes,
    *,
    snapshot_date: date,
    version: str | None = None,
    source_kind: NcmSourceKind = NcmSourceKind.IMPORTED_UNVERIFIED,
) -> NcmSnapshot:
    """Importa bytes sem presumir autenticidade nem usar o relógio na vigência.

    OFFICIAL_DOWNLOAD é reservado ao cliente HTTPS; importar um arquivo local
    não comprova sua procedência. O hash cobre os bytes originais, incluindo BOM.
    """
    if not raw or len(raw) > MAX_SNAPSHOT_BYTES:
        raise NcmSnapshotError("Snapshot vazio ou maior que 20 MiB")
    if type(snapshot_date) is not date:
        raise NcmSnapshotError("Data do snapshot deve ser uma data explicita")
    source_kind = NcmSourceKind(source_kind)
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as error:
        raise NcmSnapshotError("Snapshot deve ser JSON UTF-8 valido") from error
    if not isinstance(payload, dict):
        raise NcmSnapshotError("Snapshot deve ser um objeto JSON")
    updated = _text(payload.get("Data_Ultima_Atualizacao_NCM"), "Data_Ultima_Atualizacao_NCM")
    # A data de atualização pode ser anterior à captura. "Vigente em" declara
    # a data de cobertura da tabela diária e precisa coincidir com o snapshot.
    if updated.startswith("Vigente em "):
        if _date(updated.removeprefix("Vigente em "), "Data_Ultima_Atualizacao_NCM") != snapshot_date:
            raise NcmSnapshotError("Data do snapshot diverge da cobertura declarada no arquivo")
    else:
        if _date(updated, "Data_Ultima_Atualizacao_NCM") > snapshot_date:
            raise NcmSnapshotError("Atualizacao posterior a data do snapshot")
    rows = payload.get("Nomenclaturas")
    if not isinstance(rows, list) or not rows:
        raise NcmSnapshotError("Nomenclaturas deve ser uma lista nao vazia")
    records: dict[str, NcmRecord] = {}
    hierarchy: dict[str, NcmRecord] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise NcmSnapshotError(f"Nomenclatura {index} invalida")
        code = _text(row.get("Codigo"), "Codigo")
        # A exportação também inclui capítulos (01), posições (01.01), subposições (0101.2,
        # 0101.21) e itens (0101.21.0); só os códigos de oito dígitos são NCM completos.
        if not re.fullmatch(r"[0-9]{2}(?:\.[0-9]{2})?|[0-9]{4}(?:\.[0-9]{1,2}(?:\.[0-9]{1,2})?)?", code):
            raise NcmSnapshotError(f"Codigo de nomenclatura invalido: {code}")
        description = _text(row.get("Descricao"), "Descricao")
        start = _date(row.get("Data_Inicio"), "Data_Inicio")
        end = _date(row.get("Data_Fim"), "Data_Fim")
        if start > end:
            raise NcmSnapshotError(f"Vigencia invertida: {code}")
        digits = code.replace(".", "")
        if len(digits) != 8:
            if digits in hierarchy:
                raise NcmSnapshotError(f"Codigo duplicado no snapshot: {code}")
            hierarchy[digits] = NcmRecord(code, description, start, end)
            continue
        normalized = f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"
        if normalized in records:
            raise NcmSnapshotError(f"Codigo duplicado no snapshot: {normalized}")
        records[normalized] = NcmRecord(normalized, description, start, end)
    if not records:
        raise NcmSnapshotError("Snapshot sem codigos NCM de oito digitos")
    digest = hashlib.sha256(raw).hexdigest()
    version = version if version is not None else f"ncm-{snapshot_date.isoformat()}-{digest[:12]}"
    validate_ncm_version(version)
    return NcmSnapshot(
        version, digest, snapshot_date, source_kind, updated, MappingProxyType(records), MappingProxyType(hierarchy)
    )


def check_snapshot_ncm(snapshot: NcmSnapshot, raw_code: str | None) -> NcmSnapshotCheck:
    """Só comprova existência/vigência; coerência PDM e aprovação são separadas."""
    normalized = get_normalization_repository("rule_based_v1").normalize_ncm(raw_code).value
    if normalized is not None and not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}", normalized):
        normalized = None
    record = snapshot.records.get(normalized) if normalized else None
    valid = bool(record and record.valid_from <= snapshot.snapshot_date <= record.valid_until)
    reasons = []
    if not normalized:
        reasons.append("NCM_INVALID_FORMAT")
    elif record is None:
        reasons.append("NCM_NOT_IN_SNAPSHOT")
    elif not valid:
        reasons.append("NCM_NOT_EFFECTIVE_IN_SNAPSHOT")
    if snapshot.source_kind != NcmSourceKind.OFFICIAL_DOWNLOAD:
        reasons.append("NCM_SOURCE_UNVERIFIED")
    return NcmSnapshotCheck(
        raw_code,
        normalized,
        normalized is not None,
        record is not None,
        valid,
        bool(reasons),
        tuple(reasons),
        snapshot.version,
        snapshot.source_sha256,
        snapshot.snapshot_date,
        snapshot.source_kind,
    )
