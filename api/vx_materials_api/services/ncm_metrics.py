"""Propostas fiscais do escopo consultado e medição documental de desenvolvimento."""

import json
from importlib.resources import files

from sqlalchemy import select

from vx_materials_api.db.models import AuditLog
from vx_materials_api.schemas.metrics import NcmBenchmark, NcmMetrics, NcmProposalCounts


def _code(value):
    normalized = (value or "").replace(".", "").replace(" ", "")
    return normalized if len(normalized) == 8 and normalized.isascii() and normalized.isdecimal() else None


def ncm_metrics(db, tenant_id, proposals, originals, before, after):
    """Cada proposta de NCM conta uma vez; somente decisão fiscal auditada mede aceitação."""
    ids = [str(proposal_id) for proposal_id, *_ in proposals]
    decisions = {}
    if ids:
        events = db.execute(
            select(AuditLog.entity_id, AuditLog.action)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.entity_type == "sanitization_proposal",
                AuditLog.entity_id.in_(ids),
                AuditLog.actor_type == "USER",
                AuditLog.actor_user_id.is_not(None),
                AuditLog.effective_role == "ROLE_AUDITOR_FISCAL",
                AuditLog.action.in_(["PROPOSAL_APPROVE_FISCAL", "PROPOSAL_REJECT_FISCAL"]),
            )
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        for proposal_id, action in events:
            decisions[proposal_id] = action
    content, formatting = NcmProposalCounts(), NcmProposalCounts()
    for proposal_id, status, members, target, before_ncm, has_before in proposals:
        # O antes da própria proposta é fixo; só o legado usa o snapshot original.
        target_code = _code(target)
        previous = [before_ncm] if has_before else [originals[member["material_id"]] for member in members]
        only_format = target_code is not None and all(_code(value) == target_code for value in previous)
        counts = formatting if only_format else content
        counts.created += 1
        action = decisions.get(str(proposal_id))
        if status == "REJECTED":
            counts.rejected += 1
        elif status == "STALE":
            counts.stale += 1
        elif action == "PROPOSAL_APPROVE_FISCAL":
            counts.fiscal_approved += 1
        elif status == "PENDING":
            counts.pending += 1
    approved = sum(action == "PROPOSAL_APPROVE_FISCAL" for action in decisions.values())
    return NcmMetrics(
        missing_before=before.missing_ncm,
        missing_after=after.missing_ncm if after else None,
        content=content,
        format_only=formatting,
        fiscal_decided=len(decisions),
        fiscal_approved_decisions=approved,
        operational_precision=approved / len(decisions) if decisions else None,
        benchmark=NcmBenchmark.model_validate(
            json.loads(files("pipelines.evaluation_data").joinpath("ncm_benchmark_v2.json").read_text(encoding="utf-8"))
        ),
    )
