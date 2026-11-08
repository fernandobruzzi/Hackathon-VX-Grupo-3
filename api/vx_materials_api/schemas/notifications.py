"""Notificações do solicitante (#249), derivadas da auditoria."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class Notification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    request_id: UUID | None
    protocol: str | None
    action: str
    title: str
    reason: str | None
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    """`unread_count` é o total real de não lidas, não o tamanho da página."""

    model_config = ConfigDict(extra="forbid")
    items: list[Notification]
    unread_count: int = Field(ge=0)
    next_cursor: UUID | None


class MarkNotificationsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID] = Field(default_factory=list, max_length=100)
    all: StrictBool = False
