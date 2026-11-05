"""Classificacao auditavel de CSVs, sem escrita na base mestre ou nos arquivos de entrada."""

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from domain.contracts import ClassificationInput, ClassificationStatus
from domain.pdm_loader import load_pdm
from repositories.classification import get_classification_repository

_COLUMNS = {
    "materials": ("CODIGO_MATERIAL", "DESCRICAO_LONGA", "DESCRICAO_CURTA", "GRUPO_MERCADORIA"),
    "orders": ("ID_PEDIDO", "TEXTO_SOLICITACAO", "CONTEUDO_ANEXO"),
}


def classification_report(path: str, pdm_path: str, input_kind: str, repository_name: str | None = None) -> dict:
    catalog = load_pdm(pdm_path)
    repository = get_classification_repository(catalog, repository_name)
    columns = _COLUMNS[input_kind]
    counts = Counter({status.value: 0 for status in ClassificationStatus})
    classes: Counter[str] = Counter()
    items = []
    with open(path, encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Colunas ausentes: {sorted(missing)}")
        for index, row in enumerate(reader, start=2):
            item = (
                ClassificationInput(row[columns[1]], row[columns[2]], row[columns[3]])
                if input_kind == "materials"
                else ClassificationInput(row[columns[1]], attachment_text=row[columns[2]])
            )
            result = repository.classify(item)
            counts[result.status.value] += 1
            if result.pdm_class_id:
                classes[result.pdm_class_id] += 1
            items.append({"source_id": row[columns[0]], "source_record": index, **asdict(result)})
    return {
        "repository": repository.name,
        "input_kind": input_kind,
        "input_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "rows": len(items),
        "counts": dict(counts),
        "classes": dict(sorted(classes.items())),
        "items": items,
    }


def classification_evaluation(path: str, pdm_path: str, repository_name: str | None = None) -> dict:
    """Mede precisao sobre rotulos independentes, sem trata-los como confianca do algoritmo."""
    sample = json.loads(Path(path).read_text(encoding="utf-8"))
    catalog = load_pdm(pdm_path)
    repository = get_classification_repository(catalog, repository_name)
    results = []
    predicted = correct = in_scope = correct_out_of_scope = false_out_of_scope = 0
    for case in sample["cases"]:
        expected = case["expected_class_id"]
        if expected is not None and expected not in catalog.classes:
            raise ValueError(f"Rotulo desconhecido: {expected}")
        result = repository.classify(ClassificationInput(**case["input"]))
        predicted += result.status is ClassificationStatus.CLASSIFIED
        correct += result.pdm_class_id is not None and result.pdm_class_id == expected
        in_scope += expected is not None
        correct_out_of_scope += expected is None and result.status is ClassificationStatus.OUT_OF_SCOPE
        false_out_of_scope += expected is not None and result.status is ClassificationStatus.OUT_OF_SCOPE
        results.append(
            {
                "id": case["id"],
                "expected_class_id": expected,
                "predicted_class_id": result.pdm_class_id,
                "status": result.status,
                "rule": result.rule,
            }
        )
    return {
        "repository": repository.name,
        "sample_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "label_method": sample["label_method"],
        "reviewed_items": len(results),
        "classified": predicted,
        "correctly_classified": correct,
        "precision": correct / predicted if predicted else None,
        "coverage": predicted / len(results) if results else None,
        "in_scope_recall": correct / in_scope if in_scope else None,
        "correct_out_of_scope": correct_out_of_scope,
        "false_out_of_scope": false_out_of_scope,
        "items": results,
    }
