"""Fila e decisao com verificacao de identidade, acao e recurso no servidor."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vx_materials_api.db.models import SanitizationProposal
from vx_materials_api.dependencies import get_db
from vx_materials_api.errors import ApiError
from vx_materials_api.schemas.proposals import ProposalDecision
from vx_materials_api.security.approval_identity import Principal, get_principal, require_reviewer, verify_write
from vx_materials_api.services.approval_service import decide_proposal
from vx_materials_api.services.proposal_queries import audit_events, detail, queue

router = APIRouter(prefix="/api/v1")
Db = Annotated[Session, Depends(get_db)]
Caller = Annotated[Principal, Depends(get_principal)]


def catalog(request: Request):
    import os
    from pathlib import Path

    from domain.pdm_loader import load_pdm
    from vx_materials_api import settings

    if request.app.state.pdm_catalog is None:
        request.app.state.pdm_catalog = load_pdm(
            os.environ.get("PDM_WORKBOOK_PATH", str(Path(settings.data_dir()) / "03_padrao_cadastro_PDM.xlsx"))
        )
    return request.app.state.pdm_catalog


@router.get("/sanitization/queue")
def get_queue(
    request: Request,
    db: Db,
    caller: Caller,
    review_area: Literal["TECHNICAL", "FISCAL"] | None = None,
    status: Literal["PENDING", "APPLIED", "REJECTED", "STALE", "DECIDED"] | None = None,
    proposal_type: Literal["MERGE", "PDM_CORRECTION", "UNIT_CORRECTION", "NCM_CORRECTION", "ENRICHMENT", "COMPOSITE"]
    | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: UUID | None = None,
):
    return queue(
        db,
        caller,
        catalog(request),
        area=review_area,
        status=status,
        proposal_type=proposal_type,
        limit=limit,
        cursor=str(cursor) if cursor else None,
    )


@router.get("/sanitization/{proposal_id}")
def get_proposal(proposal_id: UUID, request: Request, db: Db, caller: Caller):
    require_reviewer(caller)
    proposal = db.get(SanitizationProposal, proposal_id)
    if (
        proposal is None
        or proposal.tenant_id != caller.tenant_id
        or not isinstance(proposal.changeset, dict)
        or proposal.changeset.get("schema_version") != "proposal-v1"
    ):
        raise ApiError(404, "NOT_FOUND", "Proposta nao encontrada.")
    return detail(db, proposal, caller, catalog(request))


@router.post("/sanitization/{proposal_id}/decide")
def decide(
    proposal_id: UUID,
    payload: ProposalDecision,
    request: Request,
    db: Db,
    caller: Caller,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    verify_write(request, caller)
    try:
        code, body = decide_proposal(
            db, caller, proposal_id, payload, idempotency_key, request.state.request_id, catalog(request)
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if (
            getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            == "uq_materials_master_canonical_identity"
        ):
            raise ApiError(409, "IDENTITY_CONFLICT", "Ja existe um principal ativo para esta identidade.") from None
        raise ApiError(503, "DATABASE_UNAVAILABLE", "Nao foi possivel registrar a transacao.") from None
    return JSONResponse(body, status_code=code)


@router.get("/audit")
def get_audit(db: Db, caller: Caller, limit: int = Query(default=20, ge=1, le=100), cursor: UUID | None = None):
    return audit_events(db, caller, limit=limit, cursor=str(cursor) if cursor else None)
