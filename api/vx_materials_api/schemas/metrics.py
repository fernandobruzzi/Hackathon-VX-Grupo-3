"""Métricas operacionais e financeiras do contrato público do dashboard."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from vx_materials_api.savings_assumptions import AssumptionSource, SavingsAssumption


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityCounts(_Contract):
    materials_total: int
    active: int
    blocked: int
    obsolete: int
    missing_ncm: int
    noncanonical_unit: int
    # Ativos apontados como duplicados por propostas de unificação pendentes ou aplicadas.
    duplicate_codes: int


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


class NcmProposalCounts(_Contract):
    created: int = 0
    fiscal_approved: int = 0
    rejected: int = 0
    pending: int = 0
    stale: int = 0


class NcmBenchmarkFamily(_Contract):
    family: str
    resolved: int
    eligible_problems: int
    improper_changes: int
    abstentions: int


class NcmBenchmark(_Contract):
    data_origin: Literal["DEVELOPMENT_MEASUREMENT"]
    labels: Literal["DOCUMENTAL_SEM_REVISAO_INDEPENDENTE"]
    benchmark_version: str
    measured_at: datetime
    rules_version: str
    algorithms: dict[str, str]
    pdm_source_sha256: str
    input_sha256: str
    families: list[NcmBenchmarkFamily]


class NcmMetrics(_Contract):
    missing_before: int
    missing_after: int | None
    content: NcmProposalCounts
    format_only: NcmProposalCounts
    fiscal_decided: int
    fiscal_approved_decisions: int
    operational_precision: float | None
    benchmark: NcmBenchmark


class StockSavingsEvidence(_Contract):
    delivery_id: UUID
    quantity: str
    unit: str
    unit_price: str
    source: str
    recorded_on: date
    snapshot_ids: list[str]
    factors: dict[str, str]


class SavingsComponent(_Contract):
    key: Literal["registration_reuse", "duplicate_codes", "batch_reviews", "stock_fulfilled"]
    label: str
    kind: Literal["ESTIMATED", "MEASURED_KIT_VALUE"]
    count: str | None
    count_unit: str
    amount_brl: str | None
    formula: str
    assumptions: list[SavingsAssumption] = Field(default_factory=list)
    unavailable_reason: str | None = None
    estimated_hours: str | None = None
    quantities: dict[str, str] = Field(default_factory=dict)
    stock_evidence: list[StockSavingsEvidence] = Field(default_factory=list)


class FinancialMetrics(_Contract):
    currency: Literal["BRL"] = "BRL"
    data_origin: Literal["SYNTHETIC_CHALLENGE_DATA"] = "SYNTHETIC_CHALLENGE_DATA"
    inventory_book_value: str | None
    realized_savings: str | None = None
    estimated_savings: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    components: list[SavingsComponent] = Field(default_factory=list)
    assumption_source: AssumptionSource | None = None
    calculation_version: str = "savings-v1"


class QualitySnapshotRequest(_Contract):
    # Sem dataset, vale o importado mais recentemente.
    dataset_id: UUID | None = None


class QualitySnapshotOut(_Contract):
    id: UUID
    dataset_id: UUID
    created_at: datetime
    applied_proposals: int
    materials_changed: int
    inventory_value_conserved: bool
    export_key: str


class DashboardMetrics(_Contract):
    dataset_id: UUID
    comparison_status: Literal["AFTER_SNAPSHOT_NOT_AVAILABLE", "AVAILABLE"] = "AFTER_SNAPSHOT_NOT_AVAILABLE"
    before: QualityCounts
    after: QualityCounts | None = None
    after_snapshot: QualitySnapshotOut | None = None
    pipeline: ProposalCounts
    evaluation: Evaluation = Field(default_factory=Evaluation)
    ncm: NcmMetrics
    financial: FinancialMetrics | None = None
