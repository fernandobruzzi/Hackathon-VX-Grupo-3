"""Pendências manuais da Governança, separadas da fila de propostas."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from vx_materials_api.routes.sanitization import Caller, Db, catalog
from vx_materials_api.schemas.manual_reviews import ManualReviewResolution
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services.manual_reviews import list_reviews, propose_resolution

router = APIRouter(prefix="/api/v1/manual-reviews", tags=["manual-reviews"])


@router.get("")
def list_pending(
    db: Db,
    caller: Caller,
    run_id: UUID | None = None,
    reason: str | None = Query(default=None, max_length=200),
    material_code: str | None = Query(default=None, max_length=200),
    cursor: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    return list_reviews(
        db, caller, run_id=run_id, reason=reason, material_code=material_code, cursor=cursor, limit=limit
    )


@router.post("/{review_id}/propose", status_code=202)
def propose(
    review_id: UUID,
    payload: ManualReviewResolution,
    request: Request,
    db: Db,
    caller: Caller,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    result = propose_resolution(
        db, caller, review_id, payload, idempotency_key, request.state.request_id, catalog(request)
    )
    db.commit()
    return result


@router.get("/catalog")
def review_catalog(request: Request, caller: Caller):
    from vx_materials_api.security.rbac import require_permission

    require_permission(caller, "merge:decide")
    pdm = catalog(request)
    return {
        "pdm_version": pdm.version,
        "classes": [
            {
                "id": c.id,
                "item_names": list(c.item_names),
                "unit": c.default_unit,
                "attributes": [
                    {
                        "name": a.name,
                        "required": a.required,
                        "format": a.format,
                        "allowed_values": list(a.allowed_values or ()),
                    }
                    for a in c.attributes
                ],
                "ncm_codes": sorted({code for ref in c.ncm_references for code in ref.codes}),
            }
            for c in sorted(pdm.classes.values(), key=lambda c: c.id)
        ],
    }
