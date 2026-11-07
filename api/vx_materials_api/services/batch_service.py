"""Disparo e acompanhamento de jobs de batch.

A API cria o job, grava o manifesto no armazenamento e dispara a task. A task acompanha o próprio
progresso no banco (checkpoint e heartbeat). Antes de qualquer leitura ou disparo, jobs sem sinal de
vida há mais que o prazo viram FAILED, com o checkpoint preservado: reprocessar continua dele.
"""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from clients.storage import ObjectStore
from domain.pdm_loader import DEFAULT_PDM_VERSION
from pipelines.full_run import PIPELINE_VERSION
from vx_materials_api.db.models import BatchJob, Dataset, MaterialMaster, OperationRequest, UserSso
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.batch import BatchJobOut, BatchJobRequest, JobCounts, JobError, JobProgress
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.rbac import require_permission
from vx_materials_api.services.batch_runner import BatchRunner, LaunchRequest

NCM_VERSION = "ncm-demo-v1"
SUPPORTED_TYPES = frozenset({"SANITIZE"})
ACTIVE_STATUSES = ("QUEUED", "RUNNING")
WORKER_TIMEOUT = "WORKER_TIMEOUT"
WORKER_NOT_STARTED = "WORKER_NOT_STARTED"
_ERROR_CODE = re.compile(r"^([A-Z][A-Z_]+): (.*)$", re.S)
COMMAND_OPERATION = "BATCH_COMMAND"


def _command(db: Session, identity: Identity, key: uuid.UUID, action: str, resource: uuid.UUID, payload: dict):
    # O lock de usuário/chave também serializa uma tentativa com outro tenant ou recurso.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"batch-command:{identity.user_id}:{key}"},
    )
    digest = hashlib.sha256(
        json.dumps(
            {"tenant": str(identity.tenant_id), "action": action, "resource": str(resource), "payload": payload},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    previous = db.scalar(
        select(OperationRequest).where(
            OperationRequest.user_id == identity.user_id,
            OperationRequest.operation == COMMAND_OPERATION,
            OperationRequest.idempotency_key == str(key),
        )
    )
    if previous is not None and previous.payload_hash != digest:
        raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "A chave já foi usada com outro comando batch.")
    return previous, digest


def _remember_command(db: Session, identity: Identity, key: uuid.UUID, digest: str, job: BatchJob) -> None:
    # Persiste antes do disparo: nem uma resposta perdida nem uma falha ambígua relança a task.
    db.add(
        OperationRequest(
            user_id=identity.user_id,
            operation=COMMAND_OPERATION,
            idempotency_key=str(key),
            payload_hash=digest,
            status="COMPLETED",
            resource_id=str(job.id),
            response={"job_id": str(job.id)},
        )
    )


def _replay_job(db: Session, identity: Identity, previous: OperationRequest) -> BatchJob:
    job = db.scalar(
        select(BatchJob).where(BatchJob.id == uuid.UUID(previous.resource_id), BatchJob.tenant_id == identity.tenant_id)
    )
    if job is None:
        raise ApiProblem(404, "NOT_FOUND", "Job não encontrado.")
    return job


def manifest_key(job_id: uuid.UUID) -> str:
    return f"runs/{job_id}/manifest.json"


def expire_stale_jobs(db: Session, tenant_id: uuid.UUID, timeout_seconds: int) -> int:
    """Marca como FAILED os jobs sem heartbeat (ou que nunca começaram) dentro do prazo."""
    stale = text(
        """
        UPDATE batch_jobs
        SET status = 'FAILED',
            error_summary = CASE WHEN heartbeat_at IS NULL
                THEN 'WORKER_NOT_STARTED: A task não começou dentro do prazo.'
                ELSE 'WORKER_TIMEOUT: Processamento interrompido por ausência de heartbeat.' END
        WHERE tenant_id = :tenant AND status IN ('QUEUED', 'RUNNING')
          AND COALESCE(heartbeat_at, updated_at) < now() - make_interval(secs => :timeout)
        """
    )
    expired = db.execute(stale, {"tenant": tenant_id, "timeout": timeout_seconds}).rowcount
    db.commit()
    return expired


def _active_job(db: Session, tenant_id: uuid.UUID) -> BatchJob | None:
    return db.scalar(
        select(BatchJob).where(BatchJob.tenant_id == tenant_id, BatchJob.status.in_(ACTIVE_STATUSES)).limit(1)
    )


def _launch(db: Session, job: BatchJob, runner: BatchRunner) -> None:
    try:
        job.task_arn = runner.launch(LaunchRequest(str(job.id), manifest_key(job.id), job.updated_at.isoformat()))
    except Exception as error:
        job.status = "FAILED"
        job.error_summary = f"LAUNCH_FAILED: {type(error).__name__}: {error}"[:500]
        db.commit()
        raise ApiProblem(503, "BATCH_LAUNCH_FAILED", "Não foi possível disparar o batch.") from error
    db.commit()


def _require_single_dataset(db: Session, tenant_id: uuid.UUID) -> None:
    count = db.scalar(select(func.count()).select_from(Dataset).where(Dataset.tenant_id == tenant_id))
    if count != 1:
        raise ApiProblem(
            422,
            "MULTIPLE_DATASETS_NOT_SUPPORTED",
            "O batch suporta exatamente um dataset por empresa no MVP. Múltiplas importações não são suportadas.",
        )


def start_job(
    db: Session,
    identity: Identity,
    request: BatchJobRequest,
    store: ObjectStore,
    runner: BatchRunner,
    timeout_seconds: int,
    idempotency_key: uuid.UUID,
) -> BatchJob:
    require_permission(identity, "batch:run")
    if request.job_type not in SUPPORTED_TYPES:
        raise ApiProblem(422, "JOB_TYPE_NOT_SUPPORTED", f"O tipo {request.job_type} ainda não roda no batch.")
    if set(request.scope.include_statuses) != {"ATIVO", "BLOQUEADO", "OBSOLETO"}:
        raise ApiProblem(
            422, "SCOPE_NOT_SUPPORTED", "O batch exige todos os status; subconjuntos e lista vazia não são suportados."
        )
    if request.scope.pdm_class_ids:
        raise ApiProblem(422, "SCOPE_NOT_SUPPORTED", "O batch processa a base inteira; filtrar classes ainda não.")
    if request.pdm_version != DEFAULT_PDM_VERSION:
        raise ApiProblem(422, "PDM_VERSION_NOT_LOADED", f"O PDM carregado é {DEFAULT_PDM_VERSION}.")
    dataset = db.scalar(
        select(Dataset).where(Dataset.id == request.dataset_id, Dataset.tenant_id == identity.tenant_id)
    )
    if dataset is None:
        raise ApiProblem(404, "NOT_FOUND", "Dataset não encontrado.")

    expire_stale_jobs(db, identity.tenant_id, timeout_seconds)
    # Um job por vez: o lock evita dois disparos simultâneos passando pela mesma verificação.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"batch:{identity.tenant_id}"})
    previous, digest = _command(
        db, identity, idempotency_key, "START", request.dataset_id, request.model_dump(mode="json")
    )
    if previous is not None:
        return _replay_job(db, identity, previous)
    _require_single_dataset(db, identity.tenant_id)
    active = _active_job(db, identity.tenant_id)
    if active is not None:
        raise ApiProblem(409, "JOB_ALREADY_RUNNING", "Já existe um job em andamento.", {"job_id": str(active.id)})

    job = BatchJob(
        tenant_id=identity.tenant_id,
        requested_by_user_id=identity.user_id,
        dataset_id=dataset.id,
        job_type=request.job_type,
        pdm_version=request.pdm_version,
        ncm_version=request.ncm_version,
        status="QUEUED",
        checkpoint={},
    )
    db.add(job)
    db.flush()
    manifest = {
        "job_id": str(job.id),
        "dataset_id": str(dataset.id),
        "pipeline_version": PIPELINE_VERSION,
        "pdm_version": request.pdm_version,
        "ncm_version": request.ncm_version,
        "input_manifest_key": f"raw/{dataset.id}/manifest.json",
        "output_prefix": f"runs/{job.id}/",
    }
    store.put_if_absent(manifest_key(job.id), json.dumps(manifest, indent=2, sort_keys=True).encode())
    _remember_command(db, identity, idempotency_key, digest, job)
    db.commit()
    _launch(db, job, runner)
    return job


def resume_job(
    db: Session,
    identity: Identity,
    job_id: uuid.UUID,
    runner: BatchRunner,
    timeout_seconds: int,
    idempotency_key: uuid.UUID,
) -> BatchJob:
    """Reprocessa um job que falhou. A task continua dos checkpoints dele, sem duplicar propostas."""
    require_permission(identity, "batch:run")
    expire_stale_jobs(db, identity.tenant_id, timeout_seconds)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"batch:{identity.tenant_id}"})
    job = db.scalar(
        select(BatchJob).where(BatchJob.id == job_id, BatchJob.tenant_id == identity.tenant_id).with_for_update()
    )
    if job is None:
        raise ApiProblem(404, "NOT_FOUND", "Job não encontrado.")
    previous, digest = _command(db, identity, idempotency_key, "RESUME", job_id, {})
    if previous is not None:
        return _replay_job(db, identity, previous)
    _require_single_dataset(db, identity.tenant_id)
    if job.status != "FAILED":
        raise ApiProblem(409, "JOB_NOT_RESUMABLE", "Só um job que falhou pode ser reprocessado.")
    active = _active_job(db, identity.tenant_id)
    if active is not None:
        raise ApiProblem(409, "JOB_ALREADY_RUNNING", "Já existe um job em andamento.", {"job_id": str(active.id)})
    # Volta para a fila sem apagar o checkpoint; o heartbeat nulo conta o prazo a partir de agora.
    db.execute(
        update(BatchJob)
        .where(BatchJob.id == job.id)
        .values(status="QUEUED", heartbeat_at=None, error_summary=None, updated_at=func.now())
    )
    _remember_command(db, identity, idempotency_key, digest, job)
    db.commit()
    db.refresh(job)
    _launch(db, job, runner)
    return job


def get_job(db: Session, identity: Identity, job_id: uuid.UUID, timeout_seconds: int) -> BatchJob:
    expire_stale_jobs(db, identity.tenant_id, timeout_seconds)
    job = db.scalar(select(BatchJob).where(BatchJob.id == job_id, BatchJob.tenant_id == identity.tenant_id))
    if job is None:
        raise ApiProblem(404, "NOT_FOUND", "Job não encontrado.")
    return job


def list_jobs(db: Session, identity: Identity, limit: int, timeout_seconds: int) -> list[BatchJob]:
    expire_stale_jobs(db, identity.tenant_id, timeout_seconds)
    return list(
        db.scalars(
            select(BatchJob)
            .where(BatchJob.tenant_id == identity.tenant_id)
            .order_by(BatchJob.created_at.desc(), BatchJob.id)
            .limit(limit)
        )
    )


def latest_dataset(db: Session, identity: Identity) -> Dataset | None:
    return db.scalar(
        select(Dataset).where(Dataset.tenant_id == identity.tenant_id).order_by(Dataset.imported_at.desc()).limit(1)
    )


def _utc(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _error(summary: str | None) -> JobError | None:
    if not summary:
        return None
    match = _ERROR_CODE.match(summary)
    if match:
        return JobError(code=match.group(1), message=match.group(2))
    return JobError(code="BATCH_ERROR", message=summary)


def to_contract(db: Session, job: BatchJob) -> BatchJobOut:
    checkpoint: dict[str, Any] = job.checkpoint or {}
    counts: dict[str, Any] = job.counts or {}
    analysis = checkpoint.get("analysis", {})
    total = analysis.get("total")
    if total is None:
        total = db.scalar(
            select(func.count()).select_from(MaterialMaster).where(MaterialMaster.tenant_id == job.tenant_id)
        )
    attempts = checkpoint.get("attempts", [])
    last = attempts[-1] if attempts else {}
    finished = None
    if job.status == "SUCCEEDED":
        finished = last.get("finished_at")
    elif job.status == "FAILED":
        finished = last.get("failed_at") or job.updated_at
    saved = checkpoint.get("save", {})
    requester = db.scalar(select(UserSso.display_name).where(UserSso.id == job.requested_by_user_id))
    return BatchJobOut(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        requested_by=requester or "—",
        pdm_version=job.pdm_version,
        ncm_version=job.ncm_version or NCM_VERSION,
        progress=JobProgress(processed=analysis.get("processed", 0), total=total),
        counts=JobCounts(
            # Durante a gravação, as propostas salvas até agora; ao concluir, o total do job.
            proposals=counts.get("proposals", saved.get("saved", 0)),
            merges=counts.get("merges", 0),
            ncm=counts.get("ncm", 0),
            enrichment=counts.get("enrichment", 0),
        ),
        started_at=_utc(attempts[0].get("started_at")) if attempts else None,
        finished_at=_utc(finished),
        heartbeat_at=_utc(job.heartbeat_at),
        error=_error(job.error_summary) if job.status == "FAILED" else None,
    )
