"""Entrada de decisao e contrato persistido entre o produtor batch e a API."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

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


class SupplementalSource(StrictModel):
    object_key: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EnrichmentContext(StrictModel):
    schema_version: Literal["enrichment-v1", "internal-enrichment-v1"]
    report_key: str = Field(min_length=1, max_length=1024)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_signature: str = Field(min_length=1, max_length=128)
    divergent_attributes: list[str] = Field(default_factory=list)
    blocked_attributes: list[str] = Field(default_factory=list)
    supplemental_source: SupplementalSource | None = None


class LlmCallRecord(StrictModel):
    repository: str
    model: str
    prompt_version: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    simulated: bool


class LlmAuditAttribute(StrictModel):
    nome: str
    valor: str
    trecho: str
    base: Literal["LITERAL", "INFERIDO"]


class LlmAuditConfidence(StrictModel):
    """Confiança da sugestão (#297): organiza a revisão e nunca aprova nada sozinha."""

    version: str = Field(min_length=1)
    domain_validated: bool
    chosen: str
    candidates: list[str] = Field(min_length=1)
    scorer: dict[str, Any] | None = None
    probabilities: dict[str, float] | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    band: Literal["ALTA", "MEDIA", "BAIXA"] | None = None
    error: str | None = None


class LlmAuditContext(StrictModel):
    """Evidência do auditor LLM (#290). É contexto da revisão: nada aqui é aplicado por si só."""

    policy_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    call: LlmCallRecord
    simulated: bool
    selection_reasons: list[str] = Field(min_length=1)
    class_source: Literal["RULES", "LLM"]
    rules_reading: dict[str, Any]
    attributes: list[LlmAuditAttribute] = Field(default_factory=list)
    inferred_attributes: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    rationale: str
    context: dict[str, Any]
    confidence: LlmAuditConfidence | None = None


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
    origin: Literal["RULES", "LLM_AUDITOR"] = "RULES"
    llm_audit: LlmAuditContext | None = None

    @model_validator(mode="after")
    def audit_matches_origin(self):
        if (self.origin == "LLM_AUDITOR") != (self.llm_audit is not None):
            raise ValueError("Sugestão do auditor LLM exige origem LLM_AUDITOR e o contexto da auditoria")
        if self.llm_audit is not None and self.review_lane is not None:
            raise ValueError("Sugestão do auditor LLM nunca entra em lote")
        return self
