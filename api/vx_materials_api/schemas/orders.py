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
