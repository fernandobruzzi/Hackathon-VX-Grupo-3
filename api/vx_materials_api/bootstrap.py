"""Carga inicial: preserva os arquivos originais e carrega materiais e saldos.

Tudo é derivado do conteúdo dos arquivos, então repetir o comando não duplica nada. Os valores
entram como vieram: correções só acontecem depois, por propostas aprovadas.
"""

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from clients.storage import ObjectStore, get_object_store
from domain.pdm_loader import load_pdm
from vx_materials_api import settings
from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot, MaterialMaster, ReferenceVersion
from vx_materials_api.db.session import make_engine

MATERIALS_FILE = "01_base_materiais.csv"
ORDERS_FILE = "02_pedidos_cadastro.csv"
PDM_FILE = "03_padrao_cadastro_PDM.xlsx"

REAL_PRODUCTS = 15
SOURCE_SYSTEM = "ERP_KIT"
_NAMESPACE = uuid.UUID("5f2b1c9e-6c0a-4f6b-9d55-7a1e2c3d4b60")
# Empresa única do MVP.
TENANT_ID = uuid.uuid5(_NAMESPACE, "serra-azul")

_COLUMNS = {
    "CODIGO_MATERIAL",
    "DESCRICAO_CURTA",
    "DESCRICAO_LONGA",
    "UNIDADE_MEDIDA",
    "NCM",
    "FABRICANTE",
    "REFERENCIA_FABRICANTE",
    "CENTRO",
    "STATUS",
    "ESTOQUE_ATUAL",
    "PRECO_MEDIO_UNITARIO",
}
_REDIRECT = re.compile(r"USAR COD (\d+)")
_BATCH = 1000

REDIRECT_LINKED = "LEGACY_REDIRECT"
REDIRECT_INCONSISTENT = "LEGACY_REDIRECT_INCONSISTENT"


class BootstrapError(ValueError):
    """Os arquivos do kit não correspondem ao esperado."""


@dataclass(frozen=True)
class BootstrapResult:
    dataset_id: str
    manifest_key: str
    materials: int
    materials_inserted: int
    snapshots_inserted: int
    statuses: dict[str, int]
    redirects: dict[str, int]
    real_material_codes: list[str]


def _empty_to_none(value: str) -> str | None:
    return value or None


def _material_id(code: str) -> uuid.UUID:
    return uuid.uuid5(TENANT_ID, code)


def read_materials(content: bytes) -> list[dict[str, str]]:
    """Lê a base, guardando a linha da planilha original: cabeçalho na 1, primeiro registro na 2."""
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline="")))
    if not rows:
        raise BootstrapError(f"{MATERIALS_FILE} sem registros")
    missing = _COLUMNS - rows[0].keys()
    if missing:
        raise BootstrapError(f"{MATERIALS_FILE} sem as colunas: {sorted(missing)}")
    codes = Counter(row["CODIGO_MATERIAL"] for row in rows)
    repeated = [code for code, count in codes.items() if count > 1]
    if repeated:
        raise BootstrapError(f"Codigos repetidos em {MATERIALS_FILE}: {repeated[:5]}")
    if len(rows) < REAL_PRODUCTS:
        raise BootstrapError(f"{MATERIALS_FILE} tem menos de {REAL_PRODUCTS} registros")
    return rows


def resolve_redirect(row: dict[str, str], statuses: dict[str, str]) -> tuple[str | None, str | None]:
    """Interpreta `USAR COD x` de um bloqueado, devolvendo (código de destino, motivo do bloqueio).

    Só vira vínculo o que aponta direto para um ativo. O resto fica sem destino, como pendência
    de revisão, e o texto original continua como evidência.
    """
    if row["STATUS"] != "BLOQUEADO":
        return None, None
    match = _REDIRECT.search(row["DESCRICAO_LONGA"])
    if not match:
        return None, None
    target = match[1]
    if target != row["CODIGO_MATERIAL"] and statuses.get(target) == "ATIVO":
        return target, REDIRECT_LINKED
    return None, REDIRECT_INCONSISTENT


def _material_values(row: dict[str, str], target: str | None, reason: str | None) -> dict:
    code = row["CODIGO_MATERIAL"]
    return {
        "id": _material_id(code),
        "tenant_id": TENANT_ID,
        "source_system": SOURCE_SYSTEM,
        "material_code": code,
        "status": row["STATUS"],
        "block_reason": reason,
        "active_code_target": _material_id(target) if target else None,
        "original_description_short": _empty_to_none(row["DESCRICAO_CURTA"]),
        "original_description_long": _empty_to_none(row["DESCRICAO_LONGA"]),
        "manufacturer": _empty_to_none(row["FABRICANTE"]),
        "manufacturer_reference": _empty_to_none(row["REFERENCIA_FABRICANTE"]),
        "unit": _empty_to_none(row["UNIDADE_MEDIDA"]),
        "ncm": _empty_to_none(row["NCM"]),
    }


def _snapshot_values(row: dict[str, str], line: int, dataset_id: uuid.UUID) -> dict:
    quantity = Decimal(row["ESTOQUE_ATUAL"])
    price = Decimal(row["PRECO_MEDIO_UNITARIO"])
    return {
        "id": uuid.uuid5(dataset_id, str(line)),
        "tenant_id": TENANT_ID,
        "dataset_id": dataset_id,
        "material_id": _material_id(row["CODIGO_MATERIAL"]),
        "center_code": row["CENTRO"].split(" - ", 1)[0],
        "quantity": quantity,
        "unit": _empty_to_none(row["UNIDADE_MEDIDA"]),
        "unit_price": price,
        "total_value": quantity * price,
        "source_line": line,
        "raw_record": row,
    }


def _store_files(
    store: ObjectStore, dataset_id: uuid.UUID, contents: dict[str, bytes], row_counts: dict[str, int], pdm_version: str
) -> list[dict]:
    files = []
    for name, content in contents.items():
        stored = store.put_if_absent(f"raw/{dataset_id}/{name}", content)
        files.append(
            {
                "name": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "rows": row_counts.get(name),
                "object_key": stored.key,
                "version_id": stored.version_id,
            }
        )
    store.put_if_absent(f"references/pdm/{pdm_version}/{PDM_FILE}", contents[PDM_FILE])
    return files


def _insert_batches(connection, model, values: list[dict], constraint_columns: list[str]) -> int:
    inserted = 0
    for start in range(0, len(values), _BATCH):
        statement = insert(model).on_conflict_do_nothing(index_elements=constraint_columns).returning(model.id)
        inserted += len(connection.execute(statement, values[start : start + _BATCH]).all())
    return inserted


def bootstrap(data_dir: str | Path, engine: Engine, store: ObjectStore) -> BootstrapResult:
    directory = Path(data_dir)
    contents = {name: (directory / name).read_bytes() for name in (MATERIALS_FILE, ORDERS_FILE, PDM_FILE)}

    rows = read_materials(contents[MATERIALS_FILE])
    orders = list(csv.DictReader(io.StringIO(contents[ORDERS_FILE].decode("utf-8-sig"), newline="")))
    catalog = load_pdm(directory / PDM_FILE)
    real_codes = [row["CODIGO_MATERIAL"] for row in rows[-REAL_PRODUCTS:]]

    digests = [hashlib.sha256(content).hexdigest() for content in contents.values()]
    dataset_id = uuid.uuid5(_NAMESPACE, "|".join(digests))
    row_counts = {MATERIALS_FILE: len(rows), ORDERS_FILE: len(orders)}

    files = _store_files(store, dataset_id, contents, row_counts, catalog.version)
    manifest = {
        "dataset_id": str(dataset_id),
        "tenant_id": str(TENANT_ID),
        "pdm_version": catalog.version,
        "files": files,
        "real_material_codes": real_codes,
    }
    manifest_key = f"raw/{dataset_id}/manifest.json"
    store.put_if_absent(manifest_key, json.dumps(manifest, indent=2, sort_keys=True).encode())

    statuses = {row["CODIGO_MATERIAL"]: row["STATUS"] for row in rows}
    plain, linked = [], []
    redirects: Counter[str] = Counter()
    for row in rows:
        target, reason = resolve_redirect(row, statuses)
        if reason:
            redirects[reason] += 1
        (linked if target else plain).append(_material_values(row, target, reason))
    snapshots = [_snapshot_values(row, line, dataset_id) for line, row in enumerate(rows, start=2)]

    # Uma transação só: uma falha nunca deixa a carga pela metade.
    with engine.begin() as connection:
        connection.execute(
            insert(Dataset)
            .values(id=dataset_id, tenant_id=TENANT_ID, files=files, real_material_codes=real_codes)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        connection.execute(
            insert(ReferenceVersion)
            .values(
                kind="PDM",
                version=catalog.version,
                source_hash=catalog.source_sha256,
                s3_path=f"references/pdm/{catalog.version}/{PDM_FILE}",
                validation_status="VALIDATED",
            )
            .on_conflict_do_nothing(index_elements=["kind", "version"])
        )
        # Materiais com destino por último: a chave estrangeira exige que o destino já exista.
        key = ["tenant_id", "material_code"]
        materials_inserted = _insert_batches(connection, MaterialMaster, plain, key)
        materials_inserted += _insert_batches(connection, MaterialMaster, linked, key)
        snapshots_inserted = _insert_batches(
            connection, MaterialInventorySnapshot, snapshots, ["dataset_id", "source_line"]
        )
        stored_snapshots = connection.execute(
            select(func.count())
            .select_from(MaterialInventorySnapshot)
            .where(MaterialInventorySnapshot.dataset_id == dataset_id)
        ).scalar_one()
        if stored_snapshots != len(rows):
            raise BootstrapError(f"Esperados {len(rows)} saldos, encontrados {stored_snapshots}")

    return BootstrapResult(
        dataset_id=str(dataset_id),
        manifest_key=manifest_key,
        materials=len(rows),
        materials_inserted=materials_inserted,
        snapshots_inserted=snapshots_inserted,
        statuses=dict(sorted(Counter(statuses.values()).items())),
        redirects=dict(sorted(redirects.items())),
        real_material_codes=real_codes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vx-bootstrap", description="Carrega o kit de dados")
    parser.add_argument("--data-dir", default=settings.data_dir(), help="Pasta com os arquivos do kit")
    args = parser.parse_args(argv)
    engine = make_engine()
    try:
        result = bootstrap(args.data_dir, engine, get_object_store())
    finally:
        engine.dispose()
    json.dump(asdict(result), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
