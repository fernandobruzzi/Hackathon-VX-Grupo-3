"""Prepara entradas congeladas e fichas vazias; não avalia nem homologa o saneamento."""

import csv
import hashlib
import importlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

from pipelines.evaluate_sanitization import implementation_fingerprint
from pipelines.merge_sample import SEED, SIZE, describe, sample_merges
from pipelines.sanitize import _catalog, analysis_signature, analyze_material, merge_proposals, read_csv_records
from repositories.candidates import get_candidate_repository
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _implementation() -> dict:
    sources = {}
    for name in ("cli", "pipelines.review_handoff", "pipelines.merge_sample"):
        sources[f"{name.replace('.', '/')}.py"] = hashlib.sha256(
            Path(importlib.import_module(name).__file__).read_bytes()
        ).hexdigest()
    analysis = implementation_fingerprint()
    return {
        "sha256": _digest({"analysis": analysis, "files": sources}),
        "analysis": analysis,
        "files": sources,
        "python": platform.python_version(),
        "openpyxl": version("openpyxl"),
    }


def _blank_review() -> dict:
    return {"author": None, "participated_in_rule_adjustment": None, "label": None, "evidence": [], "conflicts": []}


def _blank_value() -> dict:
    return {**_blank_review(), "value": None}


def review_handoff(
    csv_path: str,
    pdm_workbook: str,
    repository_name: str | None = None,
    *,
    size: int = SIZE,
    seed: int = SEED,
    historical_paths: list[str] | None = None,
) -> dict:
    """JSON determinístico, sem banco/AWS, com históricos fornecidos sem reinterpretá-los."""
    if size < 1:
        raise ValueError("O tamanho da amostra deve ser positivo")
    historical = []
    for name in historical_paths or []:
        raw = Path(name).read_bytes()
        historical.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "document": json.loads(raw)})
    with open(csv_path, encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    originals = {row["CODIGO_MATERIAL"]: row for row in rows}
    if len(originals) != len(rows):
        raise ValueError("Código de material repetido no CSV")
    catalog = _catalog(pdm_workbook)
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    candidates, normalizer = get_candidate_repository(repository_name), get_normalization_repository()
    analyzed = [analyze_material(record, catalog, classifier, extractor) for record in read_csv_records(csv_path)]
    proposals = merge_proposals(analyzed, catalog, candidates, normalizer)
    frame = [
        {"id": p.id, "codes": list(p.material_codes), "changeset_sha256": p.changeset_hash}
        for p in sorted(proposals, key=lambda p: p.id)
    ]
    selected = sample_merges(proposals, size=size, seed=seed)
    cases = []
    for proposal in selected:
        fields = catalog.classes[proposal.changeset["pdm_class_id"]].attributes
        cases.append(
            {
                "id": proposal.id,
                "codes": list(proposal.material_codes),
                "group_review": _blank_review(),
                "members": [
                    {
                        "code": code,
                        "original": originals[code],
                        "class_review": _blank_value(),
                        "field_reviews": [{"field": field.name, **_blank_value()} for field in fields],
                    }
                    for code in proposal.material_codes
                ],
            }
        )
    packet = {
        "schema_version": "review-handoff-v1",
        "kind": "REVIEW_PREPARATION",
        "independent_review": False,
        "authorizes_publication": False,
        "authorizes_merge": False,
        "sources": {
            "dataset_sha256": hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
            "pdm_sha256": catalog.source_sha256,
            "pdm_version": catalog.version,
        },
        "implementation": _implementation(),
        "analysis_signature": analysis_signature(catalog, classifier, extractor),
        "repositories": {"candidates": candidates.name, "normalization": normalizer.name},
        "sampling": {
            "unit": "PROPOSAL_GROUP",
            "method": "sample_merges: random.Random(seed).sample, frame ordenado por id",
            "seed": seed,
            "requested_size": size,
            "frame": frame,
            "frame_sha256": _digest(frame),
            "selected_ids": [p.id for p in selected],
        },
        "review_cases": cases,
        "predictions": {p.id: describe(p) for p in selected},
        "historical_sources": historical,
        "limitations": [
            "Preparação sem revisor técnico ou evidência de intercambiabilidade confirmados; homologação pendente.",
            "Gerar com #73 e #85 integradas, antes de ajustar regras com os resultados da nova coorte.",
            "Amostra somente de MERGEs propostos; não mede recall, abstenções ou precisão da base inteira.",
            "Campos sugeridos pela classe prevista; o revisor pode corrigir a classe e acrescentar campos.",
            "Históricos são anexos rastreáveis, sem transferência de rótulos para as fichas vazias.",
        ],
    }
    return {"packet_sha256": _digest(packet), **packet}
