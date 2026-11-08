"""Criação, consulta e cancelamento da solicitação pelo próprio solicitante."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from vx_materials_api.routes.sanitization import Caller, Db
from vx_materials_api.schemas.material_requests import (
    CancelMaterialRequest,
    ConfirmFulfillment,
    CreateMaterialRequest,
    ForwardToPurchasing,
    FulfillmentPreview,
    FulfillmentResult,
    MaterialRequestDetail,
    MaterialRequestList,
    RequestStatus,
)
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import material_request_service as service
from vx_materials_api.services import partial_fulfillment_service, purchase_forward_service

router = APIRouter(prefix="/api/v1/material-requests", tags=["material-requests"])


@router.post("", status_code=201, response_model=MaterialRequestDetail)
def create(
    payload: CreateMaterialRequest,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.create_request(db, caller, payload, idempotency_key, request.state.request_id)


@router.get("", response_model=MaterialRequestList)
def list_requests(
    caller: Caller,
    db: Db,
    status: RequestStatus | None = None,
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
):
    return service.list_requests(db, caller, status=status, mine=mine, limit=limit, cursor=cursor)


@router.get("/{request_id}", response_model=MaterialRequestDetail)
def get(request_id: UUID, caller: Caller, db: Db):
    return service.get_request(db, caller, request_id)


@router.post("/{request_id}/cancel", response_model=MaterialRequestDetail)
def cancel(
    request_id: UUID,
    payload: CancelMaterialRequest,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.cancel_request(db, caller, request_id, payload, idempotency_key, request.state.request_id)


@router.post("/{request_id}/purchase-forwards", status_code=201, response_model=MaterialRequestDetail)
def forward_to_purchasing(
    request_id: UUID,
    payload: ForwardToPurchasing,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return purchase_forward_service.forward_request(
        db, caller, request_id, payload, idempotency_key, request.state.request_id
    )


@router.get("/{request_id}/fulfillment-options", response_model=FulfillmentPreview)
def fulfillment_options(request_id: UUID, caller: Caller, db: Db):
    return partial_fulfillment_service.preview(db, caller, request_id)


@router.post("/{request_id}/fulfillment", status_code=201, response_model=FulfillmentResult)
def confirm_fulfillment(
    request_id: UUID,
    payload: ConfirmFulfillment,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return partial_fulfillment_service.confirm(
        db, caller, request_id, payload, idempotency_key, request.state.request_id
    )
