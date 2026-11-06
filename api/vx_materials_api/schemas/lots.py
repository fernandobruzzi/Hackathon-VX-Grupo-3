"""Entrada da aprovação em lote por amostra (#120)."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from vx_materials_api.schemas.proposals import Reason, StrictModel


class LotReviewOpen(StrictModel):
    lot_key: str = Field(min_length=1, max_length=500)
    tier: Literal[1, 2]


class SampleMark(StrictModel):
    proposal_id: UUID = Field(strict=False)
    verdict: Literal["CORRECT", "WRONG"]


class LotDecision(StrictModel):
    expected_version: int = Field(ge=1)
    marks: list[SampleMark] = Field(min_length=1, max_length=100)
    reason: Reason
