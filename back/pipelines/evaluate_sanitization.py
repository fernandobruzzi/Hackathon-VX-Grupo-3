"""Avaliação de desenvolvimento sobre coortes congeladas; não altera dados ou decisões."""

import hashlib
import importlib
import json
import re
from collections import Counter
from importlib.resources import files
from itertools import combinations
from pathlib import Path

from domain.evaluation import merge_metrics, ratio, resolve_reviews
from pipelines.corrections import propose_corrections
from pipelines.full_run import coverage
from pipelines.measure_extraction import Row, measure_against_columns, measure_known_pairs
from pipelines.ncm_corrections import propose_ncm_corrections
from pipelines.sanitize import _catalog, analysis_signature, analyze_material, merge_proposals, read_csv_records
from repositories.candidates import get_candidate_repository
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository


def implementation_fingerprint():
    """Vincula o relatório ao código instalado, mesmo sem .git dentro da imagem."""
    sources = {}
    for package in ("domain", "repositories"):
        root = Path(importlib.import_module(package).__file__).parent
        for path in root.rglob("*.py"):
            relative = path.relative_to(root)
            if all(part.isidentifier() for part in (*relative.parts[:-1], path.stem)):
                sources[f"{package}/{relative.as_posix()}"] = path.read_bytes()
    for name in (
        "sanitize",
        "corrections",
        "ncm_corrections",
        "full_run",
        "evaluate_sanitization",
        "measure_extraction",
    ):
        module = importlib.import_module(f"pipelines.{name}")
        sources[f"pipelines/{name}.py"] = Path(module.__file__).read_bytes()
    payload = {name: hashlib.sha256(value).hexdigest() for name, value in sorted(sources.items())}
    return {
        "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        "source_files": len(payload),
    }


def frozen_data(name):
    return files("pipelines.evaluation_data").joinpath(name).read_bytes()


def cohort_data(name, manifest_path=None):
    if Path(name).name != name:
        raise ValueError("Os arquivos da coorte devem estar no mesmo diretório do manifesto")
    return (Path(manifest_path).parent / name).read_bytes() if manifest_path else frozen_data(name)


def load_cohorts(manifest_path=None):
    raw = Path(manifest_path).read_bytes() if manifest_path else frozen_data("manifest_v2.json")
    manifest = json.loads(raw)
    if manifest.get("schema_version") != "evaluation-v1":
        raise ValueError("Versão do manifesto de avaliação não suportada")
    cohort_ids = set()
    for cohort in manifest.get("additional_group_cohorts", []):
        if cohort["id"] in cohort_ids or cohort["file"] not in manifest["legacy_files"]:
            raise ValueError("Coorte adicional repetida ou sem hash registrado")
        cohort_ids.add(cohort["id"])
    frozen = {**manifest["legacy_files"], "technical_v1.json": manifest["technical_file_sha256"]}
    for name, expected in frozen.items():
        if hashlib.sha256(cohort_data(name, manifest_path)).hexdigest() != expected:
            raise ValueError("Coorte histórica foi alterada: crie uma nova versão em vez de substituir a antiga")
    return (
        manifest,
        json.loads(cohort_data("merge_groups_v1.json", manifest_path)),
        json.loads(cohort_data("merge_pairs_v1.json", manifest_path)),
    )


def reviewed_cases(entries, additions=()):
    cases = []
    seen = set()
    for entry in entries:
        codes = tuple(sorted(entry["codes"]))
        if len(codes) < 2 or len(set(codes)) != len(codes) or codes in seen:
            raise ValueError("Casos duplicados ou sem membros suficientes")
        seen.add(codes)
        reviews = [{"author": "UNRECORDED_LEGACY", "label": entry["same_item"], "evidence": [entry["note"]]}]
        reviews.extend(
            {key: review[key] for key in ("author", "label", "evidence")}
            for review in additions
            if tuple(sorted(review["codes"])) == codes
        )
        expected, review_status = resolve_reviews(reviews)
        cases.append(
            {
                "codes": list(codes),
                "expected": expected,
                "review_status": review_status,
                "historical_label": entry["same_item"],
                "reviews": reviews,
            }
        )
    unknown = {tuple(sorted(review["codes"])) for review in additions} - seen
    if unknown:
        raise ValueError("Revisão adicional não pertence à coorte histórica")
    return cases


def compare_merges(merges, groups, pairs, additions=()):
    current = [set(proposal.material_codes) for proposal in merges]
    group_cases = reviewed_cases(groups["reviewed"], additions)
    for case in group_cases:
        members = set(case["codes"])
        case["proposed"] = members in current
        case["current_status"] = (
            "EXACT_PROPOSAL"
            if case["proposed"]
            else ("CHANGED_GROUP" if any(members <= candidate for candidate in current) else "NOT_PROPOSED")
        )
    predicted_pairs = {tuple(pair) for group in current for pair in combinations(sorted(group), 2)}
    pair_cases = reviewed_cases(pairs["pairs"])
    for case in pair_cases:
        if len(case["codes"]) != 2:
            raise ValueError("A unidade par exige exatamente dois códigos")
        case["proposed"] = tuple(case["codes"]) in predicted_pairs
    return {
        "groups": {"unit": "PROPOSAL_GROUP", **merge_metrics(group_cases, group_interval=True), "cases": group_cases},
        "pairs": {"unit": "MATERIAL_PAIR", **merge_metrics(pair_cases), "cases": pair_cases},
    }


def evaluate_technical(sample, analyzed):
    if not sample.get("author") or not sample.get("method"):
        raise ValueError("Amostra técnica exige autoria e método")
    rows, counts, classes = [], Counter(), Counter()
    seen = set()
    for case in sample["cases"]:
        code = case["code"]
        if code in seen or code not in analyzed:
            raise ValueError("Material técnico ausente ou repetido na coorte")
        seen.add(code)
        material = analyzed[code]
        if material.record.description != case["description"] or not case.get("evidence"):
            raise ValueError("Texto/evidência da amostra técnica não corresponde ao registro original")
        class_correct = material.pdm_class_id == case["expected_class_id"]
        classes["reviewed"] += 1
        classes["correct"] += class_correct
        for attribute, expected in case["attributes"].items():
            predicted = material.attributes.get(attribute)
            present = predicted is not None
            counts["reviewed_fields"] += 1
            counts["predicted_fields"] += present
            counts["expected_present"] += expected is not None
            equal = predicted == expected
            if attribute in {"REFERENCIA", "REFERENCIA FABRICANTE"} and predicted and expected:
                # Só grafia: preserva -00 e REV A como informação, sem assumir intercambiabilidade.
                equal = re.sub(r"[\s./-]", "", predicted) == re.sub(r"[\s./-]", "", expected)
            correct = class_correct and equal
            counts["correct_predictions"] += present and correct
            counts["recovered_fields"] += expected is not None and correct
            counts["unsupported_fills"] += expected is None and present
            counts["wrong_values"] += expected is not None and present and not correct
            counts["safe_abstentions"] += expected is None and not present
            rows.append(
                {
                    "code": code,
                    "expected_class_id": case["expected_class_id"],
                    "predicted_class_id": material.pdm_class_id,
                    "attribute": attribute,
                    "expected": expected,
                    "predicted": predicted,
                    "correct": correct,
                    "evidence": case["evidence"],
                    "tags": case["tags"],
                }
            )
    return {
        "unit": "REVIEWED_ATTRIBUTE",
        "author": sample["author"],
        "method": sample["method"],
        "selection": sample["selection"],
        "counts": dict(counts),
        "class_accuracy_in_cohort": ratio(classes["correct"], classes["reviewed"]),
        "precision": ratio(counts["correct_predictions"], counts["predicted_fields"]),
        "positive_recovery_in_cohort": ratio(counts["recovered_fields"], counts["expected_present"]),
        "algorithm_abstention": ratio(
            counts["reviewed_fields"] - counts["predicted_fields"], counts["reviewed_fields"]
        ),
        "conditional_precision_interval": None,
        "interval_scope": "Campos correlacionados e amostra dirigida de desenvolvimento; sem intervalo populacional.",
        "cases": rows,
    }


def sanitization_evaluation(csv_path, pdm_workbook, repository_name=None, manifest_path=None):
    manifest, groups, pairs = load_cohorts(manifest_path)
    digest = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()
    if digest != manifest["dataset_sha256"]:
        raise ValueError("O dataset não corresponde à coorte congelada")
    catalog = _catalog(pdm_workbook)
    records = read_csv_records(csv_path)
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    normalizer, corrector = get_normalization_repository(), get_correction_repository()
    candidates = get_candidate_repository(repository_name)
    analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
    merges = merge_proposals(analyzed, catalog, candidates, normalizer)
    pending_by_code = {}
    corrections, pending = propose_corrections(analyzed, catalog, normalizer, corrector, pending_by_code)
    corrections += propose_ncm_corrections(analyzed, catalog)
    report = compare_merges(merges, groups, pairs, manifest["group_review_additions"])
    additional_groups = {}
    for cohort in manifest.get("additional_group_cohorts", []):
        data = json.loads(cohort_data(cohort["file"], manifest_path))
        additional_groups[cohort["id"]] = {
            **compare_merges(merges, data, pairs, cohort["review_additions"])["groups"],
            "selection": cohort["selection"],
            "source_commit": cohort["source_commit"],
        }
    technical = json.loads(cohort_data("technical_v1.json", manifest_path))
    for case in technical["cases"]:
        pdm_class = catalog.classes.get(case["expected_class_id"])
        if pdm_class is None or set(case["attributes"]) - {a.name for a in pdm_class.attributes}:
            raise ValueError("O PDM mudou a classe/campos da coorte técnica; registre uma revisão versionada")
    source_rows = [Row(r.code, r.description, r.group, r.manufacturer, r.reference, r.status) for r in records]
    return {
        "schema_version": "evaluation-report-v1",
        "evaluation_kind": "DEVELOPMENT_EVALUATION",
        "independent_review": False,
        "pdm_changed_since_cohort": catalog.source_sha256 != manifest["pdm_source_sha256"],
        "authorizes_merge": False,
        "cohort": manifest,
        "dataset_sha256": digest,
        "implementation": implementation_fingerprint(),
        "analysis_signature": analysis_signature(catalog, classifier, extractor),
        "repositories": {"candidates": candidates.name, "normalization": normalizer.name, "correction": corrector.name},
        "coverage": coverage(records, merges + corrections, pending_by_code, {}),
        "pending_reasons": dict(pending),
        "current_merge_proposals": len(merges),
        "additional_groups": additional_groups,
        **report,
        "technical": evaluate_technical(technical, {m.record.code: m for m in analyzed}),
        "hidden_columns_proxy": {
            "scope": "FABRICANTE/referência em FIL01/SOB01 classificáveis. Não valida atributos técnicos.",
            "measurements": measure_against_columns(catalog, source_rows),
        },
        "known_positive_recovery_proxy": {
            "scope": "Redirecionamentos declarados no kit; não mede precisão nem recall global.",
            "measurements": measure_known_pairs(catalog, source_rows),
        },
        "limitations": [
            "Coortes revisadas durante o desenvolvimento; sem revisão independente ou de especialista.",
            "Grupos novos ou ampliados não herdam rótulos dos grupos históricos.",
            "Resultados não medem precisão de todos os atributos ou recall de todas as duplicidades.",
            "Reexecutar após a correção de identidade da #73, preservando as coortes atuais.",
        ],
    }
