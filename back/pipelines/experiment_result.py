"""Resultado do experimento manual x solução, a partir da chave e de uma ou duas planilhas (#207).

Regras iguais às da avaliação de desenvolvimento (#85): cada revisor tem nome, o mesmo nome não
conta como dois revisores, e discordância ou "NAO SEI" deixam o caso inconclusivo, sem voto de
maioria. Toda taxa traz numerador, denominador e intervalo de Wilson dos casos decididos.
"""

import json
import unicodedata
from datetime import datetime, time
from pathlib import Path

from openpyxl import load_workbook

from domain.evaluation import ratio, wilson95
from pipelines.experiment import (
    PACKAGE_CELL,
    REVIEWER_CELL,
    SCHEMA,
    SHEET_CORRECTIONS,
    SHEET_GUIDE,
    SHEET_MANUAL,
    SHEET_PAIRS,
    _pairs,
    package_id,
    workbook,
)

YES, NO = "SIM", "NAO"
SCOPE = (
    "Amostra do kit sintético do desafio, revisada às cegas pelos revisores nomeados. Não estima a precisão "
    "em produção nem a recuperação de todas as duplicidades da base."
)


class ExperimentError(ValueError):
    """Chave e planilha não pertencem ao mesmo pacote, ou o preenchimento é inválido."""


def _answer(value, allowed=(YES, NO, "NAO SEI")):
    if value in (None, ""):
        return None
    text = str(value).strip().upper().replace("Ã", "A")
    if text not in allowed:
        raise ExperimentError(f"Resposta inválida: {value}")
    return text


def _unsubstantiated(value, allowed=(YES, NO, "NAO SEI")):
    _answer(value, allowed)  # Reject invalid labels even when evidence is absent.
    return None


def _reviewer_key(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _has_evidence(value):
    return isinstance(value, str) and bool(value.strip())


def _validate_workbook(wb, key):
    expected = workbook(key)
    if wb.sheetnames != expected.sheetnames:
        raise ExperimentError("Abas diferentes do esquema congelado")
    specs = {SHEET_PAIRS: (2, 0, 2), SHEET_CORRECTIONS: (2, 0, 4), SHEET_MANUAL: (4, 1, 4)}
    for sheet in wb:
        original = expected[sheet.title]
        if (sheet.max_row, sheet.max_column) != (original.max_row, original.max_column):
            raise ExperimentError("Linhas/colunas diferentes do pacote")
        spec = specs.get(sheet.title)
        first = spec[0] if spec else original.max_row + 1
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    raise ExperimentError("Fórmula não permitida na planilha")
                if cell.row < first:
                    editable = (sheet.title == SHEET_GUIDE and cell.coordinate == REVIEWER_CELL) or (
                        sheet.title == SHEET_MANUAL and cell.coordinate in ("B1", "D1", "F1")
                    )
                    if not editable and cell.value != (original[cell.coordinate].value or None):
                        raise ExperimentError(f"Conteúdo protegido alterado: {sheet.title}!{cell.coordinate}")
        if spec:
            first, id_column, protected = spec
            expected_rows = {
                row[id_column]: row[:protected] for row in original.iter_rows(min_row=first, values_only=True)
            }
            seen = set()
            for row in sheet.iter_rows(min_row=first, values_only=True):
                case = row[id_column]
                if case in seen or case not in expected_rows or row[:protected] != expected_rows[case]:
                    raise ExperimentError("Caso duplicado, desconhecido ou conteúdo protegido alterado")
                seen.add(case)
            if seen != set(expected_rows):
                raise ExperimentError("Casos ausentes")


def _clock(value):
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    if isinstance(value, str) and ":" in value:
        hours, minutes = value.split(":")[:2]
        return int(hours) * 60 + int(minutes)
    return None


def read_sheet(path: str, key: dict) -> dict:
    wb = load_workbook(path, data_only=False)
    guide = wb[SHEET_GUIDE]
    if guide[PACKAGE_CELL].value != key["package_id"]:
        raise ExperimentError(f"{path}: planilha do pacote {guide[PACKAGE_CELL].value}, chave {key['package_id']}")
    _validate_workbook(wb, key)
    reviewer = str(guide[REVIEWER_CELL].value or "").strip()
    if not reviewer:
        raise ExperimentError(f"{path}: revisor sem nome na célula {REVIEWER_CELL}")
    pairs = {
        row[0]: {"label": _answer(row[2]) if _has_evidence(row[3]) else _unsubstantiated(row[2]), "evidence": row[3]}
        for row in wb[SHEET_PAIRS].iter_rows(min_row=2, values_only=True)
        if row[0]
    }
    corrections = {
        row[0]: {
            "correct": _answer(row[4]) if _has_evidence(row[6]) else _unsubstantiated(row[4]),
            "lost": _answer(row[5], (YES, NO)) if _has_evidence(row[6]) else _unsubstantiated(row[5], (YES, NO)),
            "note": row[6],
        }
        for row in wb[SHEET_CORRECTIONS].iter_rows(min_row=2, values_only=True)
        if row[0]
    }
    manual = wb[SHEET_MANUAL]
    groups = {
        str(row[1]): str(row[4]).strip()
        for row in manual.iter_rows(min_row=4, values_only=True)
        if row[1] and row[4] not in (None, "") and str(row[4]).strip()
    }
    if set(pairs) != set(key["pairs"]) or set(corrections) != set(key["corrections"]):
        raise ExperimentError(f"{path}: casos diferentes dos da chave")
    start, end = _clock(manual["B1"].value), _clock(manual["D1"].value)
    return {
        "reviewer": reviewer,
        "pairs": pairs,
        "corrections": corrections,
        "groups": groups,
        "minutes": end - start if start is not None and end is not None and end >= start else None,
    }


def combine(answers: list) -> tuple[str | None, str]:
    """Um revisor: o rótulo dele. Dois: só quando concordam; o resto fica inconclusivo."""
    if not answers or any(answer not in (YES, NO) for answer in answers):
        return None, "INCONCLUSIVE"
    if len(set(answers)) > 1:
        return None, "DISAGREEMENT"
    return answers[0], "AGREEMENT" if len(answers) > 1 else "SINGLE_REVIEW"


def rate(numerator: int, denominator: int) -> dict:
    return {**ratio(numerator, denominator), "interval": wilson95(numerator, denominator)}


def experiment_result(key_path: str, sheet_paths: list[str]) -> dict:
    key = json.loads(Path(key_path).read_text())
    if key.get("schema") != SCHEMA or package_id(key) != key.get("package_id"):
        raise ExperimentError("Chave de outro formato ou alterada depois de gerada")
    if not 1 <= len(sheet_paths) <= 2:
        raise ExperimentError("Informe uma ou duas planilhas preenchidas")
    reviews = [read_sheet(path, key) for path in sheet_paths]
    names = [_reviewer_key(review["reviewer"]) for review in reviews]
    if len(set(names)) != len(names):
        raise ExperimentError("O mesmo revisor não conta como dois")

    labels = {case: combine([r["pairs"][case]["label"] for r in reviews]) for case in key["pairs"]}
    parts = {"A": [], "B": []}
    for case, item in key["pairs"].items():
        parts[item["part"]].append(case)
    decided_a = [c for c in parts["A"] if labels[c][0]]
    decided_b = [c for c in parts["B"] if labels[c][0]]
    errors = [
        {
            "case": case,
            "part": key["pairs"][case]["part"],
            "codes": key["pairs"][case]["codes"],
            "system_same_item": key["pairs"][case]["system_same_item"],
            "evidence": [r["pairs"][case]["evidence"] for r in reviews],
        }
        for case in sorted(decided_a + decided_b)
        if (labels[case][0] == YES) != key["pairs"][case]["system_same_item"]
    ]
    correct = {c: combine([r["corrections"][c]["correct"] for r in reviews]) for c in key["corrections"]}
    lost = {c: combine([r["corrections"][c]["lost"] for r in reviews]) for c in key["corrections"]}
    decided_c = [c for c in key["corrections"] if correct[c][0]]
    decided_l = [c for c in key["corrections"] if lost[c][0]]

    manual = []
    for review in reviews:
        people: dict[str, list[str]] = {}
        for code, group in review["groups"].items():
            people.setdefault(group, []).append(code)
        person_pairs = set().union(*map(_pairs, people.values())) if people else set()
        system_pairs = {tuple(pair) for pair in key["system_merge_pairs"] if set(pair) <= set(review["groups"])}
        common = person_pairs & system_pairs
        minutes = review["minutes"]
        manual.append(
            {
                "reviewer": review["reviewer"],
                "materials_grouped": len(review["groups"]),
                "slice_size": len(key["slice"]),
                "minutes": minutes,
                "materials_per_minute": len(review["groups"]) / minutes if minutes else None,
                "duplicate_pairs": {
                    "person": len(person_pairs),
                    "system_among_grouped": len(system_pairs),
                    "both": len(common),
                },
            }
        )

    agreement = None
    if len(reviews) == 2:
        both = [c for c in key["pairs"] if all(r["pairs"][c]["label"] in (YES, NO) for r in reviews)]
        same = sum(reviews[0]["pairs"][c]["label"] == reviews[1]["pairs"][c]["label"] for c in both)
        agreement = ratio(same, len(both))

    return {
        "schema": SCHEMA,
        "independent_review_verified": False,
        "system_decision_kind": key["system_decision_kind"],
        "evaluation_kind": "BLIND_REVIEW_EXPERIMENT",
        "package_id": key["package_id"],
        "analysis_signature": key["analysis_signature"],
        "dataset_sha256": key["dataset_sha256"],
        "reviewers": [review["reviewer"] for review in reviews],
        "reviewer_agreement_on_pairs": agreement,
        "merges_proposed": {
            "precision": rate(sum(labels[c][0] == YES for c in decided_a), len(decided_a)),
            "inconclusive": len(parts["A"]) - len(decided_a),
        },
        "similar_pairs_not_merged": {
            "correctly_kept_apart": rate(sum(labels[c][0] == NO for c in decided_b), len(decided_b)),
            "missed_duplicates": sum(labels[c][0] == YES for c in decided_b),
            "inconclusive": len(parts["B"]) - len(decided_b),
        },
        "system_errors": errors,
        "lot_descriptions": {
            "correct": rate(sum(correct[c][0] == YES for c in decided_c), len(decided_c)),
            "lost_information": rate(sum(lost[c][0] == YES for c in decided_l), len(decided_l)),
            "inconclusive": len(key["corrections"]) - len(decided_c),
        },
        "manual_task": manual,
        "scope": SCOPE,
        "authorizes_merge": False,
    }
