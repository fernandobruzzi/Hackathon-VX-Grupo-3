"""Dashboard autenticado: qualidade para revisores e valores somente para o fiscal."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from vx_materials_api.dependencies import current_identity, db_session
from vx_materials_api.schemas.metrics import DashboardMetrics
from vx_materials_api.security.identity import Identity
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
