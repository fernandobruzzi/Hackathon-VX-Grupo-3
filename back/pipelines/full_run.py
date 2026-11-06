"""Execução do saneamento na base inteira, com checkpoints, cobertura e métricas.

Duas etapas retomáveis:

1. Análise (classe, extração, identidade) em blocos de materiais. Cada bloco é gravado em
   `runs/{job_id}/analysis/` no armazenamento; ao retomar, blocos já gravados são lidos, não refeitos.
   É a etapa que vai concentrar custo quando houver chamadas de modelo. Job e blocos guardam a assinatura
   das regras (PDM e revisões); retomar com regras diferentes é recusado, e o caminho é um novo job.
2. Gravação das propostas em lotes. Cada lote é gravado na mesma transação do checkpoint, então o
   checkpoint nunca aponta para algo que não foi salvo. Os ids das propostas vêm do conteúdo, e repetir
   um lote não duplica nada.

Todo material termina com um desfecho registrado: proposta, pendência com motivo, sem alteração ou erro.
"""

import hashlib
import json
import os
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine

from clients.storage import ObjectStore, get_object_store
from domain.contracts import AnalyzedMaterial, MaterialRecord, MergeProposal, PdmCatalog
from pipelines.corrections import propose_corrections, summarize_corrections
from pipelines.identity_review import identity_review_report, store_identity_review
from pipelines.ncm_corrections import propose_ncm_corrections
from pipelines.sanitize import _catalog, analysis_signature, analyze_material, merge_proposals, summarize
from repositories.batch_repository import (
    DEFAULT_STALE_SECONDS,
    claim_job,
    fail_job,
    finish_job,
    heartbeat,
    insert_proposals,
    read_materials,
    single_tenant,
    update_job,
)
from repositories.candidates import get_candidate_repository
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository

PIPELINE_VERSION = "batch-v1"
# Intervalo do sinal de vida entre checkpoints. Bem abaixo do prazo em que a API dá o job como parado.
HEARTBEAT_SECONDS = 15
ANALYSIS_CHUNK = 1000
SAVE_BATCH = 500

# Desfechos por material. Um material com proposta pode também ter pendências: vale a proposta.
OUTCOME_PROPOSAL = "PROPOSTA"
OUTCOME_PENDING = "PENDENTE"
OUTCOME_UNCHANGED = "SEM_ALTERACAO"
OUTCOME_ERROR = "ERRO_ANALISE"


class AnalysisRulesChanged(RuntimeError):
    """O job foi analisado com outras regras. Misturar interpretações daria propostas incoerentes."""


@dataclass
class RunContext:
    """Onde gravar o progresso. Sem job, a execução roda inteira em memória, sem retomada."""

    engine: Engine
    tenant_id: str
    job_id: str | None = None
    store: ObjectStore | None = None
    checkpoint: dict = field(default_factory=dict)
    # Ponto de interrupção usado nos testes de retomada.
    on_step: Callable[[str, int], None] = lambda stage, done: None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _chunk_hash(records: list[MaterialRecord]) -> str:
    payload = json.dumps([[r.code, r.version] for r in records])
    return hashlib.sha256(payload.encode()).hexdigest()


def _encode(material: AnalyzedMaterial) -> dict:
    data = asdict(material)
    data["record"]["inventory"] = list(material.record.inventory)
    return data


def _decode(data: dict) -> AnalyzedMaterial:
    record = MaterialRecord(**{**data["record"], "inventory": tuple(data["record"]["inventory"])})
    return AnalyzedMaterial(
        record,
        data["pdm_class_id"],
        data["item_name"],
        data["attributes"],
        data["identity_key"],
        tuple(data.get("review_reasons", ())),
    )


def _analysis_key(job_id: str, index: int) -> str:
    return f"runs/{job_id}/analysis/chunk-{index:04d}.json"


def _save_checkpoint(context: RunContext) -> None:
    if context.job_id is None:
        return
    with context.engine.begin() as connection:
        update_job(connection, context.job_id, context.checkpoint)


def analyze_all(
    records: list[MaterialRecord], catalog: PdmCatalog, context: RunContext
) -> tuple[list[AnalyzedMaterial], dict[str, str]]:
    """Analisa em blocos. Devolve os materiais analisados e os erros por código."""
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    signature = analysis_signature(catalog, classifier, extractor)
    recorded = context.checkpoint.get("analysis_signature")
    if recorded != signature and (recorded or "analysis" in context.checkpoint):
        raise AnalysisRulesChanged(_rules_changed(recorded, signature))
    context.checkpoint["analysis_signature"] = signature
    analyzed: list[AnalyzedMaterial] = []
    errors: dict[str, str] = {}
    chunks = [records[i : i + ANALYSIS_CHUNK] for i in range(0, len(records), ANALYSIS_CHUNK)]
    reused = 0
    for index, chunk in enumerate(chunks):
        key = _analysis_key(context.job_id, index) if context.job_id and context.store else None
        digest = _chunk_hash(chunk)
        stored = _load_chunk(context.store, key, digest, signature) if key else None
        if stored is not None:
            chunk_analyzed, chunk_errors = stored
            reused += 1
        else:
            chunk_analyzed, chunk_errors = [], {}
            for record in chunk:
                try:
                    chunk_analyzed.append(analyze_material(record, catalog, classifier, extractor))
                except Exception as error:  # noqa: BLE001 - um material ruim não derruba a base inteira
                    chunk_errors[record.code] = f"{type(error).__name__}: {error}"
            if key:
                content = {
                    "input_sha256": digest,
                    "rules_signature": signature,
                    "materials": [_encode(m) for m in chunk_analyzed],
                    "errors": chunk_errors,
                }
                context.store.put_if_absent(key, json.dumps(content, ensure_ascii=False, sort_keys=True).encode())
        analyzed.extend(chunk_analyzed)
        errors.update(chunk_errors)
        context.checkpoint["analysis"] = {
            "chunks_done": index + 1,
            "chunks_total": len(chunks),
            "chunks_reused": reused,
            "processed": min((index + 1) * ANALYSIS_CHUNK, len(records)),
            "total": len(records),
        }
        _save_checkpoint(context)
        context.on_step("analysis", index + 1)
    return analyzed, errors


def _rules_changed(recorded: str | None, current: str) -> str:
    return (
        f"Regras de análise mudaram desde o início do job (antes: {recorded or 'sem assinatura'}; "
        f"agora: {current}). Os blocos gravados ficam como estão: crie um novo job."
    )


def _load_chunk(store: ObjectStore, key: str, digest: str, signature: str):
    try:
        content = json.loads(store.get(key))
    except FileNotFoundError:
        return None
    except Exception as error:  # noqa: BLE001 - S3 sinaliza ausência com erro próprio
        if "NoSuchKey" in str(error) or "404" in str(error):
            return None
        raise
    if content["input_sha256"] != digest:
        raise RuntimeError(f"{key} foi gerado de outra entrada: a base mudou durante o job")
    if content.get("rules_signature") != signature:
        raise AnalysisRulesChanged(_rules_changed(content.get("rules_signature"), signature))
    return [_decode(m) for m in content["materials"]], content["errors"]


def _proposal_set_hash(proposals: list[MergeProposal]) -> str:
    return hashlib.sha256("\n".join(f"{p.id}:{p.changeset_hash}" for p in proposals).encode()).hexdigest()


def save_all(proposals: list[MergeProposal], records: list[MaterialRecord], context: RunContext) -> int:
    """Grava em lotes, com o checkpoint na mesma transação de cada lote."""
    digest = _proposal_set_hash(proposals)
    previous = context.checkpoint.get("save", {})
    # Mesmo conjunto de propostas: pula o que já foi salvo. Se mudou, regrava tudo (sem duplicar).
    start = previous.get("saved", 0) if previous.get("proposal_set_sha256") == digest else 0
    inserted = previous.get("inserted", 0) if start else 0
    for offset in range(start, len(proposals), SAVE_BATCH):
        batch = proposals[offset : offset + SAVE_BATCH]
        with context.engine.begin() as connection:
            inserted += insert_proposals(connection, batch, records, context.tenant_id, context.job_id)
            context.checkpoint["save"] = {
                "proposal_set_sha256": digest,
                "saved": offset + len(batch),
                "total": len(proposals),
                "inserted": inserted,
            }
            if context.job_id:
                update_job(connection, context.job_id, context.checkpoint)
        context.on_step("save", offset + len(batch))
    if not proposals:
        context.checkpoint["save"] = {"proposal_set_sha256": digest, "saved": 0, "total": 0, "inserted": 0}
    return inserted


def coverage(
    records: list[MaterialRecord],
    proposals: list[MergeProposal],
    pending_by_code: dict[str, tuple[str, ...]],
    errors: dict[str, str],
) -> dict:
    """Um desfecho por material. A soma dos desfechos é sempre o total da base."""
    proposed = {code for proposal in proposals for code in proposal.material_codes}
    outcomes: Counter[str] = Counter()
    for record in records:
        if record.code in errors:
            outcomes[OUTCOME_ERROR] += 1
        elif record.code in proposed:
            outcomes[OUTCOME_PROPOSAL] += 1
        elif record.code in pending_by_code:
            outcomes[OUTCOME_PENDING] += 1
        else:
            outcomes[OUTCOME_UNCHANGED] += 1
    return {
        "materials_total": len(records),
        "outcomes": dict(sorted(outcomes.items())),
        "errors": dict(sorted(errors.items())),
    }


def model_usage() -> dict:
    """Esta versão não chama LLM nem embeddings. A estrutura soma chamadas futuras por modelo."""
    return {"calls": {}, "input_tokens": 0, "output_tokens": 0, "cost_usd": "0", "note": "sem chamadas de modelo"}


def run_full(
    records: list[MaterialRecord],
    catalog: PdmCatalog,
    context: RunContext,
    repository_name: str | None = None,
    correction_repository: str | None = None,
) -> dict:
    started = time.perf_counter()
    attempts = context.checkpoint.setdefault("attempts", [])
    attempts.append({"started_at": _now()})
    context.checkpoint["pipeline_version"] = PIPELINE_VERSION

    analyzed, errors = analyze_all(records, catalog, context)
    analysis_seconds = time.perf_counter() - started

    normalizer = get_normalization_repository()
    merges = merge_proposals(analyzed, catalog, get_candidate_repository(repository_name), normalizer)
    pending_by_code: dict[str, tuple[str, ...]] = {}
    corrections, pending = propose_corrections(
        analyzed, catalog, normalizer, get_correction_repository(correction_repository), pending_by_code
    )
    corrections += propose_ncm_corrections(analyzed, catalog)
    review = identity_review_report(analyzed, catalog)
    review_key = store_identity_review(review, context.store or get_object_store(), context.tenant_id)
    proposals = merges + corrections
    propose_seconds = time.perf_counter() - started - analysis_seconds

    inserted = save_all(proposals, records, context)
    total_seconds = time.perf_counter() - started
    attempts[-1].update({"finished_at": _now(), "seconds": round(total_seconds, 2)})

    by_type = Counter(proposal.proposal_type for proposal in proposals)
    return {
        "pipeline_version": PIPELINE_VERSION,
        "pdm_version": catalog.version,
        "analysis_signature": context.checkpoint["analysis_signature"],
        "identity_review_key": review_key,
        # Campos do contrato BatchJob.counts; o detalhe fica ao lado.
        "proposals": len(proposals),
        "merges": by_type.get("MERGE", 0),
        "ncm": by_type.get("NCM_CORRECTION", 0),
        "enrichment": by_type.get("ENRICHMENT", 0),
        "by_type": dict(sorted(by_type.items())),
        "inserted": inserted,
        "merge_summary": summarize(merges),
        "corrections": summarize_corrections(corrections, pending),
        "coverage": coverage(records, proposals, pending_by_code, errors),
        "timing_seconds": {
            "analysis": round(analysis_seconds, 2),
            "propose": round(propose_seconds, 2),
            "save": round(total_seconds - analysis_seconds - propose_seconds, 2),
            "total_this_attempt": round(total_seconds, 2),
            "total_all_attempts": round(sum(a.get("seconds", 0) for a in attempts), 2),
            "attempts": len(attempts),
        },
        "model_usage": model_usage(),
    }


class _Heartbeat:
    """Mantém `heartbeat_at` atualizado enquanto o worker trabalha entre checkpoints."""

    def __init__(self, engine: Engine, job_id: str, worker_id: str, interval: float) -> None:
        self._engine, self._job_id, self._worker_id, self._interval = engine, job_id, worker_id, interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{job_id}", daemon=True)
        self.lost = False

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                if not heartbeat(self._engine, self._job_id, self._worker_id):
                    # O próximo checkpoint do worker falha com LeaseLost e encerra a execução.
                    self.lost = True
                    return
            except Exception:  # noqa: BLE001 - falha de rede passageira não derruba o job
                continue

    def __enter__(self) -> "_Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval)


def check_manifest(store: ObjectStore, manifest_key: str, job_id: str, catalog: PdmCatalog) -> dict:
    """Confere o manifesto que a API gravou para o job. Ele nunca traz credencial do usuário."""
    manifest = json.loads(store.get(manifest_key))
    if manifest["job_id"] != job_id:
        raise RuntimeError(f"O manifesto {manifest_key} é de outro job")
    if manifest["pdm_version"] != catalog.version:
        raise RuntimeError(f"O manifesto pede o PDM {manifest['pdm_version']}, mas o carregado é {catalog.version}")
    return manifest


def run_sanitize(
    pdm_workbook: str | None = None,
    job_id: str | None = None,
    repository_name: str | None = None,
    database_url: str | None = None,
    correction_repository: str | None = None,
    store: ObjectStore | None = None,
    on_step: Callable[[str, int], None] | None = None,
    manifest_key: str | None = None,
    heartbeat_seconds: float | None = None,
) -> dict:
    """Saneamento da base gravada no banco. Com `job_id`, registra progresso e retoma do checkpoint."""
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Defina DATABASE_URL com a credencial batch_user")
    engine = create_engine(url)
    try:
        catalog = _catalog(pdm_workbook)
        tenant_id = single_tenant(engine)
        if not job_id:
            context = RunContext(engine, tenant_id, on_step=on_step or (lambda stage, done: None))
            return run_full(read_materials(engine, tenant_id), catalog, context, repository_name, correction_repository)

        store = store or get_object_store()
        if manifest_key:
            check_manifest(store, manifest_key, job_id, catalog)
        worker_id = str(uuid.uuid4())
        stale = int(os.environ.get("BATCH_HEARTBEAT_TIMEOUT_SECONDS", DEFAULT_STALE_SECONDS))
        claimed = claim_job(engine, job_id, worker_id, stale_seconds=stale)
        if claimed["tenant_id"] != tenant_id:
            raise RuntimeError("O job pertence a outra empresa")
        context = RunContext(engine, tenant_id, job_id, store, claimed["checkpoint"])
        if on_step:
            context.on_step = on_step
        interval = heartbeat_seconds or float(os.environ.get("BATCH_HEARTBEAT_SECONDS", HEARTBEAT_SECONDS))
        with _Heartbeat(engine, job_id, worker_id, interval):
            finalization_attempt = None
            try:
                metrics = context.checkpoint.get("final_metrics")
                if metrics is not None:
                    finalization_attempt = {"started_at": _now()}
                    context.checkpoint.setdefault("finalization_attempts", []).append(finalization_attempt)
                    signature = analysis_signature(
                        catalog, get_classification_repository(catalog), get_extraction_repository()
                    )
                    recorded = context.checkpoint.get("analysis_signature")
                    if recorded != signature:
                        raise AnalysisRulesChanged(_rules_changed(recorded, signature))
                if metrics is None:
                    records = read_materials(engine, tenant_id)
                    metrics = run_full(records, catalog, context, repository_name, correction_repository)
                    # Persiste o conteúdo exato antes de publicar o artefato imutável.
                    # A retomada repete só a publicação/conclusão, sem recalcular os tempos.
                    context.checkpoint["final_metrics"] = metrics
                if finalization_attempt is None:
                    finalization_attempt = {"started_at": _now()}
                    context.checkpoint.setdefault("finalization_attempts", []).append(finalization_attempt)
                _save_checkpoint(context)
                store.put_if_absent(
                    f"runs/{job_id}/metrics.json", json.dumps(metrics, ensure_ascii=False, sort_keys=True).encode()
                )
                finalization_attempt["finished_at"] = _now()
                finish_job(engine, job_id, context.checkpoint, metrics)
            except BaseException as error:
                attempt = finalization_attempt or context.checkpoint.get("attempts", [{}])[-1]
                attempt.update({"failed_at": _now(), "error": f"{type(error).__name__}: {error}"[:300]})
                fail_job(engine, job_id, context.checkpoint, f"{type(error).__name__}: {error}")
                raise
        return metrics
    finally:
        engine.dispose()
