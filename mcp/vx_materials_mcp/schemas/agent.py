"""Schemas do contrato interno API → Agent (`AgentRunRequest` e `AgentRunResponse` no OpenAPI)."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ToolName = Literal[
    "search_similar_materials",
    "get_pdm_template",
    "validate_and_format_pdm",
    "check_ncm_consistency",
    "enrich_from_trusted_source",
]
ChatValidationStatus = Literal["VALID", "INCOMPLETE", "INVALID", "OUT_OF_SCOPE"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoryMessage(_Contract):
    id: UUID
    author: Literal["user", "assistant"]
    content: str
    created_at: str


class AgentContext(_Contract):
    pdm_version: str
    ncm_version: str
    center_code: str
    history: list[HistoryMessage]
    confirmed_attributes: dict[str, str | None]


class AgentRunRequest(_Contract):
    turn_id: UUID
    session_id: UUID
    session_version: int = Field(ge=0)
    message: str = Field(min_length=1)
    context: AgentContext


class ToolCallRecord(_Contract):
    id: str
    name: ToolName
    transport: Literal["MCP_STDIO"] = "MCP_STDIO"
    input: dict[str, Any]
    status: Literal["SUCCEEDED", "FAILED", "PENDING"]
    duration_ms: float
    result: dict[str, Any]


class NcmCard(_Contract):
    suggested: str | None
    status: Literal["PENDING_VALIDATION", "CONSISTENT", "REVIEW_REQUIRED"]


class InventoryRow(_Contract):
    """Estoque autorizado. Preço e valor não entram na ficha, mesmo para quem pode vê-los."""

    center_code: str
    quantity: str
    unit: str


class ExistingMatch(_Contract):
    material_code: str
    status: Literal["ATIVO", "BLOQUEADO", "OBSOLETO"]
    pdm_description: str
    match_type: str
    reason: str
    inventory: list[InventoryRow]


class MaterialCard(_Contract):
    pdm_class_id: str | None
    # Opcional no contrato e nunca nulo: fica fora do JSON quando a classe é desconhecida.
    pdm_class_name: str | None = Field(default=None, exclude_if=lambda value: value is None)
    attributes: dict[str, str | None]
    pdm_description: str | None
    validation_status: ChatValidationStatus
    missing_attributes: list[str]
    ncm: NcmCard
    duplicate_check_status: Literal["PENDING", "NO_MATCH", "MATCH_FOUND"]
    existing: ExistingMatch | None = Field(default=None, exclude_if=lambda value: value is None)
    can_submit: bool


class AgentRunResponse(_Contract):
    """O status do turno não vem do agente: a API o deriva da ficha validada."""

    assistant_message: str
    tool_calls: list[ToolCallRecord] = Field(max_length=5)
    context_patch: dict[str, Any]
    material_card: MaterialCard
