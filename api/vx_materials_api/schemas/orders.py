"""Pedidos de cadastro no contrato público."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrderSubmitRequest(_Contract):
    expected_version: int = Field(ge=1)


class OrderDecisionRequest(_Contract):
    expected_version: int = Field(ge=1)
    decision: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=1)
    ncm_code: str | None = Field(default=None, min_length=8, max_length=10)
    ncm_source: str | None = Field(default=None, min_length=1, max_length=1000)
    ncm_evaluation_hash: str | None = Field(default=None, min_length=64, max_length=64)


class OrderComplementRequest(_Contract):
    expected_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=10000)
    source: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)
