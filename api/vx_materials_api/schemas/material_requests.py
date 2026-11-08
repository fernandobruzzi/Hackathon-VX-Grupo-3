"""Solicitação de necessidade; identidade e estado são derivados no servidor."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

RequestStatus = Literal["EM_IDENTIFICACAO", "AGUARDANDO_CADASTRO", "EM_ATENDIMENTO", "ENCERRADA"]
Quantity = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$", max_length=25)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CreateMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_text: str = Field(min_length=1, max_length=10000)
    quantity: Quantity
    unit: ShortText
    center_code: ShortText
    material_id: UUID | None = None
    chat_session_id: UUID | None = None
    registration_order_id: UUID | None = None
    # Confirma a criação mesmo com solicitação aberta do mesmo material e centro (#248).
    acknowledge_open_requests: bool = False

    @field_validator("original_text")
    @classmethod
    def nonblank_text(cls, value):
        if not value.strip():
            raise ValueError("Descreva a necessidade de material.")
        return value

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("A quantidade deve ser positiva.")
        return value


class CancelMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError("Informe o motivo do cancelamento.")
        return value


class MaterialRequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    protocol: str
    requester_user_id: UUID
    original_text: str
    material_id: UUID | None
    quantity: Quantity
    unit: str
    center_code: str
    status: RequestStatus
    closure_reason: str | None
    chat_session_id: UUID | None
    registration_order_id: UUID | None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    can_cancel: bool


class MaterialRequestTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    action: str
    actor_user_id: UUID
    before_status: RequestStatus | None
    after_status: RequestStatus
    reason: str | None
    created_at: datetime


PurchaseForwardStatus = Literal["ENCAMINHADO", "ACEITO", "DEVOLVIDO", "CANCELADO"]


class ForwardToPurchasing(BaseModel):
    """Encaminha a quantidade pendente inteira; a divisão com reserva parcial é da #242."""

    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)


class AcceptPurchaseForward(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)


class ReturnPurchaseForward(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError("Informe o motivo da devolução.")
        return value


class PurchaseForward(BaseModel):
    """Demanda para Compras; não indica pedido ao fornecedor, recebimento nem entrega."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    material_request_id: UUID
    request_protocol: str
    material_id: UUID
    material_code: str
    material_description: str | None
    quantity: Quantity
    unit: str
    center_code: str
    status: PurchaseForwardStatus
    reason: str | None
    forwarded_by_user_id: UUID
    handled_by_user_id: UUID | None
    handled_at: datetime | None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    can_handle: bool


class PurchaseForwardList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[PurchaseForward]
    next_cursor: UUID | None


class MaterialRequestDetail(MaterialRequestSummary):
    pending_quantity: Quantity
    forwarded_quantity: Quantity
    purchase_forwards: list[PurchaseForward]
    history: list[MaterialRequestTransition]


class MaterialRequestList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MaterialRequestSummary]
    next_cursor: UUID | None
