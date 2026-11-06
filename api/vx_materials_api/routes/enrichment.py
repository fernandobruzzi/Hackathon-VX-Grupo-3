"""Evidências persistidas, com o escopo e a autorização da fila de revisão."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.pdm_formatter import format_description
from domain.pdm_validator import validate_pdm
from domain.proposal_validation import is_approvable
from vx_materials_api.db.models import EnrichmentSource, SanitizationProposal
from vx_materials_api.dependencies import get_db
from vx_materials_api.errors import ApiError
from vx_materials_api.routes.sanitization import catalog
from vx_materials_api.security.approval_identity import Principal, get_principal, require_reviewer
from vx_materials_api.services.approval_service import load_members
from vx_materials_api.services.proposal_queries import allowed_actions

router = APIRouter(prefix="/api/v1/enrichment")
Db = Annotated[Session, Depends(get_db)]
Caller = Annotated[Principal, Depends(get_principal)]


def _detail(db, proposal, caller, pdm):
    interpretations, changes, materials, _ = load_members(db, proposal, caller)
    if proposal.proposal_type != "ENRICHMENT" or len(materials) != 1:
        raise ApiError(404, "NOT_FOUND", "Proposta de enriquecimento nao encontrada.")
    material = materials[0]
    baseline = interpretations[0].attributes
    context = changes.enrichment_context
    held = set(context.divergent_attributes + context.blocked_attributes) if context else set()
    sources = list(
        db.scalars(
            select(EnrichmentSource)
            .where(
                EnrichmentSource.tenant_id == caller.tenant_id,
                EnrichmentSource.material_id == material.id,
                EnrichmentSource.id.in_([UUID(v) for v in proposal.evidence_ids]),
            )
            .order_by(EnrichmentSource.attribute_name, EnrichmentSource.id)
        )
    )
    checked = validate_pdm(pdm, changes.after.pdm_class_id, changes.after.attributes, item_name=changes.after.item_name)
    actions = allowed_actions(proposal, caller)
    if changes.conflicts or not is_approvable(checked, allow_incomplete=bool(context)):
        actions = [action for action in actions if action != "APPROVE"]
    return {
        "proposal_id": str(proposal.id),
        "version": proposal.version,
        "material_code": material.material_code,
        "original_description": material.original_description_long or "",
        "proposed_description": format_description(
            pdm.classes[changes.after.pdm_class_id], changes.after.item_name, changes.after.attributes
        )
        if changes.after.item_name
        else (material.original_description_long or "Dados parciais"),
        "pdm_class_id": changes.after.pdm_class_id,
        "status": proposal.status,
        "technical_review_status": proposal.technical_review_status,
        "fiscal_review_status": proposal.fiscal_review_status,
        "allowed_actions": actions,
        "pending_attributes": [a.name for a in checked.missing_attributes],
        "evidence": [
            {
                "attribute": source.attribute_name,
                "current_value": baseline.get(source.attribute_name),
                "proposed_value": source.proposed_value,
                "source_title": source.source_title or "Fonte registrada",
                "source_url": source.source_url,
                "source_excerpt": source.source_excerpt or "",
                "source_page": source.source_page,
                "source_sha256": source.source_sha256,
                "confidence": {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAIXA"}[source.confidence_level],
                "confidence_basis": source.confidence_basis,
                "simulated": "SIMULATED" in (source.confidence_basis or []),
                "included_in_proposal": source.attribute_name not in held
                and changes.after.attributes.get(source.attribute_name) == source.proposed_value
                and baseline.get(source.attribute_name) != source.proposed_value,
                "divergence": "Valor divergente ou incompatível com o PDM; fora desta aprovação."
                if source.attribute_name in held
                else None,
            }
            for source in sources
        ],
    }


@router.get("")
def list_enrichment(
    request: Request, db: Db, caller: Caller, limit: int = Query(default=20, ge=1, le=100), cursor: UUID | None = None
):
    require_reviewer(caller)
    query = select(SanitizationProposal).where(
        SanitizationProposal.tenant_id == caller.tenant_id,
        SanitizationProposal.proposal_type == "ENRICHMENT",
        SanitizationProposal.changeset["schema_version"].astext == "proposal-v1",
    )
    if cursor:
        query = query.where(SanitizationProposal.id > cursor)
    items = []
    for proposal in db.scalars(query.order_by(SanitizationProposal.id)):
        try:
            item = _detail(db, proposal, caller, catalog(request))
        except ApiError as error:
            if error.status == 404:
                continue
            raise
        if len(items) == limit:
            return {"items": items, "next_cursor": items[-1]["proposal_id"]}
        items.append(item)
    return {"items": items, "next_cursor": None}


@router.get("/{proposal_id}")
def get_enrichment(proposal_id: UUID, request: Request, db: Db, caller: Caller):
    require_reviewer(caller)
    proposal = db.get(SanitizationProposal, proposal_id)
    if proposal is None or proposal.tenant_id != caller.tenant_id:
        raise ApiError(404, "NOT_FOUND", "Proposta de enriquecimento nao encontrada.")
    return _detail(db, proposal, caller, catalog(request))
