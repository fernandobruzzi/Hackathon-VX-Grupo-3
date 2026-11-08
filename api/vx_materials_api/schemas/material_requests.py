"""Solicitação de necessidade; identidade e estado são derivados no servidor."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator

RequestStatus = Literal["EM_IDENTIFICACAO", "AGUARDANDO_CADASTRO", "EM_ATENDIMENTO", "ENCERRADA"]


def _positive_quantity(value: str) -> str:
    if Decimal(value) <= 0:
        raise ValueError("A quantidade deve ser positiva.")
    return value


Quantity = Annotated[
    str,
    StringConstraints(pattern=r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$", max_length=25),
]
PositiveQuantity = Annotated[Quantity, AfterValidator(_positive_quantity)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CreateMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_text: str = Field(min_length=1, max_length=10000)
    quantity: PositiveQuantity
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
    """Encaminha a quantidade pendente inteira; a divisão com reserva parcial usa ConfirmFulfillment."""

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


ReservationStatus = Literal["ATIVA", "CONSUMIDA", "CANCELADA"]


class StockReservation(BaseModel):
    """`quantity` é a quantidade reservada original; `open_quantity` ainda conta em `R`."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    request_id: UUID
    material_id: UUID
    center_code: str
    quantity: Quantity
    delivered_quantity: Quantity
    open_quantity: Quantity
    unit: str
    status: ReservationStatus
    dataset_id: UUID
    created_by_user_id: UUID
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class MaterialSubstitution(BaseModel):
    """Troca confirmada pelo solicitante por um equivalente autorizado (#246)."""

    model_config = ConfigDict(extra="forbid")
    from_material_id: UUID
    from_material_code: str
    to_material_id: UUID
    to_material_code: str
    equivalence_id: UUID


class MaterialRequestDetail(MaterialRequestSummary):
    pending_quantity: Quantity
    reserved_quantity: Quantity
    delivered_quantity: Quantity
    forwarded_quantity: Quantity
    # As duas parcelas do atendimento (#242) aparecem juntas: reservas e encaminhamentos.
    reservations: list[StockReservation]
    purchase_forwards: list[PurchaseForward]
    substitution: MaterialSubstitution | None = None
    history: list[MaterialRequestTransition]


class MaterialRequestList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MaterialRequestSummary]
    next_cursor: UUID | None


FulfillmentOption = Literal["PARTIAL", "PURCHASING_ONLY"]
FulfillmentBlock = Literal[
    "REQUEST_NOT_IN_SERVICE",
    "INACTIVE_MATERIAL",
    "UNIT_MISMATCH",
    "NOTHING_PENDING",
    "NO_INVENTORY_DATASET",
    "RECONCILIATION_REQUIRED",
    "STOCK_UNIT_UNRESOLVED",
    "STOCK_AVAILABLE",
]


class ConfirmFulfillment(BaseModel):
    """Escolha do solicitante na falta parcial (D1); a divisão é recalculada no servidor."""

    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    option: FulfillmentOption


class FulfillmentSplit(BaseModel):
    """Quanto seria reservado do estoque e quanto seria encaminhado para compras."""

    model_config = ConfigDict(extra="forbid")
    option: FulfillmentOption
    reserve_quantity: Quantity
    forward_quantity: Quantity


class FulfillmentPreview(BaseModel):
    """Consulta da divisão; não reserva, não encaminha e não grava nada."""

    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    request_version: int = Field(ge=1)
    unit: str
    center_code: str
    requested: Quantity
    reserved: Quantity
    delivered: Quantity
    forwarded: Quantity
    pending: Quantity
    available: Quantity
    blocked_reason: FulfillmentBlock | None
    default_option: FulfillmentOption | None
    options: list[FulfillmentSplit]


class FulfillmentResult(BaseModel):
    """Parcelas efetivamente gravadas, calculadas com o disponível lido dentro do bloqueio."""

    model_config = ConfigDict(extra="forbid")
    option: FulfillmentOption
    reserved_quantity: Quantity
    forwarded_quantity: Quantity
    available_at_confirmation: Quantity
    reservation_id: UUID | None
    purchase_forward_id: UUID
    request: MaterialRequestDetail


class RegisterEquivalence(BaseModel):
    """Equivalência técnica aprovada pela Governança; não unifica materiais nem soma saldos."""

    model_config = ConfigDict(extra="forbid")
    material_id: UUID
    equivalent_material_id: UUID
    basis: str = Field(min_length=1, max_length=2000)


class MaterialEquivalence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    material_id: UUID
    equivalent_material_id: UUID
    basis: str
    status: Literal["APROVADA", "REVOGADA"]
    version: int = Field(ge=1)


class EquivalentAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equivalence_id: UUID
    material_id: UUID
    material_code: str
    description: str | None
    unit: str | None
    status: str
    available_quantity: Quantity
    basis: str
    selectable: bool
    blocked_reason: str | None


class EquivalentAlternatives(BaseModel):
    """Só aparece alternativa quando falta saldo do material pedido e há equivalência aprovada."""

    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    request_version: int = Field(ge=1)
    shortage: bool
    pending_quantity: Quantity | None = None
    available_quantity: Quantity | None = None
    items: list[EquivalentAlternative]


class SubstituteWithEquivalent(BaseModel):
    """A troca exige confirmação explícita do solicitante e fica registrada na solicitação."""

    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    material_id: UUID
    confirm_substitution: StrictBool
