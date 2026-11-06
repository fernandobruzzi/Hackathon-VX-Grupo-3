"""Dashboard autenticado: qualidade para revisores, valores somente para o fiscal e snapshot posterior."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from clients.storage import get_object_store
from vx_materials_api.dependencies import current_identity, db_session
from vx_materials_api.errors import request_id
from vx_materials_api.schemas.metrics import DashboardMetrics, QualitySnapshotOut, QualitySnapshotRequest
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import snapshot_service
from vx_materials_api.services.metrics_service import metrics

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics, response_model_exclude_unset=True)
def get_metrics(
    response: Response,
    identity: Annotated[Identity, Depends(current_identity)],
    db: Annotated[Session, Depends(db_session)],
    view: Literal["quality", "executive"] = "quality",
    dataset_id: UUID | None = None,
):
    result = metrics(db, identity, view=view, dataset_id=dataset_id)
    # Campos nulos são parte do contrato; só financial é omitido na visão de qualidade.
    response.headers["Cache-Control"] = "no-store"
    payload = result.model_dump(mode="json")
    if result.financial is None:
        payload.pop("financial")
    return payload


@router.post("/snapshots", status_code=201)
def create_snapshot(
    payload: QualitySnapshotRequest,
    request: Request,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    identity: Annotated[Identity, Depends(current_identity)],
    db: Annotated[Session, Depends(db_session)],
) -> QualitySnapshotOut:
    """Registra a base depois das propostas aplicadas. Só a Governança (`batch:run`) gera snapshots."""
    verify_write(request, identity)
    return snapshot_service.create_snapshot(
        db, identity, get_object_store(), payload, idempotency_key, request_id(request)
    )
