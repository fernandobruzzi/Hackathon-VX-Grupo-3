"""Rotas de jobs batch. Só a Governança (`batch:run`) inicia, reprocessa ou acompanha jobs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from clients.storage import get_object_store
from vx_materials_api import settings
from vx_materials_api.dependencies import current_identity, db_session
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.batch import (
    AutomaticCorrectionReport,
    AutomaticCorrectionRetryRequest,
    BatchJobList,
    BatchJobOut,
    BatchJobRequest,
    BatchJobResumeRequest,
    JobStatus,
)
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.rbac import require_permission
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import batch_service
from vx_materials_api.services.batch_runner import BatchRunner

router = APIRouter(prefix="/api/v1/batch", tags=["batch"])
PERMISSION = "batch:run"


def governance(identity: Annotated[Identity, Depends(current_identity)]) -> Identity:
    require_permission(identity, PERMISSION)
    return identity


def runner(request: Request) -> BatchRunner:
    configured = request.app.state.batch_runner
    if configured is None:
        raise ApiProblem(503, "BATCH_RUNNER_UNAVAILABLE", "O disparo do batch não está configurado.")
    return configured


Governance = Annotated[Identity, Depends(governance)]
Db = Annotated[Session, Depends(db_session)]


@router.post("/jobs", status_code=202)
def start_job(
    payload: BatchJobRequest,
    request: Request,
    identity: Governance,
    db: Db,
    task: Annotated[BatchRunner, Depends(runner)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> BatchJobOut:
    """Cria o job, grava o manifesto e dispara a task, sem token do usuário."""
    verify_write(request, identity)
    timeout = settings.batch_heartbeat_timeout_seconds()
    job = batch_service.start_job(db, identity, payload, get_object_store(), task, timeout, idempotency_key)
    return batch_service.to_contract(db, job)


@router.get("/jobs")
def list_jobs(
    identity: Governance,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    status: JobStatus | None = None,
) -> BatchJobList:
    timeout = settings.batch_heartbeat_timeout_seconds()
    jobs, next_cursor, active = batch_service.list_jobs(db, identity, limit, timeout, cursor=cursor, status=status)
    dataset = batch_service.latest_dataset(db, identity)
    return BatchJobList(
        automatic_correction_mode=settings.automatic_correction_mode(),
        items=[batch_service.to_contract(db, job) for job in jobs],
        latest_dataset_id=dataset.id if dataset else None,
        next_cursor=next_cursor,
        active_job=batch_service.to_contract(db, active) if active else None,
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, identity: Governance, db: Db) -> BatchJobOut:
    job = batch_service.get_job(db, identity, job_id, settings.batch_heartbeat_timeout_seconds())
    return batch_service.to_contract(db, job)


@router.post("/jobs/{job_id}/resume", status_code=202)
def resume_job(
    job_id: UUID,
    payload: BatchJobResumeRequest,
    request: Request,
    identity: Governance,
    db: Db,
    task: Annotated[BatchRunner, Depends(runner)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> BatchJobOut:
    """Reprocessa um job que falhou, continuando dos checkpoints."""
    verify_write(request, identity)
    job = batch_service.resume_job(
        db, identity, job_id, task, settings.batch_heartbeat_timeout_seconds(), idempotency_key
    )
    return batch_service.to_contract(db, job)


@router.get("/jobs/{job_id}/automatic-corrections")
def automatic_report(
    job_id: UUID,
    request: Request,
    identity: Governance,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
) -> AutomaticCorrectionReport:
    from vx_materials_api.services.automatic_corrections import report

    return report(db, identity, job_id, limit=limit, cursor=cursor)


@router.post("/jobs/{job_id}/automatic-corrections/retry", status_code=202)
def retry_automatic(
    job_id: UUID,
    payload: AutomaticCorrectionRetryRequest,
    request: Request,
    identity: Governance,
    db: Db,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> AutomaticCorrectionReport:
    from vx_materials_api.db.models import BatchJob
    from vx_materials_api.routes.sanitization import catalog
    from vx_materials_api.services.automatic_corrections import process_job, report
    from vx_materials_api.services.batch_service import _command, _remember_command

    verify_write(request, identity)
    body = report(db, identity, job_id)
    job = db.get(BatchJob, job_id)
    if not job.automatic_corrections:
        raise ApiProblem(409, "AUTOMATION_NOT_ARMED", "O job não foi autorizado para aplicação automática.")
    previous, digest = _command(db, identity, idempotency_key, "AUTOMATIC_RETRY", job_id, {})
    if previous is None:
        _remember_command(db, identity, idempotency_key, digest, job)
        db.commit()
    # Repetir o agendamento recupera uma queda após o commit do comando.
    # Resultados duráveis e travas impedem reaplicar uma correção confirmada.
    background_tasks.add_task(
        process_job, request.app.state.session_factory, job_id, catalog(request), retry_errors=True
    )
    return body
