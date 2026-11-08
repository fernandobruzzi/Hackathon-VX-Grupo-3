"""Fila de Compras: lê, aceita ou devolve encaminhamentos dos centros autorizados."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from vx_materials_api.routes.sanitization import Caller, Db
from vx_materials_api.schemas.material_requests import (
    AcceptPurchaseForward,
    PurchaseForward,
    PurchaseForwardList,
    PurchaseForwardStatus,
    ReturnPurchaseForward,
)
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import purchase_forward_service as service

router = APIRouter(prefix="/api/v1/purchase-forwards", tags=["purchase-forwards"])


@router.get("", response_model=PurchaseForwardList)
def list_forwards(
    caller: Caller,
    db: Db,
    status: PurchaseForwardStatus | None = None,
    center_code: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
):
    return service.list_forwards(db, caller, status=status, center_code=center_code, limit=limit, cursor=cursor)


@router.get("/{forward_id}", response_model=PurchaseForward)
def get(forward_id: UUID, caller: Caller, db: Db):
    return service.get_forward(db, caller, forward_id)


@router.post("/{forward_id}/accept", response_model=PurchaseForward)
def accept(
    forward_id: UUID,
    payload: AcceptPurchaseForward,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.handle_forward(
        db, caller, forward_id, payload, idempotency_key, request.state.request_id, accept=True
    )


@router.post("/{forward_id}/return", response_model=PurchaseForward)
def return_forward(
    forward_id: UUID,
    payload: ReturnPurchaseForward,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.handle_forward(
        db, caller, forward_id, payload, idempotency_key, request.state.request_id, accept=False
    )
