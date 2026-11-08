"""Métricas operacionais e financeiras do contrato público do dashboard."""

from datetime import datetime
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


class FinancialMetrics(_Contract):
    currency: Literal["BRL"] = "BRL"
    data_origin: Literal["SYNTHETIC_CHALLENGE_DATA"] = "SYNTHETIC_CHALLENGE_DATA"
    inventory_book_value: str | None
    realized_savings: str | None = None
    estimated_savings: str | None = None
    assumptions: list[str] = Field(default_factory=list)


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


class OpenRequestCounts(_Contract):
    em_identificacao: int
    aguardando_cadastro: int
    em_atendimento: int


class ClosedRequestCounts(_Contract):
    # Atendimento pelo estoque, parcial e por compras ficam separados (motivos da seção 5).
    atendida_estoque: int
    atendida_parcial_compras: int
    encaminhada_compras: int
    cancelada: int
    cadastro_rejeitado: int


class ResolutionTime(_Contract):
    # Da criação ao evento MATERIAL_REQUEST_CLOSED das solicitações atendidas.
    resolved_requests: int
    median_hours: float
    p90_hours: float


class UnavailableIndicator(_Contract):
    indicator: Literal["requests", "resolution_time", "registration_avoided", "identified_under_other_code"]
    reason: Literal["NO_REQUESTS", "NO_RESOLVED_REQUESTS", "NO_CHAT_LINKED_REQUESTS"]


class RequestJourney(_Contract):
    """Jornada do solicitante a partir das solicitações persistidas; sem quantidades nem valores."""

    requests_total: int
    open: OpenRequestCounts | None
    closed: ClosedRequestCounts | None
    resolution_time: ResolutionTime | None
    # Solicitações encaminhadas a Compras com o código existente, sem pedido de cadastro.
    registration_avoided: int | None
    # Solicitações resolvidas para um código ativo que a busca do chat comprovou pela identidade.
    identified_under_other_code: int | None
    unavailable: list[UnavailableIndicator] = Field(default_factory=list)


class DashboardMetrics(_Contract):
    dataset_id: UUID
    comparison_status: Literal["AFTER_SNAPSHOT_NOT_AVAILABLE", "AVAILABLE"] = "AFTER_SNAPSHOT_NOT_AVAILABLE"
    before: QualityCounts
    after: QualityCounts | None = None
    after_snapshot: QualitySnapshotOut | None = None
    pipeline: ProposalCounts
    evaluation: Evaluation = Field(default_factory=Evaluation)
    journey: RequestJourney
    financial: FinancialMetrics | None = None
