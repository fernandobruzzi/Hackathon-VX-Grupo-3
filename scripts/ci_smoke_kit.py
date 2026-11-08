"""Prepara um recorte determinístico do kit para o smoke de integração."""

import argparse
import csv
import shutil
from pathlib import Path

REAL_PRODUCTS = 15
MATERIAL_CODES = {"10015478", "22917812", "10213740", "10179749"}
ORDER_ID = "SC-202600001"
PDM = "03_padrao_cadastro_PDM.xlsx"


def copy_rows(source: Path, target: Path, column: str, keys: set[str], *, tail: int = 0) -> None:
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        source_rows = list(reader)
    rows = [row for row in source_rows if row[column] in keys]
    if len(rows) != len(keys) or {row[column] for row in rows} != keys:
        raise ValueError(f"Recorte incompleto ou duplicado em {source.name}")
    if tail:
        retained = source_rows[-tail:]
        if len(retained) != tail or keys.intersection(row[column] for row in retained):
            raise ValueError(f"Os produtos reais se sobrepõem ao recorte de {source.name}")
        rows.extend(retained)
    with target.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_kit(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    materials = "01_base_materiais.csv"
    orders = "02_pedidos_cadastro.csv"
    # Dois pares da demo: um técnico e outro que passa também pelo Fiscal.
    copy_rows(source / materials, target / materials, "CODIGO_MATERIAL", MATERIAL_CODES, tail=REAL_PRODUCTS)
    copy_rows(source / orders, target / orders, "ID_PEDIDO", {ORDER_ID})
    shutil.copyfile(source / PDM, target / PDM)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    create_kit(args.source, args.target)
