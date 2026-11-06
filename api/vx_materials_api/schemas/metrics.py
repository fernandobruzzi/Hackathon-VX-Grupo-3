"""Métricas operacionais e financeiras do contrato público do dashboard."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityCounts(_Contract):
    materials_total: int
    active: int
    blocked: int
    obsolete: int
    missing_ncm: int
    noncanonical_unit: int


class ProposalCounts(_Contract):
    proposals_total: int = 0
    pending: int = 0
    applied: int = 0
    rejected: int = 0
    stale: int = 0


class Evaluation(_Contract):
    reviewed_pairs: int = 0
    merge_precision: float | None = None
    duplicate_recall: float | None = None
    validated_class_ids: list[str] = Field(default_factory=list)


class FinancialMetrics(_Contract):
    currency: Literal["BRL"] = "BRL"
    data_origin: Literal["SYNTHETIC_CHALLENGE_DATA"] = "SYNTHETIC_CHALLENGE_DATA"
    inventory_book_value: str | None
    realized_savings: str | None = None
    estimated_savings: str | None = None
    assumptions: list[str] = Field(default_factory=list)


class DashboardMetrics(_Contract):
    dataset_id: UUID
    comparison_status: Literal["AFTER_SNAPSHOT_NOT_AVAILABLE"] = "AFTER_SNAPSHOT_NOT_AVAILABLE"
    before: QualityCounts
    after: QualityCounts | None = None
    pipeline: ProposalCounts
    evaluation: Evaluation = Field(default_factory=Evaluation)
    financial: FinancialMetrics | None = None
