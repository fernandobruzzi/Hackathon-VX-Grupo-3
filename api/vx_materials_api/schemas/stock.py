"""Disponibilidade e reservas de saldo; quantidades sempre como strings decimais, sem preço nem valor."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vx_materials_api.schemas.material_requests import (
    MaterialRequestSummary,
    Quantity,
    ReservationStatus,
    StockReservation,
)

__all__ = ["ReservationStatus", "StockReservation"]

MovementType = Literal["ENTREGA", "REVERSAO"]
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


class OtherCenterAvailability(BaseModel):
    """Disponível positivo de outro centro autorizado. Informativo: não reserva nem transfere."""

    model_config = ConfigDict(extra="forbid")
    center_code: str
    center_name: str | None
    available: DecimalText
    unit: str | None
    reservable: bool
    blocked_reason: AvailabilityBlock | None


class StockAlternatives(BaseModel):
    """Destino e, se ele não atende, outros centros do escopo do usuário com disponível (#251)."""

    model_config = ConfigDict(extra="forbid")
    destination: StockAvailability
    needed: DecimalText | None
    destination_sufficient: bool
    alternatives: list[OtherCenterAvailability]
    suggest_purchasing: bool


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


def _positive(value):
    if Decimal(value) <= 0:
        raise ValueError("A quantidade deve ser positiva.")
    return value


def _nonblank(value):
    if not value.strip():
        raise ValueError("Informe o motivo.")
    return value


class DeliverStockReservation(BaseModel):
    """Saída física de parte ou de toda a reserva; `expected_version` é a versão da solicitação."""

    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    quantity: Quantity

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value):
        return _positive(value)


class CancelStockReservation(BaseModel):
    """Libera a parte reservada e não entregue; `expected_version` é a versão da solicitação."""

    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        return _nonblank(value)


class ReverseStockMovement(BaseModel):
    """Movimento compensatório de uma entrega, limitado ao que ainda não foi revertido."""

    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    quantity: Quantity
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value):
        return _positive(value)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        return _nonblank(value)


class StockMovement(BaseModel):
    """Entrega ou reversão; nunca editado nem apagado. `reversed_quantity` só existe na entrega."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    reservation_id: UUID
    request_id: UUID
    movement_type: MovementType
    quantity: Quantity
    reverses_movement_id: UUID | None
    reversed_quantity: Quantity | None
    unit: str
    dataset_id: UUID
    created_by_user_id: UUID
    created_at: datetime


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


class StockMovementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movement: StockMovement
    reservation: StockReservation
    request: MaterialRequestSummary
    fulfillment: RequestFulfillment
    availability: StockAvailability


class StockReservationList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[StockReservation]
    movements: list[StockMovement]
    fulfillment: RequestFulfillment
