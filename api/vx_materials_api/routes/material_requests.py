"""Criação, consulta e cancelamento da solicitação pelo próprio solicitante."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from vx_materials_api.routes.sanitization import Caller, Db
from vx_materials_api.schemas.material_requests import (
    CancelMaterialRequest,
    CreateMaterialRequest,
    MaterialRequestDetail,
    MaterialRequestList,
    RequestStatus,
)
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import material_request_service as service

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
