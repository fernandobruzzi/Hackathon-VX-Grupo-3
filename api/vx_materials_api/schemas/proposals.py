"""Entrada de decisao e contrato persistido entre o produtor batch e a API."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from domain.proposals import canonical_hash
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


def evidence_hash(source) -> str:
    fields = (
        "attribute_name",
        "proposed_value",
        "source_url",
        "source_title",
        "source_excerpt",
        "source_page",
        "source_sha256",
    )
    return canonical_hash({field: getattr(source, field) for field in fields})
