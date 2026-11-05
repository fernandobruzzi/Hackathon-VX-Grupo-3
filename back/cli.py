"""CLI do pipeline batch."""

import argparse
import csv
import json
import sys
from collections import Counter

from domain.contracts import NormalizedField
from pipelines.classify import classification_evaluation, classification_report
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
    classify = commands.add_parser(
        "classification-report", help="Classifica cada material ou pedido sem alterar a base"
    )
    classify.add_argument("csv_path")
    classify.add_argument("--input-kind", choices=["materials", "orders"], required=True)
    classify.add_argument("--pdm-workbook", required=True)
    classify.add_argument("--repository", help="Padrao: CLASSIFICATION_REPOSITORY ou rule_based_v1")
    evaluate = commands.add_parser("classification-evaluate", help="Mede precisao e cobertura na amostra rotulada")
    evaluate.add_argument("sample_path")
    evaluate.add_argument("--pdm-workbook", required=True)
    evaluate.add_argument("--repository")
    args = parser.parse_args(argv)

    if args.command == "normalization-report":
        result = normalization_report(args.csv_path, args.repository)
    elif args.command == "classification-report":
        result = classification_report(args.csv_path, args.pdm_workbook, args.input_kind, args.repository)
    else:
        result = classification_evaluation(args.sample_path, args.pdm_workbook, args.repository)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
