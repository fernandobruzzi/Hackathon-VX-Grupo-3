"""Disponibilidade de saldo por centro, alternativas em outros centros, reserva, entrega, cancelamento e reversão."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from vx_materials_api.errors import ApiProblem
from vx_materials_api.routes.sanitization import Caller, Db
from vx_materials_api.schemas.material_requests import Quantity
from vx_materials_api.schemas.stock import (
    CancelStockReservation,
    CreateStockReservation,
    DeliverStockReservation,
    ReverseStockMovement,
    StockAlternatives,
    StockAvailability,
    StockMovementResult,
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


@router.get("/api/v1/stock/availability/alternatives", response_model=StockAlternatives)
def alternatives(
    caller: Caller,
    db: Db,
    material_id: UUID,
    center_code: Annotated[str, Query(min_length=1, max_length=100)],
    quantity: Annotated[Quantity | None, Query()] = None,
):
    needed = Decimal(quantity) if quantity is not None else None
    if needed is not None and needed <= 0:
        raise ApiProblem(422, "VALIDATION_ERROR", "A quantidade deve ser positiva.")
    return service.get_other_centers(db, caller, material_id, center_code, needed)


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


@router.post(
    "/api/v1/stock/reservations/{reservation_id}/deliveries",
    status_code=201,
    response_model=StockMovementResult,
)
def deliver(
    reservation_id: UUID,
    payload: DeliverStockReservation,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.deliver(db, caller, reservation_id, payload, idempotency_key, request.state.request_id)


@router.post("/api/v1/stock/reservations/{reservation_id}/cancel", response_model=StockReservationResult)
def cancel_reservation(
    reservation_id: UUID,
    payload: CancelStockReservation,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.cancel_reservation(db, caller, reservation_id, payload, idempotency_key, request.state.request_id)


@router.post(
    "/api/v1/stock/movements/{movement_id}/reversal",
    status_code=201,
    response_model=StockMovementResult,
)
def reverse_delivery(
    movement_id: UUID,
    payload: ReverseStockMovement,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return service.reverse_delivery(db, caller, movement_id, payload, idempotency_key, request.state.request_id)
