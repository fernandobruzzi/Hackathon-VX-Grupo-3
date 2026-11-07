"""Rotas de jobs batch. Só a Governança (`batch:run`) inicia, reprocessa ou acompanha jobs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from clients.storage import get_object_store
from vx_materials_api import settings
from vx_materials_api.dependencies import current_identity, db_session
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.batch import BatchJobList, BatchJobOut, BatchJobRequest, BatchJobResumeRequest
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
def list_jobs(identity: Governance, db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> BatchJobList:
    timeout = settings.batch_heartbeat_timeout_seconds()
    jobs = batch_service.list_jobs(db, identity, limit, timeout)
    dataset = batch_service.latest_dataset(db, identity)
    return BatchJobList(
        items=[batch_service.to_contract(db, job) for job in jobs],
        latest_dataset_id=dataset.id if dataset else None,
        next_cursor=None,
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
