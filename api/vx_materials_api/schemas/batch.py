"""Schemas de batch (`BatchJobRequest`, `BatchJob` e `BatchJobList` no OpenAPI)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]
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
    status: JobStatus
    requested_by: str
    pdm_version: str
    ncm_version: str
    progress: JobProgress
    counts: JobCounts
    started_at: str | None
    finished_at: str | None
    heartbeat_at: str | None
    error: JobError | None
    automatic_corrections: "AutomaticCorrectionSummary | None" = None


class BatchJobList(_Contract):
    automatic_correction_mode: Literal["OFF", "SIMULATE", "APPLY"] = "OFF"
    items: list[BatchJobOut]
    # O dataset que um novo job usaria: a tela inicia o job sem pedir o id ao usuário.
    latest_dataset_id: UUID | None
    next_cursor: str | None = Field(default=None)
    active_job: BatchJobOut | None


class AutomaticCorrectionSummary(_Contract):
    mode: Literal["OFF", "SIMULATE", "APPLY"]
    configured_mode: Literal["OFF", "SIMULATE", "APPLY"]
    policy_version: str
    execution_id: UUID | None
    status: Literal["DISABLED", "WAITING", "RUNNING", "COMPLETED", "POLICY_CHANGED", "PAUSED"]
    counts: dict[str, int]
    reasons: dict[str, int]


class AutomaticCorrectionItem(_Contract):
    id: UUID
    proposal_id: UUID
    material_id: UUID | None
    status: Literal["ELIGIBLE", "APPLIED", "REVIEW", "STALE", "ERROR", "SKIPPED"]
    eligible: bool
    reasons: list[str]
    attempts: int
    index_status: Literal["NOT_REQUIRED", "PENDING", "CURRENT", "FAILED"]
    index_error: str | None


class AutomaticCorrectionReport(AutomaticCorrectionSummary):
    items: list[AutomaticCorrectionItem]
    next_cursor: str | None


class AutomaticCorrectionRetryRequest(_Contract):
    """Repete somente a execução já autorizada; não permite selecionar modo nem proposta."""


BatchJobOut.model_rebuild()
