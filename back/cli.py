"""CLI do pipeline batch."""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from clients.storage import get_object_store
from domain.contracts import NormalizedField
from domain.pdm_loader import load_pdm
from domain.runtime import check_simulated_clients
from pipelines.classify import classification_evaluation, classification_report
from pipelines.enrich_real_products import run_enrichment
from pipelines.evaluate_sanitization import sanitization_evaluation
from pipelines.experiment import SEED as EXPERIMENT_SEED
from pipelines.experiment import experiment_packets
from pipelines.experiment_result import experiment_result
from pipelines.full_run import run_sanitize
from pipelines.review_handoff import review_handoff
from pipelines.sanitize import sanitize_report
from pipelines.search_index import run_index, watch_index
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
    check_simulated_clients()
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
    classify.add_argument("--repository", help="Padrao: CLASSIFICATION_REPOSITORY ou aliases_v1")
    evaluate = commands.add_parser("classification-evaluate", help="Mede precisao e cobertura na amostra rotulada")
    evaluate.add_argument("sample_path")
    evaluate.add_argument("--pdm-workbook", required=True)
    evaluate.add_argument("--repository")
    report_merges = commands.add_parser("sanitize-report", help="Resume as propostas de um CSV, sem gravar nada")
    report_merges.add_argument("csv_path")
    report_merges.add_argument("--pdm-workbook")
    report_merges.add_argument("--repository", help="Padrao: CANDIDATE_REPOSITORY ou exact_identity_v1")
    sanitation_eval = commands.add_parser("sanitization-evaluate", help="Avalia coortes congeladas de desenvolvimento")
    sanitation_eval.add_argument("csv_path")
    sanitation_eval.add_argument("--pdm-workbook", required=True)
    sanitation_eval.add_argument("--repository")
    sanitation_eval.add_argument(
        "--cohort-manifest", help="Manifesto versionado; padrão: coortes de desenvolvimento v1/v2"
    )
    handoff = commands.add_parser("review-handoff", help="Prepara coorte e fichas vazias sem homologar resultados")
    handoff.add_argument("csv_path")
    handoff.add_argument("--pdm-workbook", required=True)
    handoff.add_argument("--repository")
    handoff.add_argument("--size", type=int, default=40)
    handoff.add_argument("--seed", type=int, default=32)
    handoff.add_argument(
        "--historical-source", action="append", default=[], help="JSON histórico rastreável; repetível"
    )
    packets = commands.add_parser("experiment-packets", help="Gera a planilha cega e a chave do experimento")
    packets.add_argument("csv_path")
    packets.add_argument("--pdm-workbook", required=True)
    packets.add_argument("--out-dir", required=True, help="Pasta da planilha e da chave (chave fica fora)")
    packets.add_argument("--seed", type=int, default=EXPERIMENT_SEED)
    packets.add_argument("--pairs", type=int, default=40, help="Casos em cada parte A e B")
    packets.add_argument("--corrections", type=int, default=40)
    packets.add_argument("--slice", type=int, default=120)
    result = commands.add_parser("experiment-result", help="Calcula o resultado a partir de 1 ou 2 planilhas")
    result.add_argument("key_path")
    result.add_argument("sheets", nargs="+")
    index = commands.add_parser("index", help="Reconstroi o indice de busca, com a credencial batch_user")
    index.add_argument("--pdm-workbook")
    index.add_argument("--watch", action="store_true", help="Atualiza automaticamente fontes alteradas")
    index.add_argument("--poll-seconds", type=int, default=2)
    index.add_argument("--if-stale", action="store_true", help="Pula se a versao atual ja cobre todos os materiais")
    sanitize = commands.add_parser("sanitize", help="Grava propostas no banco, com a credencial batch_user")
    sanitize.add_argument("--pdm-workbook")
    sanitize.add_argument("--job-id")
    sanitize.add_argument("--manifest-key", help="Manifesto gravado pela API para o job, no armazenamento")
    sanitize.add_argument("--repository", help="Padrao: CANDIDATE_REPOSITORY ou exact_identity_v1")
    internal = commands.add_parser(
        "enrichment-report", help="Diagnostica completude e fontes internas sem banco ou rede"
    )
    internal.add_argument("--data-dir", default="data/desafio01")
    internal.add_argument("--internal-documents", help="Bundle documental local com dataset_id=kit")
    register = commands.add_parser("register-internal-sources", help="Valida e arquiva documentos internos imutáveis")
    register.add_argument("bundle_path")
    register.add_argument("--dataset-id", required=True)
    review = commands.add_parser("enrichment-review-packet", help="Congela amostra por atributo para revisão")
    review.add_argument("report_path")
    review.add_argument("--seed", type=int, default=263)
    review.add_argument("--sample-size", type=int, default=100)
    enrichment_eval = commands.add_parser("enrichment-evaluate", help="Avalia sugestões revisadas por atributo")
    enrichment_eval.add_argument("packet_path")
    enrichment_eval.add_argument("reviews_path")
    enrich = commands.add_parser(
        "enrich-real-products", help="Registra evidências e propostas imutáveis dos 15 produtos reais"
    )
    enrich.add_argument("--manifest-key", required=True, help="Chave do manifesto original criado por vx-bootstrap")
    enrich.add_argument("--pdm-workbook", required=True)
    enrich.add_argument(
        "--material-code", action="append", help="Restringe aos códigos informados, sempre dentro do manifesto"
    )
    enrich.add_argument("--repository", help="Padrão: ENRICHMENT_REPOSITORY ou catalog_labels_v1")
    enrich.add_argument("--evidence-manifest-key", help="Chave de relatório anterior para repetir sem rede")
    publish = commands.add_parser(
        "publish-enrichment", help="Persiste evidencias e propostas de um relatorio, sem editar o mestre"
    )
    publish.add_argument("--report-key", required=True)
    publish.add_argument("--pdm-workbook", required=True)
    args = parser.parse_args(argv)

    if args.command == "experiment-packets":
        if min(args.pairs, args.corrections, args.slice) < 1:
            parser.error("tamanhos devem ser positivos")
        result = experiment_packets(
            args.csv_path,
            args.pdm_workbook,
            args.out_dir,
            args.seed,
            pairs_size=args.pairs,
            corrections_size=args.corrections,
            slice_size=args.slice,
        )
    elif args.command == "experiment-result":
        result = experiment_result(args.key_path, args.sheets)
    elif args.command == "sanitization-evaluate":
        result = sanitization_evaluation(args.csv_path, args.pdm_workbook, args.repository, args.cohort_manifest)
    elif args.command == "review-handoff":
        result = review_handoff(
            args.csv_path,
            args.pdm_workbook,
            args.repository,
            size=args.size,
            seed=args.seed,
            historical_paths=args.historical_source,
        )
    elif args.command == "enrichment-report":
        from pipelines.internal_enrichment import report_kit

        result = report_kit(args.data_dir, supplemental_path=args.internal_documents)
    elif args.command == "register-internal-sources":
        from enrichment.internal_documents import bundle_object_key, parse_bundle

        content = Path(args.bundle_path).read_bytes()
        bundle = parse_bundle(content, args.dataset_id)
        key = bundle_object_key(content, args.dataset_id)
        get_object_store().put_if_absent(key, content)
        result = {"object_key": key, "documents": len(bundle["documents"]), "dataset_id": args.dataset_id}
    elif args.command == "enrichment-review-packet":
        from pipelines.evaluate_enrichment import create_review_packet

        result = create_review_packet(
            json.loads(Path(args.report_path).read_text()), seed=args.seed, sample_size=args.sample_size
        )
    elif args.command == "enrichment-evaluate":
        from pipelines.evaluate_enrichment import evaluate_packet

        result = evaluate_packet(
            json.loads(Path(args.packet_path).read_text()), json.loads(Path(args.reviews_path).read_text())
        )
    elif args.command == "publish-enrichment":
        from repositories.enrichment_repository import publish_enrichment

        result = publish_enrichment(get_object_store(), args.report_key, load_pdm(args.pdm_workbook))
    elif args.command == "enrich-real-products":
        from repositories.enrichment import get_enrichment_repository

        result = run_enrichment(
            get_object_store(),
            args.manifest_key,
            load_pdm(args.pdm_workbook),
            material_codes=args.material_code,
            repository=get_enrichment_repository(args.repository),
            evidence_manifest_key=args.evidence_manifest_key,
        )
    elif args.command == "index":
        if args.watch:
            watch_index(args.pdm_workbook, poll_seconds=args.poll_seconds)
        result = run_index(args.pdm_workbook, if_stale=args.if_stale)
    elif args.command == "sanitize-report":
        result = sanitize_report(args.csv_path, args.pdm_workbook, args.repository)
    elif args.command == "sanitize":
        result = run_sanitize(args.pdm_workbook, args.job_id, args.repository, manifest_key=args.manifest_key)
    elif args.command == "normalization-report":
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
