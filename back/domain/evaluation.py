"""Contagens de avaliação: unidades e denominadores explícitos, sem efeito sobre decisões."""

import math
from collections import Counter


def ratio(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def wilson95(correct: int, total: int) -> dict | None:
    """Intervalo de Wilson bilateral; não corrige viés de seleção ou de revisão."""
    if not 0 <= correct <= total:
        raise ValueError("Contagens binomiais inválidas")
    if total == 0:
        return None
    z = 1.959963984540054
    p = correct / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return {"method": "WILSON", "level": 0.95, "lower": max(0.0, center - radius), "upper": min(1.0, center + radius)}


def resolve_reviews(reviews: list[dict]) -> tuple[bool | None, str]:
    """Divergência ou revisão inconclusiva não vira maioria nem confirmação implícita."""
    if not reviews:
        return None, "NOT_REVIEWED"
    authors = set()
    labels = []
    for review in reviews:
        if not isinstance(review.get("author"), str) or not review["author"].strip():
            raise ValueError("Toda revisão exige autor")
        author = review["author"].strip().casefold()
        if author in authors:
            raise ValueError("Um autor não conta como dois revisores")
        authors.add(author)
        evidence = review.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(not isinstance(text, str) or not text.strip() for text in evidence)
        ):
            raise ValueError("Toda revisão exige evidência textual")
        if "label" not in review:
            raise ValueError("Toda revisão exige rótulo explícito, mesmo quando nulo")
        label = review["label"]
        if label is not None and type(label) is not bool:
            raise ValueError("Rótulo deve ser booleano ou nulo")
        labels.append(label)
    if len({label for label in labels if label is not None}) > 1:
        return None, "DISAGREEMENT"
    if None in labels:
        return None, "INCONCLUSIVE"
    return labels[0], "AGREEMENT" if len(labels) > 1 else "SINGLE_DEVELOPMENT_REVIEW"


def merge_metrics(cases: list[dict], *, group_interval: bool = False) -> dict:
    """Ausência de proposta é abstenção. Recuperação só se refere aos positivos desta coorte."""
    counts = Counter(
        dict.fromkeys(
            ["cases", "proposed", "reviewed", "positive_labels", "correct", "wrong", "unreviewed_proposals"], 0
        )
    )
    for case in cases:
        expected, proposed = case["expected"], case["proposed"]
        counts["cases"] += 1
        counts["proposed"] += proposed
        counts["reviewed"] += expected is not None
        counts["positive_labels"] += expected is True
        if proposed:
            counts["correct"] += expected is True
            counts["wrong"] += expected is False
            counts["unreviewed_proposals"] += expected is None
    decided = counts["correct"] + counts["wrong"]
    interval = wilson95(counts["correct"], decided) if group_interval else None
    proposed = counts["proposed"]
    return {
        "counts": dict(counts),
        "precision": ratio(counts["correct"], decided),
        "prediction_coverage": ratio(proposed, counts["cases"]),
        "review_coverage": ratio(counts["reviewed"], counts["cases"]),
        "positive_recovery_in_cohort": ratio(counts["correct"], counts["positive_labels"]),
        "algorithm_abstention": ratio(counts["cases"] - proposed, counts["cases"]),
        "inconclusive_reviews": counts["cases"] - counts["reviewed"],
        "precision_bounds_including_unknown_labels": {
            "lower": counts["correct"] / proposed,
            "upper": (counts["correct"] + counts["unreviewed_proposals"]) / proposed,
        }
        if proposed
        else None,
        "conditional_precision_interval": interval,
        "interval_scope": "Grupos decididos da coorte; hipótese binomial. Não certifica a população nem corrige viés."
        if group_interval
        else "Indisponível: pares selecionados e correlacionados não são ensaios independentes.",
        "population_duplicate_recall": None,
    }
