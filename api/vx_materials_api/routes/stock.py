"""Disponibilidade de saldo por centro e reserva transacional para solicitações."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from vx_materials_api.routes.sanitization import Caller, Db
from vx_materials_api.schemas.stock import (
    CreateStockReservation,
    StockAvailability,
    StockReservationList,
    StockReservationResult,
)
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import stock_service as service

router = APIRouter(tags=["stock"])


@router.get("/api/v1/stock/availability", response_model=StockAvailability)
def availability(
    caller: Caller,
    db: Db,
    material_id: UUID,
    center_code: Annotated[str, Query(min_length=1, max_length=100)],
):
    return service.get_availability(db, caller, material_id, center_code)


@router.post(
    "/api/v1/material-requests/{request_id}/reservations",
    status_code=201,
    response_model=StockReservationResult,
)
def reserve(
    request_id: UUID,
    payload: CreateStockReservation,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.reserve(db, caller, request_id, payload, idempotency_key, request.state.request_id)


@router.get("/api/v1/material-requests/{request_id}/reservations", response_model=StockReservationList)
def list_reservations(request_id: UUID, caller: Caller, db: Db):
    return service.list_reservations(db, caller, request_id)
