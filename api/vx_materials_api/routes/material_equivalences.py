"""Registro de equivalências técnicas aprovadas pela Governança (#246)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request

from vx_materials_api.routes.sanitization import Caller, Db
from vx_materials_api.schemas.material_requests import MaterialEquivalence, RegisterEquivalence
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import equivalence_service

router = APIRouter(prefix="/api/v1/material-equivalences", tags=["material-equivalences"])


@router.post("", status_code=201, response_model=MaterialEquivalence)
def register(
    payload: RegisterEquivalence,
    request: Request,
    caller: Caller,
    db: Db,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    return equivalence_service.register_equivalence(db, caller, payload, idempotency_key, request.state.request_id)
