"""Indicadores da jornada do solicitante, lidos das solicitações, encaminhamentos e auditoria persistidos.

Tudo fica no tenant e nos centros autorizados da sessão (centro de destino da solicitação).
Nenhum indicador é estimado: sem dados que o sustentem, ele volta nulo e listado em `unavailable`.
As contagens não carregam quantidades, preços nem valores.
"""

import math
from collections import Counter
from statistics import median

from sqlalchemy import Text, cast, func, select

from vx_materials_api.db.models import AuditLog, ChatSession, MaterialMaster, MaterialRequest, PurchaseForward
from vx_materials_api.schemas.metrics import (
    ClosedRequestCounts,
    OpenRequestCounts,
    RequestJourney,
    ResolutionTime,
    UnavailableIndicator,
)

# Encerramentos por atendimento (stock_service.close_if_fulfilled); cancelamento não é resolução.
RESOLVED_REASONS = ("ATENDIDA_ESTOQUE", "ATENDIDA_PARCIAL_COMPRAS", "ENCAMINHADA_COMPRAS")
# Encaminhamentos que continuam valendo como demanda para Compras.
LIVE_FORWARDS = ("ENCAMINHADO", "ACEITO")


def _percentile(values: list[float], fraction: float) -> float:
    """Percentil pelo posto mais próximo: sempre um valor observado, nunca interpolado."""
    ordered = sorted(values)
    return ordered[max(math.ceil(fraction * len(ordered)) - 1, 0)]


def _resolution_time(db, identity, scoped) -> ResolutionTime | None:
    closed_at = (
        select(
            AuditLog.entity_id.label("entity_id"),
            func.min(AuditLog.created_at).label("closed_at"),
        )
        .where(
            AuditLog.tenant_id == identity.tenant_id,
            AuditLog.entity_type == "material_request",
            AuditLog.action == "MATERIAL_REQUEST_CLOSED",
        )
        .group_by(AuditLog.entity_id)
        .subquery()
    )
    rows = db.execute(
        select(MaterialRequest.created_at, closed_at.c.closed_at)
        .join(closed_at, closed_at.c.entity_id == cast(MaterialRequest.id, Text))
        .where(*scoped, MaterialRequest.closure_reason.in_(RESOLVED_REASONS))
    ).all()
    hours = [max((closed - created).total_seconds(), 0) / 3600 for created, closed in rows]
    if not hours:
        return None
    return ResolutionTime(
        resolved_requests=len(hours),
        median_hours=round(median(hours), 2),
        p90_hours=round(_percentile(hours, 0.9), 2),
    )


def _identified_under_other_code(db, identity, scoped) -> int | None:
    """Solicitações cujo material é o código ativo que a busca do chat vinculado comprovou.

    Vale a correspondência de identidade salva na conversa (`duplicate_check.existing`): o mesmo
    código ativo, ou o código bloqueado cujo `active_code_target` é o material da solicitação.
    Semelhança sem identidade comprovada não conta. Sem solicitação vinculada a conversa, não há
    base para o indicador.
    """
    linked = db.execute(
        select(MaterialRequest.material_id, ChatSession.context)
        .join(ChatSession, ChatSession.id == MaterialRequest.chat_session_id)
        .where(*scoped, ChatSession.tenant_id == identity.tenant_id)
    ).all()
    if not linked:
        return None
    matches = {}
    for material_id, context in linked:
        check = (context or {}).get("duplicate_check") if isinstance(context, dict) else None
        existing = check.get("existing") if isinstance(check, dict) else None
        code = existing.get("material_code") if isinstance(existing, dict) else None
        if material_id is not None and isinstance(code, str):
            matches.setdefault(code, []).append(material_id)
    if not matches:
        return 0
    found = db.execute(
        select(MaterialMaster.material_code, MaterialMaster.id, MaterialMaster.active_code_target).where(
            MaterialMaster.tenant_id == identity.tenant_id, MaterialMaster.material_code.in_(list(matches))
        )
    ).all()
    targets = {code: {material, target} - {None} for code, material, target in found}
    return sum(material_id in targets.get(code, set()) for code, ids in matches.items() for material_id in ids)


def journey(db, identity) -> RequestJourney:
    scoped = (
        MaterialRequest.tenant_id == identity.tenant_id,
        MaterialRequest.center_code.in_(identity.center_codes),
    )
    states = Counter()
    reasons = Counter()
    for status, reason, count in db.execute(
        select(MaterialRequest.status, MaterialRequest.closure_reason, func.count())
        .where(*scoped)
        .group_by(MaterialRequest.status, MaterialRequest.closure_reason)
    ):
        states[status] += count
        if reason is not None:
            reasons[reason] += count
    total = sum(states.values())
    if not total:
        return RequestJourney(
            requests_total=0,
            open=None,
            closed=None,
            resolution_time=None,
            registration_avoided=None,
            identified_under_other_code=None,
            unavailable=[
                UnavailableIndicator(indicator=name, reason="NO_REQUESTS")
                for name in ("requests", "resolution_time", "registration_avoided", "identified_under_other_code")
            ],
        )
    unavailable = []
    resolution = _resolution_time(db, identity, scoped)
    if resolution is None:
        unavailable.append(UnavailableIndicator(indicator="resolution_time", reason="NO_RESOLVED_REQUESTS"))
    identified = _identified_under_other_code(db, identity, scoped)
    if identified is None:
        unavailable.append(
            UnavailableIndicator(indicator="identified_under_other_code", reason="NO_CHAT_LINKED_REQUESTS")
        )
    # Cadastro evitado: atendida por Compras com o código já existente, sem pedido de cadastro.
    avoided = db.scalar(
        select(func.count(func.distinct(MaterialRequest.id)))
        .join(PurchaseForward, PurchaseForward.material_request_id == MaterialRequest.id)
        .where(
            *scoped,
            PurchaseForward.tenant_id == identity.tenant_id,
            PurchaseForward.status.in_(LIVE_FORWARDS),
            MaterialRequest.registration_order_id.is_(None),
        )
    )
    return RequestJourney(
        requests_total=total,
        open=OpenRequestCounts(
            em_identificacao=states["EM_IDENTIFICACAO"],
            aguardando_cadastro=states["AGUARDANDO_CADASTRO"],
            em_atendimento=states["EM_ATENDIMENTO"],
        ),
        closed=ClosedRequestCounts(
            atendida_estoque=reasons["ATENDIDA_ESTOQUE"],
            atendida_parcial_compras=reasons["ATENDIDA_PARCIAL_COMPRAS"],
            encaminhada_compras=reasons["ENCAMINHADA_COMPRAS"],
            cancelada=reasons["CANCELADA"],
            cadastro_rejeitado=reasons["CADASTRO_REJEITADO"],
        ),
        resolution_time=resolution,
        registration_avoided=avoided,
        identified_under_other_code=identified,
        unavailable=unavailable,
    )
