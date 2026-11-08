"""Disponibilidade e reservas de saldo; quantidades sempre como strings decimais, sem preço nem valor."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vx_materials_api.schemas.material_requests import MaterialRequestSummary, Quantity

ReservationStatus = Literal["ATIVA", "CONSUMIDA", "CANCELADA"]
AvailabilityBlock = Literal[
    "INACTIVE_MATERIAL",
    "MATERIAL_WITHOUT_UNIT",
    "NO_INVENTORY_DATASET",
    "RECONCILIATION_REQUIRED",
]
DecimalText = str


class StockAvailability(BaseModel):
    """`available = imported - reserved - delivered`, no centro, na unidade do material."""

    model_config = ConfigDict(extra="forbid")
    material_id: UUID
    material_code: str
    center_code: str
    unit: str | None
    dataset_id: UUID | None
    imported: DecimalText
    reserved: DecimalText
    delivered: DecimalText
    available: DecimalText
    unconverted_units: list[str]
    reservable: bool
    blocked_reason: AvailabilityBlock | None


class CreateStockReservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    quantity: Quantity

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("A quantidade deve ser positiva.")
        return value


class StockReservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    request_id: UUID
    material_id: UUID
    center_code: str
    quantity: Quantity
    unit: str
    status: ReservationStatus
    dataset_id: UUID
    created_by_user_id: UUID
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class RequestFulfillment(BaseModel):
    """Parcelas da solicitação (seção 4.2): `pending = requested - reserved - delivered - forwarded`."""

    model_config = ConfigDict(extra="forbid")
    requested: DecimalText
    reserved: DecimalText
    delivered: DecimalText
    forwarded: DecimalText
    pending: DecimalText


class StockReservationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reservation: StockReservation
    request: MaterialRequestSummary
    fulfillment: RequestFulfillment
    availability: StockAvailability


class StockReservationList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[StockReservation]
    fulfillment: RequestFulfillment
