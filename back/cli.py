"""CLI do pipeline batch."""

import argparse
import csv
import json
import sys
from collections import Counter

from domain.contracts import NormalizedField
from repositories.normalization import get_normalization_repository


def normalization_report(path: str, repository_name: str | None) -> dict:
    """Conta o resultado da normalizacao na base 01, sem alterar nenhum dado."""
    repository = get_normalization_repository(repository_name)
    fields = {
        "ncm": ("NCM", repository.normalize_ncm),
        "unit": ("UNIDADE_MEDIDA", repository.normalize_unit),
        "text": ("DESCRICAO_LONGA", repository.normalize_text),
    }
    counts: dict[str, Counter] = {field: Counter() for field in fields}
    rows = 0
    with open(path, encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            rows += 1
            for field, (column, normalize) in fields.items():
                result: NormalizedField = normalize(row[column])
                counts[field][f"{result.status.value} {result.rule}"] += 1
    return {
        "repository": repository.name,
        "rows": rows,
        "fields": {field: dict(sorted(c.items())) for field, c in counts.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vx-back")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("normalization-report", help="Resume a normalizacao da base de materiais")
    report.add_argument("csv_path", help="Caminho de 01_base_materiais.csv")
    report.add_argument("--repository", help="Algoritmo; padrao: NORMALIZATION_REPOSITORY ou rule_based_v1")
    args = parser.parse_args(argv)

    json.dump(normalization_report(args.csv_path, args.repository), sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
