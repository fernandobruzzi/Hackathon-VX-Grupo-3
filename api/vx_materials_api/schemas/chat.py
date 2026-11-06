"""Schemas de conversa (`ChatMessageRequest`, `ChatTurnResponse` e retorno do Agent no OpenAPI)."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatAction(_Contract):
    """Ação dos botões do front. O texto exibido no botão não importa: vale o tipo e o código."""

    type: Literal["PICK_CANDIDATE", "DISMISS_CANDIDATES"]
    material_code: str | None = None


class ChatMessageRequest(_Contract):
    session_id: UUID | None
    client_message_id: UUID
    expected_session_version: int = Field(ge=0)
    message: str = Field(min_length=1)
    center_code: str
    action: ChatAction | None = None


class ToolCall(_Contract):
    id: str
    name: Literal[
        "search_similar_materials",
        "get_pdm_template",
        "validate_and_format_pdm",
        "check_ncm_consistency",
        "enrich_from_trusted_source",
    ]
    transport: Literal["MCP_STDIO"]
    input: dict[str, Any]
    status: Literal["SUCCEEDED", "FAILED", "PENDING"]
    duration_ms: float | None = Field(default=None, exclude_if=lambda value: value is None)
    result: dict[str, Any]


class NcmCard(_Contract):
    suggested: str | None
    status: Literal["PENDING_VALIDATION", "CONSISTENT", "REVIEW_REQUIRED"]


class InventoryRow(_Contract):
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


class SimilarCandidate(_Contract):
    material_code: str
    status: Literal["ATIVO", "BLOQUEADO", "OBSOLETO"]
    pdm_description: str
    active_code_target: str | None


class MaterialCard(_Contract):
    pdm_class_id: str | None
    pdm_class_name: str | None = Field(default=None, exclude_if=lambda value: value is None)
    attributes: dict[str, str | None]
    pdm_description: str | None
    validation_status: Literal["VALID", "INCOMPLETE", "INVALID", "OUT_OF_SCOPE"]
    missing_attributes: list[str]
    ncm: NcmCard
    duplicate_check_status: Literal["PENDING", "NO_MATCH", "MATCH_FOUND"]
    existing: ExistingMatch | None = Field(default=None, exclude_if=lambda value: value is None)
    similar_candidates: list[SimilarCandidate] = Field(default_factory=list)
    can_submit: bool


class AgentRunResponse(_Contract):
    """Retorno do Agent, validado antes de qualquer persistência."""

    assistant_message: str
    tool_calls: list[ToolCall] = Field(max_length=5)
    context_patch: dict[str, Any]
    material_card: MaterialCard


class ChatTurnResponse(_Contract):
    request_id: str
    session_id: UUID
    session_version: int
    order_id: UUID | None
    status: Literal["NEEDS_INPUT", "EXISTING", "READY_TO_SUBMIT", "SUBMITTED", "OUT_OF_SCOPE"]
    assistant_message: str
    tool_calls: list[ToolCall]
    material_card: MaterialCard


class ChatSubmitRequest(_Contract):
    expected_session_version: int = Field(ge=1)


class ChatSubmitResponse(_Contract):
    session_id: UUID
    session_version: int
    order_id: UUID
    status: Literal["READY_FOR_REVIEW", "EXISTING"]


class ChatSessionSummary(_Contract):
    id: UUID
    title: str
    updated_at: str


class ChatSessionList(_Contract):
    items: list[ChatSessionSummary]
    next_cursor: str | None


class SavedChatMessage(_Contract):
    id: UUID
    author: Literal["user", "assistant"]
    content: str
    created_at: str


class SavedToolCall(_Contract):
    turn: int
    call: ToolCall


class ChatSessionDetail(_Contract):
    session_id: UUID
    session_version: int
    processing: bool
    center_code: str | None
    messages: list[SavedChatMessage]
    calls: list[SavedToolCall]
    material_card: MaterialCard | None
    order_id: UUID | None
