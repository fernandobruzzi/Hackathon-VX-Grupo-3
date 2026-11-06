"""Entrada de decisao e contrato persistido entre o produtor batch e a API."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from domain.enrichment_rules import evidence_hash as evidence_hash
from domain.proposals import proposal_hash as proposal_hash

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProposalDecision(StrictModel):
    expected_version: int = Field(ge=1)
    review_area: Literal["TECHNICAL", "FISCAL"]
    decision: Literal["APPROVE", "REJECT"]
    primary_material_code: str | None = None
    reason: Reason


class MemberInterpretation(StrictModel):
    material_id: UUID
    expected_version: int = Field(ge=1)
    pdm_class_id: str | None
    item_name: str | None
    attributes: dict[str, str | None]


class MaterialAfter(StrictModel):
    pdm_class_id: str | None
    item_name: str | None
    attributes: dict[str, str | None]
    unit: str
    ncm: str | None
    # Só em correções de PDM: grupo da classe confirmada, gravado como dado revisado.
    merchandise_group: str | None = None


class UnitConversion(StrictModel):
    from_unit: str
    to_unit: str
    factor: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$", max_length=64)
    source: Reason

    @field_validator("factor")
    @classmethod
    def positive_factor(cls, value):
        from decimal import Decimal

        if Decimal(value) <= 0:
            raise ValueError("Fator deve ser positivo")
        return value


class StoredChange(StrictModel):
    field: str
    before: str | None
    after: str
    source: Reason


class ReviewLane(StrictModel):
    """Nível de revisão gravado pelo batch (#119). Só os níveis 1 e 2 entram em lote."""

    tier: Literal[1, 2, 3]
    lot_key: str = Field(min_length=1)
    reasons: list[str] = Field(default_factory=list)


class EnrichmentContext(StrictModel):
    schema_version: Literal["enrichment-v1"]
    report_key: str = Field(min_length=1, max_length=1024)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_signature: str = Field(min_length=1, max_length=128)
    divergent_attributes: list[str] = Field(default_factory=list)
    blocked_attributes: list[str] = Field(default_factory=list)


class ProposalChangeset(StrictModel):
    schema_version: Literal["proposal-v1"]
    dataset_id: UUID
    pdm_version: str
    pdm_source_sha256: str
    after: MaterialAfter
    conversions: list[UnitConversion] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    sources: dict[str, str] = Field(default_factory=dict)
    evidence_hashes: dict[str, str] = Field(default_factory=dict)
    primary_material_code: str | None = None
    ranking_score: float | None = None
    changes: list[StoredChange] = Field(default_factory=list)
    ncm_assessment: dict[str, Any] | None = None
    ncm_before_assessment: dict[str, Any] | None = None
    review_lane: ReviewLane | None = None
    enrichment_context: EnrichmentContext | None = None
