"""Notificações do solicitante sobre as próprias solicitações (#249)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from vx_materials_api.routes.sanitization import Caller, Db
from vx_materials_api.schemas.notifications import MarkNotificationsRead, NotificationList
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import notification_service as service

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
def list_notifications(
    caller: Caller,
    db: Db,
    unread: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
):
    return service.list_notifications(db, caller, unread_only=unread, cursor=cursor, limit=limit)


@router.post("/read", response_model=NotificationList)
def mark_read(
    payload: MarkNotificationsRead,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    # Marcar como lida é idempotente por natureza; a chave segue o padrão das escritas.
    verify_write(request, caller)
    return service.mark_read(db, caller, payload)
