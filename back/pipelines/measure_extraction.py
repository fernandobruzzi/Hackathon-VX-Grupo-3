"""Mede a extração na base inteira: quantos materiais ficam completos, por grupo e por campo faltante.

Rodar em back/: `uv run python -m pipelines.measure_extraction`.

Usa o classificador real, então materiais sem classe contam contra a cobertura. Esse número é um
indicativo, não a precisão da extração.
"""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from domain.contracts import ClassificationInput, ClassificationRepository, PdmCatalog, PdmClass, ValidationStatus
from domain.pdm_loader import load_pdm
from domain.pdm_validator import is_valid_value, validate_pdm
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository

DATA = Path(__file__).parents[2] / "data" / "desafio01"
_REDIRECT = re.compile(r"USAR COD (\d+)\s*-\s*(.*)")
_REDIRECT_PREFIX = re.compile(r"^NAO UTILIZAR - USAR COD \d+\s*-\s*")


@dataclass(frozen=True)
class Row:
    code: str
    description: str
    group: str
    manufacturer: str
    reference: str
    status: str = ""


def read_rows(path: Path = DATA / "01_base_materiais.csv") -> list[Row]:
    with open(path, encoding="utf-8-sig", newline="") as source:
        return [
            Row(
                row["CODIGO_MATERIAL"],
                row["DESCRICAO_LONGA"],
                row["GRUPO_MERCADORIA"],
                row["FABRICANTE"],
                row["REFERENCIA_FABRICANTE"],
                row["STATUS"],
            )
            for row in csv.DictReader(source)
        ]


def classify_row(
    catalog: PdmCatalog, classifier: ClassificationRepository, row: Row
) -> tuple[PdmClass, str | None] | None:
    """Classe e item, pelo mesmo classificador do saneamento."""
    description = _REDIRECT_PREFIX.sub("", row.description)
    result = classifier.classify(ClassificationInput(description, None, row.group))
    if result.pdm_class_id is None:
        return None
    pdm_class = catalog.classes[result.pdm_class_id]
    if len(pdm_class.item_names) == 1:
        return pdm_class, pdm_class.item_names[0]
    names = [evidence.matched_name for evidence in result.evidence if evidence.matched_name in pdm_class.item_names]
    return pdm_class, max(names, key=len) if names else None


def measure(catalog: PdmCatalog, rows: list[Row], repository_name: str | None = None) -> dict:
    repository = get_extraction_repository(repository_name)
    classifier = get_classification_repository(catalog)
    statuses: Counter[str] = Counter()
    by_group: dict[str, Counter[str]] = defaultdict(Counter)
    missing: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    invalid_values = 0
    for row in rows:
        classified = classify_row(catalog, classifier, row)
        if classified is None:
            statuses["SEM_CLASSE"] += 1
            by_group[row.group]["SEM_CLASSE"] += 1
            continue
        pdm_class, item = classified
        known = {a.name: a for a in pdm_class.attributes}
        result = repository.extract(
            pdm_class,
            row.description,
            manufacturer=row.manufacturer or None,
            manufacturer_reference=row.reference or None,
        )
        for name, extracted in result.attributes.items():
            rules[extracted.rule] += 1
            invalid_values += not is_valid_value(known[name], extracted.value)
        validation = validate_pdm(
            catalog, pdm_class.id, {n: a.value for n, a in result.attributes.items()}, item_name=item
        )
        statuses[validation.status.value] += 1
        by_group[row.group][validation.status.value] += 1
        missing.update(f"{pdm_class.id}/{m.name}" for m in validation.missing_attributes)
    return {
        "repository": repository.name,
        "rows": len(rows),
        "statuses": dict(statuses.most_common()),
        "valid_percent": round(100 * statuses[ValidationStatus.VALID.value] / len(rows), 1),
        "invalid_values": invalid_values,
        "by_group": {group: dict(counts.most_common()) for group, counts in sorted(by_group.items())},
        "top_missing": dict(missing.most_common(20)),
        "rules": dict(rules.most_common()),
    }


def _reference_key(value: str) -> str:
    """Compara referências como a identidade compara, ignorando separadores, `-00` e `REV x`."""
    return re.sub(r"[\s.\-/]", "", re.sub(r"(?:-00|\s+REV [A-Z])$", "", value))


def measure_against_columns(catalog: PdmCatalog, rows: list[Row], repository_name: str | None = None) -> dict:
    """Extrai só da descrição, escondendo as colunas, e usa as colunas como gabarito."""
    repository = get_extraction_repository(repository_name)
    classifier = get_classification_repository(catalog)
    report = {}
    for attribute, column, same in (
        ("FABRICANTE", "manufacturer", str.__eq__),
        ("REFERENCIA FABRICANTE", "reference", lambda a, b: _reference_key(a) == _reference_key(b)),
    ):
        total = filled = correct = 0
        for row in rows:
            truth = getattr(row, column)
            if not truth or row.group not in ("FIL01", "SOB01"):
                continue
            classified = classify_row(catalog, classifier, row)
            if classified is None or attribute not in {a.name for a in classified[0].attributes}:
                continue
            total += 1
            extracted = repository.extract(classified[0], row.description).attributes.get(attribute)
            if extracted:
                filled += 1
                correct += bool(same(extracted.value, truth))
        report[attribute] = {
            "rows": total,
            "filled": filled,
            "correct": correct,
            "coverage_percent": round(100 * filled / total, 1) if total else 0,
            "precision_percent": round(100 * correct / filled, 1) if filled else 0,
        }
    return report


def measure_known_pairs(catalog: PdmCatalog, rows: list[Row], repository_name: str | None = None) -> dict:
    """Pares `USAR COD x` apontando para um ativo: a própria base diz que são o mesmo item.

    Mede duplicidades encontradas. Não mede junções erradas, que exigem pares revisados por pessoas.
    """
    repository = get_extraction_repository(repository_name)
    classifier = get_classification_repository(catalog)
    by_code = {row.code: row for row in rows}

    def identity(row: Row, description: str) -> tuple[str | None, str | None]:
        classified = classify_row(catalog, classifier, replace(row, description=description))
        if classified is None:
            return None, None
        pdm_class, item = classified
        result = repository.extract(
            pdm_class,
            description,
            manufacturer=row.manufacturer or None,
            manufacturer_reference=row.reference or None,
        )
        attributes = {name: value.value for name, value in result.attributes.items()}
        return pdm_class.id, validate_pdm(catalog, pdm_class.id, attributes, item_name=item).identity_key

    report = Counter({"pairs": 0, "same_identity": 0, "different_identity": 0, "undecided": 0})
    for row in rows:
        match = _REDIRECT.search(row.description)
        target = by_code.get(match[1]) if match else None
        if target is None or target.code == row.code or target.status != "ATIVO":
            continue
        report["pairs"] += 1
        first_class, first = identity(row, match[2])
        second_class, second = identity(target, target.description)
        if first is None or second is None or first_class != second_class:
            report["undecided"] += 1
        elif first == second:
            report["same_identity"] += 1
        else:
            report["different_identity"] += 1
    return dict(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mede a extracao de atributos na base inteira")
    parser.add_argument("--repository", help="Algoritmo; padrao: EXTRACTION_REPOSITORY ou rule_based_v1")
    args = parser.parse_args()
    catalog = load_pdm(DATA / "03_padrao_cadastro_PDM.xlsx")
    rows = read_rows()
    report = measure(catalog, rows, args.repository)
    report["against_columns"] = measure_against_columns(catalog, rows, args.repository)
    report["known_pairs"] = measure_known_pairs(catalog, rows, args.repository)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
