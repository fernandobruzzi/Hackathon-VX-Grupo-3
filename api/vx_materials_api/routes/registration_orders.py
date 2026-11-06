"""Pedidos de cadastro: lista, submissão do dono e decisão da Governança e do Fiscal (#24)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from vx_materials_api.dependencies import current_identity, db_session
from vx_materials_api.errors import request_id
from vx_materials_api.routes.sanitization import catalog
from vx_materials_api.schemas.orders import OrderComplementRequest, OrderDecisionRequest, OrderSubmitRequest
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import order_service

router = APIRouter(prefix="/api/v1/registration-orders", tags=["orders"])
Caller = Annotated[Identity, Depends(current_identity)]
Db = Annotated[Session, Depends(db_session)]
Status = Literal[
    "DRAFT", "INCOMPLETE", "READY_FOR_REVIEW", "EXISTING", "OUT_OF_SCOPE", "PENDING_FISCAL", "REGISTERED", "REJECTED"
]


@router.get("")
def list_orders(
    caller: Caller,
    db: Db,
    status: Status | None = None,
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
):
    return order_service.list_orders(db, caller, status=status, mine=mine, limit=limit, cursor=cursor)


@router.post("/{order_id}/submit")
def submit_order(
    order_id: UUID,
    payload: OrderSubmitRequest,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return order_service.submit_order(
        db, caller, catalog(request), order_id, payload.expected_version, idempotency_key, request_id(request)
    )


@router.post("/{order_id}/decide")
def decide_order(
    order_id: UUID,
    payload: OrderDecisionRequest,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return order_service.decide_order(
        db, caller, catalog(request), order_id, payload, idempotency_key, request_id(request)
    )


@router.post("/{order_id}/complement")
def complement_order(
    order_id: UUID,
    payload: OrderComplementRequest,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return order_service.complement_order(
        db, caller, catalog(request), order_id, payload, idempotency_key, request_id(request)
    )
@router.get("/{order_id}")
def order_review(order_id: UUID, request: Request, caller: Caller, db: Db):
    return order_service.get_order_review(db, caller, catalog(request), order_id)
