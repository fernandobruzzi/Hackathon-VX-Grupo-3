"""Resultado do experimento manual x solução, a partir da chave e de uma ou duas planilhas (#207).

Regras iguais às da avaliação de desenvolvimento (#85): cada revisor tem nome, o mesmo nome não
conta como dois revisores, e discordância ou "NAO SEI" deixam o caso inconclusivo, sem voto de
maioria. Toda taxa traz numerador, denominador e intervalo de Wilson dos casos decididos.
"""

import json
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
)

YES, NO = "SIM", "NAO"
SCOPE = (
    "Amostra do kit sintético do desafio, revisada às cegas pelos revisores nomeados. Não estima a precisão "
    "em produção nem a recuperação de todas as duplicidades da base."
)


class ExperimentError(ValueError):
    """Chave e planilha não pertencem ao mesmo pacote, ou o preenchimento é inválido."""


def _answer(value):
    if value in (None, ""):
        return None
    text = str(value).strip().upper().replace("Ã", "A")
    return {"SIM": YES, "NAO": NO, "NAO SEI": "NAO SEI"}.get(text, text)


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
    wb = load_workbook(path, data_only=True)
    guide = wb[SHEET_GUIDE]
    if guide[PACKAGE_CELL].value != key["package_id"]:
        raise ExperimentError(f"{path}: planilha do pacote {guide[PACKAGE_CELL].value}, chave {key['package_id']}")
    reviewer = str(guide[REVIEWER_CELL].value or "").strip()
    if not reviewer:
        raise ExperimentError(f"{path}: revisor sem nome na célula {REVIEWER_CELL}")
    pairs = {
        row[0]: {"label": _answer(row[2]), "evidence": row[3]}
        for row in wb[SHEET_PAIRS].iter_rows(min_row=2, values_only=True)
        if row[0]
    }
    corrections = {
        row[0]: {"correct": _answer(row[4]), "lost": _answer(row[5]), "note": row[6]}
        for row in wb[SHEET_CORRECTIONS].iter_rows(min_row=2, values_only=True)
        if row[0]
    }
    manual = wb[SHEET_MANUAL]
    groups = {
        str(row[1]): str(row[4]).strip()
        for row in manual.iter_rows(min_row=4, values_only=True)
        if row[1] and row[4] not in (None, "")
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
    if any(answer in (None, "NAO SEI") for answer in answers):
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
    names = [review["reviewer"].casefold() for review in reviews]
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
        system: dict[str, list[str]] = {}
        for code, group in review["groups"].items():
            people.setdefault(group, []).append(code)
            identity = key["slice"][code]["identity_key"]
            if identity:
                system.setdefault(identity, []).append(code)
        person_pairs = set().union(*map(_pairs, people.values())) if people else set()
        system_pairs = set().union(*map(_pairs, system.values())) if system else set()
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
