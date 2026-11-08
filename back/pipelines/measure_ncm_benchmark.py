"""Mede as propostas de NCM do batch contra um benchmark com gabarito documental.

O motor lê só a base sem gabarito. A base com gabarito entra depois, unida por `ID_BENCHMARK`,
apenas para pontuar. Qualquer família e qualquer versão com as mesmas colunas servem, sem mudar
este código (ver `data/benchmark_ncm/v1/README.md`).

Os rótulos são documentais e não têm revisão humana independente: o resultado é medição de
desenvolvimento, nunca acurácia homologada nem autorização para aplicar propostas.

Uso, de `back/`:

    uv run python -m pipelines.measure_ncm_benchmark ../data/benchmark_ncm/v1 \\
        --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx

Com `--llm-audit`, o auditor LLM (#290) roda depois das regras, com o modelo de `LLM_REPOSITORY`, e o
relatório ganha `llm_audit`: resultado por caso, acertos e erros por família e o total com o auditor.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from clients.ncm_snapshot_store import load_configured_ncm_snapshot
from domain.pdm_loader import load_pdm
from pipelines.llm_audit import PROPOSED, audit_cases, select_audit_cases, summarize_audit
from pipelines.ncm_corrections import propose_ncm_corrections
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.extraction import get_extraction_repository
from repositories.llm import get_llm_repository
from repositories.ncm_scorer import get_ncm_scorer

SITUATIONS = ("CORRETO", "INCORRETO", "AUSENTE")


def normalize_ncm(raw: str | None) -> str | None:
    """Oito dígitos, aceitando só dígitos, pontos e espaços; nunca extrai, trunca ou completa."""
    raw = (raw or "").strip()
    if not raw or any(char not in "0123456789. " for char in raw):
        return None
    digits = raw.replace(".", "").replace(" ", "")
    return digits if len(digits) == 8 else None


def _ratio(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def score(rows: list[dict], predictions: dict[str, str | None], proposed: set[str]) -> dict:
    """`rows` vem da base com gabarito; `predictions` e `proposed` são indexados por ID_BENCHMARK."""
    families: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        key, family = row["ID_BENCHMARK"], row["FAMILIA_GABARITO"]
        counts = families[family]
        original = normalize_ncm(row["NCM"])
        predicted = predictions[key]
        if row["ELEGIVEL_BENCHMARK_NCM"] != "true":
            counts["pending"] += 1
            counts["pending_routed"] += key not in proposed
            continue
        situation = row["SITUACAO_NCM_ORIGINAL"]
        hit = predicted == row["NCM_GABARITO"]
        counts[f"{situation}_total"] += 1
        counts[f"{situation}_hit"] += hit
        counts["scorable"] += 1
        counts["hit"] += hit
        counts["proposed"] += key in proposed
        counts["proposed_hit"] += key in proposed and hit
        counts["abstained"] += key not in proposed and situation != "CORRETO"
        counts["improper_change"] += situation == "CORRETO" and not hit
        counts["format_only"] += key in proposed and predicted == original
    report = {"families": {}, "rotulos": "DOCUMENTAL_SEM_REVISAO_INDEPENDENTE"}
    total: Counter = Counter()
    for family, counts in sorted(families.items()):
        total.update(counts)
        report["families"][family] = _summary(counts)
    report["total"] = _summary(total)
    return report


def _summary(counts: Counter) -> dict:
    rates = {s: _ratio(counts[f"{s}_hit"], counts[f"{s}_total"]) for s in SITUATIONS}
    present = [rate["value"] for rate in rates.values() if rate["value"] is not None]
    fixed = counts["INCORRETO_hit"] + counts["AUSENTE_hit"]
    return {
        "accuracy": _ratio(counts["hit"], counts["scorable"]),
        "balanced_accuracy": sum(present) / len(present) if present else None,
        "by_situation": rates,
        "errors_and_missing_resolved": _ratio(fixed, counts["INCORRETO_total"] + counts["AUSENTE_total"]),
        "proposal_precision": _ratio(counts["proposed_hit"], counts["proposed"]),
        "improper_changes": counts["improper_change"],
        "format_only_proposals": counts["format_only"],
        "abstentions": counts["abstained"],
        "pending_routed_to_review": _ratio(counts["pending_routed"], counts["pending"]),
    }


def measure(benchmark_dir: Path, pdm_workbook: str, *, llm_audit: bool = False) -> dict:
    llm = get_llm_repository() if llm_audit else None
    if llm_audit and llm is None:
        raise ValueError("A medição do auditor exige LLM_REPOSITORY (bedrock_v1 ou simulated_v1).")
    records = read_csv_records(str(benchmark_dir / "base_sem_gabarito.csv"))
    with (benchmark_dir / "base_sem_gabarito.csv").open(encoding="utf-8-sig", newline="") as source:
        keys = [row["ID_BENCHMARK"] for row in csv.DictReader(source)]
    catalog = load_pdm(pdm_workbook)
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
    snapshot = load_configured_ncm_snapshot()
    proposals = propose_ncm_corrections(analyzed, catalog, snapshot=snapshot)
    targets = {proposal.suggested_primary_code: proposal.changeset["after"]["ncm"] for proposal in proposals}
    outcomes = None
    if llm is not None:
        # O modelo vê só a base sem gabarito, como as regras.
        cases = select_audit_cases(analyzed, catalog, set(targets))
        outcomes = audit_cases(cases, catalog, llm, snapshot=snapshot, scorer=get_ncm_scorer())
    # O gabarito só é lido depois que todas as propostas existem.
    with (benchmark_dir / "base_com_gabarito.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if [row["ID_BENCHMARK"] for row in rows] != keys:
        raise ValueError("As bases com e sem gabarito precisam ter os mesmos ID_BENCHMARK, na mesma ordem.")
    key_of = {record.code: key for key, record in zip(keys, records, strict=True)}
    report = {
        "benchmark": str(benchmark_dir),
        "algorithms": {
            "classification": f"{classifier.name}@{classifier.revision}",
            "extraction": f"{extractor.name}@{extractor.revision}",
            "corrections": get_correction_repository().name,
        },
        **score(rows, _predictions(records, keys, targets), {key_of[code] for code in targets}),
    }
    if outcomes is not None:
        audited = {o.material_code: o.proposal.changeset["after"]["ncm"] for o in outcomes if o.status == PROPOSED}
        combined = {**targets, **audited}
        report["llm_audit"] = {
            **summarize_audit(outcomes),
            "families": score_audit(rows, outcomes, key_of),
            "with_auditor": score(rows, _predictions(records, keys, combined), {key_of[c] for c in combined}),
        }
    return report


def _predictions(records, keys, targets: dict[str, str]) -> dict[str, str | None]:
    return {key: normalize_ncm(targets.get(r.code, r.ncm)) for key, r in zip(keys, records, strict=True)}


def score_audit(rows: list[dict], outcomes, key_of: dict[str, str]) -> dict:
    """Acertos, erros e abstenções do auditor por família, separando pendentes do gabarito."""
    by_key = {row["ID_BENCHMARK"]: row for row in rows}
    families: dict[str, Counter] = defaultdict(Counter)
    for outcome in outcomes:
        row = by_key[key_of[outcome.material_code]]
        counts = families[row["FAMILIA_GABARITO"]]
        counts["cases"] += 1
        counts[outcome.status.lower()] += 1
        if row["ELEGIVEL_BENCHMARK_NCM"] != "true":
            counts["pending_cases"] += 1
            counts["pending_with_suggestion"] += outcome.status == PROPOSED
            continue
        if outcome.status == PROPOSED:
            hit = normalize_ncm(outcome.proposal.changeset["after"]["ncm"]) == row["NCM_GABARITO"]
            counts["proposed_hit" if hit else "proposed_wrong"] += 1
            # Calibração (#297): acerto por faixa de confiança, sem faixa quando não há pontuador.
            level = outcome.proposal.changeset["llm_audit"]["confidence"]["band"] or "SEM_PONTUADOR"
            counts[f"band_{level}_{'hit' if hit else 'wrong'}"] += 1
            counts["improper_change"] += row["SITUACAO_NCM_ORIGINAL"] == "CORRETO" and not hit
    total: Counter = Counter()
    for counts in families.values():
        total.update(counts)
    return {**{family: dict(sorted(c.items())) for family, c in sorted(families.items())}, "total": dict(total)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("benchmark_dir", type=Path)
    parser.add_argument("--pdm-workbook", required=True)
    parser.add_argument(
        "--llm-audit", action="store_true", help="Inclui o auditor LLM (#290), com o modelo de LLM_REPOSITORY."
    )
    args = parser.parse_args(argv)
    report = measure(args.benchmark_dir, args.pdm_workbook, llm_audit=args.llm_audit)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
