"""Schemas de batch (`BatchJobRequest`, `BatchJob` e `BatchJobList` no OpenAPI)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

JobType = Literal["SANITIZE", "IMPORT_ORDERS", "ENRICH_REAL_PRODUCTS"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BatchScope(_Contract):
    pdm_class_ids: list[str]
    include_statuses: list[Literal["ATIVO", "BLOQUEADO", "OBSOLETO"]] = Field(
        description="Exige todos os status; subconjuntos e lista vazia recebem 422 SCOPE_NOT_SUPPORTED."
    )


class BatchJobRequest(_Contract):
    dataset_id: UUID
    job_type: JobType
    pdm_version: str
    ncm_version: str
    scope: BatchScope


class BatchJobResumeRequest(_Contract):
    """Sem campos: o job reprocessado é o da rota."""


class JobProgress(_Contract):
    processed: int
    total: int


class JobCounts(_Contract):
    proposals: int
    merges: int
    ncm: int
    enrichment: int


class JobError(_Contract):
    code: str
    message: str


class BatchJobOut(_Contract):
    id: UUID
    job_type: JobType
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]
    requested_by: str
    pdm_version: str
    ncm_version: str
    progress: JobProgress
    counts: JobCounts
    started_at: str | None
    finished_at: str | None
    heartbeat_at: str | None
    error: JobError | None


class BatchJobList(_Contract):
    items: list[BatchJobOut]
    # O dataset que um novo job usaria: a tela inicia o job sem pedir o id ao usuário.
    latest_dataset_id: UUID | None
    next_cursor: str | None = Field(default=None)
