"""Projecoes do contrato publico, com escopo e remocao de valores financeiros."""

from uuid import UUID

from sqlalchemy import select

from vx_materials_api.db.models import AuditLog, SanitizationProposal, UserSso
from vx_materials_api.errors import ApiError
from vx_materials_api.security.approval_identity import require_reviewer
from vx_materials_api.security.rbac import has_permission, require_any_permission
from vx_materials_api.services.approval_service import (
    consolidated_inventory,
    exact_sum,
    inventory_rows,
    load_members,
)
from vx_materials_api.services.ncm_validation import evaluate_proposed_ncm


def allowed_actions(proposal, principal):
    if proposal.status != "PENDING":
        return []
    technical = has_permission(principal, "merge:decide") and proposal.technical_review_status == "PENDING"
    fiscal = has_permission(principal, "ncm:decide") and proposal.fiscal_review_status == "PENDING"
    return ["APPROVE", "REJECT"] if technical or fiscal else []


def detail(db, proposal, principal, catalog):
    from domain.pdm_validator import validate_pdm

    interpretations, changes, materials, snapshots = load_members(db, proposal, principal)
    after = changes.after
    validation = validate_pdm(catalog, after.pdm_class_id, after.attributes, item_name=after.item_name, unit=after.unit)
    current_rows = inventory_rows(db, snapshots, None, changes)
    member_rows = []
    for material in materials:
        stock = [entry for entry in current_rows if entry["owner"] == material.id]
        row = {
            "material_code": material.material_code,
            "status": material.status,
            "description": material.pdm_description
            or material.original_description_long
            or material.original_description_short
            or "",
            "unit": material.unit,
            "ncm": material.ncm,
            "inventory": [
                {k: value for k, value in entry.items() if k != "dataset_id"} for entry in consolidated_inventory(stock)
            ],
        }
        if principal.financial and all(entry["total_value"] is not None for entry in stock):
            from decimal import Decimal

            total = Decimal(0)
            for entry in stock:
                total = exact_sum(total, entry["total_value"])
            row["value_brl"] = str(total)
        member_rows.append(row)
    conflicts = list(changes.conflicts)
    # Correcao de unidade aplica so a grafia da unidade, sem identidade: o PDM completo nao se aplica.
    unit_only = proposal.proposal_type == "UNIT_CORRECTION"
    ncm_evaluation = None
    if not unit_only and after.pdm_class_id in catalog.classes:
        try:
            ncm_evaluation = evaluate_proposed_ncm(catalog, changes)
        except ApiError as error:
            conflicts.append(error.message)
    if not unit_only and (validation.status.value != "VALID" or validation.not_applicable_attributes):
        conflicts.append("Os dados propostos nao atendem ao PDM.")
    try:
        consolidated = consolidated_inventory(
            inventory_rows(db, snapshots, after.unit, changes), financial=principal.financial
        )
    except ApiError as error:
        consolidated = []
        conflicts.append(error.message)
    first_class = catalog.classes.get(after.pdm_class_id)
    primary = next((m for m in materials if m.id == proposal.primary_material_id), None)
    labels = {
        "pdm_class_id": "Classe PDM",
        "description": "Descrição",
        "merchandise_group": "Grupo de mercadorias",
        "unit": "Unidade",
        "ncm": "NCM",
    }
    changes_rows = [
        change.model_dump() | {"field": labels.get(change.field, change.field)} for change in changes.changes
    ]
    recorded = {change.field for change in changes.changes}
    if primary and not unit_only:
        for field in ("pdm_class_id", "unit", "ncm"):
            before_value = getattr(primary, field)
            after_value = getattr(after, field)
            if before_value != after_value and field not in recorded:
                changes_rows.append(
                    {
                        "field": labels[field],
                        "before": before_value,
                        "after": after_value or "",
                        "source": changes.sources.get(field, "Fonte nao informada"),
                    }
                )
        for name, value in after.attributes.items():
            if primary.attributes.get(name) != value:
                changes_rows.append(
                    {
                        "field": name,
                        "before": primary.attributes.get(name),
                        "after": value or "",
                        "source": changes.sources.get("attributes", "Fonte nao informada"),
                    }
                )
    result = {
        "id": str(proposal.id),
        "version": proposal.version,
        "proposal_type": proposal.proposal_type,
        "status": proposal.status,
        "title": f"{after.item_name or after.pdm_class_id or 'Classe pendente'} · "
        + " / ".join(m.material_code for m in materials),
        "material_codes": [m.material_code for m in materials],
        "suggested_primary_code": primary.material_code if primary else None,
        "identity": {
            "mode": first_class.identity_mode.value if first_class else "TECHNICAL_ATTRIBUTES",
            "summary": after.item_name or after.pdm_class_id or "Classe pendente",
        },
        "members": member_rows,
        "after": {
            "description": validation.formatted_description
            or after.item_name
            or after.pdm_class_id
            or "Descrição pendente",
            "ncm": after.ncm,
            "unit": after.unit,
            "attributes": {k: v for k, v in after.attributes.items() if v is not None},
        },
        "changes": changes_rows,
        "technical_review_status": proposal.technical_review_status,
        "fiscal_review_status": proposal.fiscal_review_status,
        "conflicts": conflicts,
        "ranking_score": changes.ranking_score,
        "created_at": proposal.created_at.isoformat().replace("+00:00", "Z"),
        "ncm_assessment": ncm_evaluation,
        "allowed_actions": [
            action for action in allowed_actions(proposal, principal) if action != "APPROVE" or not conflicts
        ],
        "consolidated_inventory": [{k: v for k, v in row.items() if k != "dataset_id"} for row in consolidated],
    }
    if principal.financial:
        from decimal import Decimal

        total = Decimal(0)
        known = not conflicts
        for row in consolidated:
            if row.get("total_value") is None:
                known = False
            else:
                total = exact_sum(total, Decimal(row["total_value"]))
        result["consolidated_value_brl"] = str(total) if known else None
    return result


def queue(db, principal, catalog, *, area=None, status=None, proposal_type=None, cursor=None, limit=20):
    require_reviewer(principal)
    query = select(SanitizationProposal).where(
        SanitizationProposal.tenant_id == principal.tenant_id,
        SanitizationProposal.changeset["schema_version"].astext == "proposal-v1",
    )
    if status == "DECIDED":
        query = query.where(SanitizationProposal.status != "PENDING")
    elif status:
        query = query.where(SanitizationProposal.status == status)
    if proposal_type:
        query = query.where(SanitizationProposal.proposal_type == proposal_type)
    if area:
        field = (
            SanitizationProposal.fiscal_review_status
            if area == "FISCAL"
            else SanitizationProposal.technical_review_status
        )
        query = query.where(field == "PENDING")
    if cursor:
        query = query.where(SanitizationProposal.id > UUID(cursor))
    # O limite e aplicado apos o guard de recurso, para nao expor propostas de centros alheios.
    items = []
    for proposal in db.scalars(query.order_by(SanitizationProposal.id)):
        try:
            row = detail(db, proposal, principal, catalog)
        except ApiError as error:
            if error.status == 404:
                continue
            raise
        if len(items) == limit:
            return {"items": items, "next_cursor": items[-1]["id"]}
        items.append(
            {
                k: row[k]
                for k in (
                    "id",
                    "version",
                    "proposal_type",
                    "status",
                    "material_codes",
                    "suggested_primary_code",
                    "identity",
                    "technical_review_status",
                    "fiscal_review_status",
                    "conflicts",
                    "allowed_actions",
                    "title",
                    "ranking_score",
                    "created_at",
                )
            }
        )
    return {"items": items, "next_cursor": None}


def redact_financial(value):
    if isinstance(value, list):
        return [redact_financial(item) for item in value]
    if isinstance(value, dict):
        return {
            k: redact_financial(v)
            for k, v in value.items()
            if k
            not in {
                "total_value",
                "unit_price",
                "value_brl",
                "financial",
            }
        }
    return value


def audit_events(db, principal, *, cursor=None, limit=20):
    require_any_permission(principal, "audit:own", "audit:technical", "audit:fiscal")
    query = (
        select(AuditLog, UserSso.display_name)
        .outerjoin(UserSso, AuditLog.actor_user_id == UserSso.id)
        .where(
            AuditLog.tenant_id == principal.tenant_id,
            AuditLog.entity_type == "sanitization_proposal",
        )
    )
    if has_permission(principal, "audit:fiscal"):
        query = query.where(AuditLog.effective_role.in_(["ROLE_GOVERNANCA_PDM", "ROLE_AUDITOR_FISCAL"]))
    elif has_permission(principal, "audit:technical"):
        query = query.where(AuditLog.effective_role == "ROLE_GOVERNANCA_PDM")
    else:
        query = query.where(AuditLog.actor_user_id == principal.user_id)
    if cursor:
        query = query.where(AuditLog.id > UUID(cursor))
    items = []
    for event, actor in db.execute(query.order_by(AuditLog.id)):
        if any(
            row["center_code"] not in principal.center_codes
            for state in (event.before_json, event.after_json)
            if isinstance(state, dict)
            for row in state.get("inventory", [])
        ):
            continue
        proposal = db.get(SanitizationProposal, UUID(event.entity_id))
        if proposal is None or proposal.tenant_id != principal.tenant_id:
            continue
        try:
            load_members(db, proposal, principal)
        except ApiError:
            continue
        if len(items) == limit:
            return {"items": items, "next_cursor": items[-1]["id"]}
        before, after = event.before_json, event.after_json
        if not principal.financial:
            before, after = redact_financial(before), redact_financial(after)
        items.append(
            {
                "id": str(event.id),
                "actor": actor or "Usuario",
                "effective_role": event.effective_role,
                "action": event.action,
                "entity": f"proposta {event.entity_id}",
                "reason": event.reason,
                "request_id": event.request_id or "",
                "created_at": event.created_at.isoformat().replace("+00:00", "Z"),
                "before": before,
                "after": after,
            }
        )
    return {"items": items, "next_cursor": None}
