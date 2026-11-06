"""Aprovação em lote de correções de forma, depois de revisar uma amostra (#120, decisão da #36).

Lote = propostas pendentes com o mesmo `review_lane.lot_key` e nível 1 ou 2, gravados pelo batch (#119).
Abrir a revisão congela as propostas e versões do lote e sorteia a amostra no servidor. A decisão
exige a amostra inteira marcada: com zero erros, cada proposta é aplicada pelo mesmo serviço de
aprovação item a item, com auditoria própria; com qualquer erro, nada é aplicado e o lote volta
para a revisão individual. Nada fiscal entra em lote.
"""

import hashlib
import json
import random
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from domain.contracts import PdmCatalog
from domain.pdm_validator import validate_pdm
from vx_materials_api.db.models import AuditLog, LotReview, MaterialMaster, OperationRequest, SanitizationProposal
from vx_materials_api.errors import ApiError
from vx_materials_api.schemas.lots import LotDecision
from vx_materials_api.schemas.proposals import ProposalDecision
from vx_materials_api.security.approval_identity import Principal, require_reviewer
from vx_materials_api.services.approval_service import decide_proposal

LOT_TYPES = ("UNIT_CORRECTION", "PDM_CORRECTION")
MIN_LOT_SIZE = 20
SAMPLE_SIZE = {1: 10, 2: 20}
ROLE = "ROLE_GOVERNANCA_PDM"


def _require_governance(principal: Principal):
    # Só quem decide a revisão técnica (Governança) vê e decide lotes; o Fiscal nunca entra em lote.
    require_reviewer(principal, "TECHNICAL")


def _lock(db: Session, principal: Principal):
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 0))"), {"tenant": str(principal.tenant_id)})


def _returned_ids(db: Session, principal: Principal) -> set[str]:
    """Propostas de lotes devolvidos: seguem só pela revisão individual."""
    rows = db.scalars(
        select(LotReview.proposal_versions).where(
            LotReview.tenant_id == principal.tenant_id, LotReview.status == "RETURNED"
        )
    )
    return {proposal_id for versions in rows for proposal_id in versions}


def _candidates(db: Session, principal: Principal, lot_key: str | None = None):
    lane = SanitizationProposal.changeset["review_lane"]
    statement = select(
        SanitizationProposal.id,
        SanitizationProposal.version,
        SanitizationProposal.proposal_type,
        lane["lot_key"].astext,
        lane["tier"].astext,
    ).where(
        SanitizationProposal.tenant_id == principal.tenant_id,
        SanitizationProposal.status == "PENDING",
        SanitizationProposal.technical_review_status == "PENDING",
        SanitizationProposal.fiscal_review_status == "NOT_REQUIRED",
        SanitizationProposal.proposal_type.in_(LOT_TYPES),
        SanitizationProposal.changeset["schema_version"].astext == "proposal-v1",
        lane["tier"].astext.in_(["1", "2"]),
    )
    if lot_key is not None:
        statement = statement.where(lane["lot_key"].astext == lot_key)
    returned = _returned_ids(db, principal)
    lots = defaultdict(list)
    for proposal_id, version, proposal_type, key, tier in db.execute(statement.order_by(SanitizationProposal.id)):
        if key and str(proposal_id) not in returned:
            lots[(key, int(tier), proposal_type)].append((str(proposal_id), version))
    return lots


def _describe_key(lot_key: str, catalog: PdmCatalog) -> dict:
    parts = lot_key.split("|")
    class_id = parts[-1] if len(parts) >= 3 else None
    pdm_class = catalog.classes.get(class_id) if class_id else None
    return {
        "rule": "|".join(parts[1:-1]) if len(parts) >= 3 else lot_key,
        "pdm_class_id": class_id if pdm_class else None,
        "pdm_class_name": pdm_class.item_names[0] if pdm_class and pdm_class.item_names else None,
    }


def list_lots(db: Session, principal: Principal, catalog: PdmCatalog) -> dict:
    _require_governance(principal)
    open_reviews = {
        (review.lot_key, review.tier): review
        for review in db.scalars(
            select(LotReview).where(LotReview.tenant_id == principal.tenant_id, LotReview.status == "OPEN")
        )
    }
    items = []
    for (key, tier, proposal_type), members in _candidates(db, principal).items():
        if len(members) < MIN_LOT_SIZE:
            continue
        review = open_reviews.get((key, tier))
        items.append(
            {
                "lot_key": key,
                "tier": tier,
                "proposal_type": proposal_type,
                **_describe_key(key, catalog),
                "size": len(members),
                "sample_size": SAMPLE_SIZE[tier],
                "open_review_id": str(review.id) if review else None,
            }
        )
    items.sort(key=lambda item: (item["tier"], -item["size"], item["lot_key"]))
    return {"items": items, "min_lot_size": MIN_LOT_SIZE}


def _audit(db, principal, review, action, reason, before, after, request_id):
    audit = AuditLog(
        id=uuid.uuid4(),
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_type="USER",
        roles_snapshot=list(principal.roles),
        effective_role=ROLE,
        action=action,
        entity_type="lot_review",
        entity_id=str(review.id),
        before_json=before,
        after_json=after,
        reason=reason,
        request_id=request_id,
    )
    db.add(audit)
    return audit


def _state(review: LotReview) -> dict:
    return {
        "lot_review_id": str(review.id),
        "lot_key": review.lot_key,
        "tier": review.tier,
        "status": review.status,
        "version": review.version,
        "size": len(review.proposal_versions),
        "sample_ids": review.sample_ids,
        "marks": review.marks,
    }


def open_review(
    db: Session, principal: Principal, lot_key: str, tier: int, request_id: str, catalog: PdmCatalog
) -> tuple[int, dict]:
    """Abre a revisão do lote, ou devolve a que já está aberta: a amostra não é sorteada de novo."""
    _require_governance(principal)
    _lock(db, principal)
    existing = db.scalar(
        select(LotReview).where(
            LotReview.tenant_id == principal.tenant_id,
            LotReview.lot_key == lot_key,
            LotReview.tier == tier,
            LotReview.status == "OPEN",
        )
    )
    if existing is not None:
        return 200, review_detail(db, principal, existing.id, catalog)
    lots = _candidates(db, principal, lot_key)
    matches = [(proposal_type, members) for (_, t, proposal_type), members in lots.items() if t == tier]
    if len(matches) != 1 or len(matches[0][1]) < MIN_LOT_SIZE:
        raise ApiError(
            422, "LOT_NOT_ELIGIBLE", f"Lote precisa de ao menos {MIN_LOT_SIZE} propostas pendentes elegíveis."
        )
    proposal_type, members = matches[0]
    ids = sorted(proposal_id for proposal_id, _ in members)
    sample = sorted(random.SystemRandom().sample(ids, SAMPLE_SIZE[tier]))
    review = LotReview(
        id=uuid.uuid4(),
        tenant_id=principal.tenant_id,
        lot_key=lot_key,
        tier=tier,
        proposal_type=proposal_type,
        proposal_versions=dict(members),
        sample_ids=sample,
        marks={},
        status="OPEN",
        result={},
        created_by_user_id=principal.user_id,
        version=1,
    )
    db.add(review)
    db.flush()
    _audit(db, principal, review, "LOT_REVIEW_OPEN", None, None, _state(review), request_id)
    db.flush()
    return 201, review_detail(db, principal, review.id, catalog)


def _load_review(db: Session, principal: Principal, review_id, *, lock=False) -> LotReview:
    statement = select(LotReview).where(LotReview.id == review_id, LotReview.tenant_id == principal.tenant_id)
    review = db.scalar(statement.with_for_update() if lock else statement)
    if review is None:
        raise ApiError(404, "NOT_FOUND", "Revisão de lote não encontrada.")
    return review


def _sample_item(db: Session, proposal: SanitizationProposal, catalog: PdmCatalog) -> dict:
    changeset = proposal.changeset
    member = (proposal.members or [{}])[0]
    material = db.get(MaterialMaster, uuid.UUID(member["material_id"])) if member.get("material_id") else None
    after = changeset.get("after", {})
    description = None
    if proposal.proposal_type == "PDM_CORRECTION" and after.get("pdm_class_id"):
        description = validate_pdm(
            catalog, after["pdm_class_id"], after.get("attributes", {}), item_name=after.get("item_name")
        ).formatted_description
    return {
        "proposal_id": str(proposal.id),
        "proposal_type": proposal.proposal_type,
        "status": proposal.status,
        "material_code": material.material_code if material else None,
        "original_description": (material.original_description_long or material.original_description_short)
        if material
        else None,
        "current_description": material.pdm_description if material else None,
        "proposed_description": description,
        "changes": changeset.get("changes", []),
    }


def review_detail(db: Session, principal: Principal, review_id, catalog: PdmCatalog) -> dict:
    _require_governance(principal)
    review = _load_review(db, principal, review_id)
    proposals = {
        str(p.id): p
        for p in db.scalars(
            select(SanitizationProposal).where(
                SanitizationProposal.tenant_id == principal.tenant_id,
                SanitizationProposal.id.in_([uuid.UUID(i) for i in review.sample_ids]),
            )
        )
    }
    return {
        "id": str(review.id),
        "lot_key": review.lot_key,
        "tier": review.tier,
        "proposal_type": review.proposal_type,
        **_describe_key(review.lot_key, catalog),
        "status": review.status,
        "version": review.version,
        "size": len(review.proposal_versions),
        "sample": [_sample_item(db, proposals[i], catalog) for i in review.sample_ids if i in proposals],
        "marks": review.marks,
        "result": review.result or None,
        "created_at": review.created_at.isoformat().replace("+00:00", "Z") if review.created_at else None,
        "decided_at": review.decided_at.isoformat().replace("+00:00", "Z") if review.decided_at else None,
    }


def decide_review(
    db: Session,
    principal: Principal,
    review_id,
    decision: LotDecision,
    idempotency_key: uuid.UUID,
    request_id: str,
    catalog: PdmCatalog,
) -> tuple[int, dict]:
    _require_governance(principal)
    _lock(db, principal)
    operation = "sanitization.lot_decide"
    body_hash = hashlib.sha256(
        json.dumps({"lot_review_id": str(review_id), **decision.model_dump(mode="json")}, sort_keys=True).encode()
    ).hexdigest()
    previous = db.scalar(
        select(OperationRequest).where(
            OperationRequest.user_id == principal.user_id,
            OperationRequest.operation == operation,
            OperationRequest.idempotency_key == str(idempotency_key),
        )
    )
    review = _load_review(db, principal, review_id, lock=True)
    if previous:
        if previous.payload_hash != body_hash:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "A chave ja foi usada com outra solicitacao.")
        return previous.response["status_code"], previous.response["body"]
    if review.version != decision.expected_version:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "A revisão do lote foi alterada. Atualize a tela.",
            expected_version=decision.expected_version,
            current_version=review.version,
        )
    if review.status != "OPEN":
        raise ApiError(409, "LOT_REVIEW_FINALIZED", "Esta revisão de lote já foi decidida.")
    marks = {str(mark.proposal_id): mark.verdict for mark in decision.marks}
    if len(marks) != len(decision.marks) or set(marks) != set(review.sample_ids):
        raise ApiError(422, "SAMPLE_INCOMPLETE", "Marque cada item da amostra, e somente eles, como correto ou errado.")
    before = _state(review)
    review.marks = marks
    review.decided_by_user_id = principal.user_id
    review.decided_at = datetime.now(UTC)
    wrong = sorted(proposal_id for proposal_id, verdict in marks.items() if verdict == "WRONG")
    if wrong:
        # Qualquer erro devolve o lote inteiro para a revisão individual e registra a regra com erro.
        review.status = "RETURNED"
        review.result = {"wrong_ids": wrong, "rule": _describe_key(review.lot_key, catalog)["rule"]}
        action = "LOT_REVIEW_RETURNED"
    else:
        review.status = "APPROVED"
        review.result = _apply(db, principal, review, decision, idempotency_key, request_id, catalog)
        action = "LOT_REVIEW_APPROVE"
    review.version += 1
    audit = _audit(
        db, principal, review, action, decision.reason, before, {**_state(review), "result": review.result}, request_id
    )
    body = {
        "lot_review_id": str(review.id),
        "status": review.status,
        "version": review.version,
        "result": review.result,
        "audit_event_id": str(audit.id),
    }
    db.add(
        OperationRequest(
            user_id=principal.user_id,
            operation=operation,
            idempotency_key=str(idempotency_key),
            payload_hash=body_hash,
            status="COMPLETED",
            resource_id=str(review.id),
            response={"status_code": 200, "body": body},
        )
    )
    db.flush()
    return 200, body


def _apply(db, principal, review, decision, idempotency_key, request_id, catalog) -> dict:
    """Aplica cada proposta pelo fluxo normal, uma por vez e cada uma num savepoint.

    Um item que falha (mudou, foi decidido à parte, deixou de valer o PDM) volta ao estado anterior
    e não bloqueia os outros. Nenhum item fica aplicado pela metade.
    """
    lot = {"id": str(review.id), "lot_key": review.lot_key, "tier": review.tier, "sample_ids": review.sample_ids}
    reason = (
        f"Lote {review.lot_key} aprovado após amostra de {len(review.sample_ids)} itens sem erros. {decision.reason}"
    )
    counts = {"APPLIED": 0, "STALE": 0, "SKIPPED": 0}
    items = []
    for proposal_id, version in sorted(review.proposal_versions.items()):
        item_key = uuid.uuid5(idempotency_key, proposal_id)
        payload = ProposalDecision(
            expected_version=version, review_area="TECHNICAL", decision="APPROVE", reason=reason[:2000]
        )
        try:
            with db.begin_nested():
                status, body = decide_proposal(
                    db, principal, uuid.UUID(proposal_id), payload, item_key, request_id, catalog, lot=lot
                )
        except ApiError as error:
            counts["SKIPPED"] += 1
            items.append({"proposal_id": proposal_id, "status": "SKIPPED", "code": error.code})
            continue
        if status == 200:
            outcome = body["status"] if body["status"] in counts else "APPLIED"
        else:
            outcome = "STALE"
        counts[outcome] += 1
        item = {"proposal_id": proposal_id, "status": outcome}
        if status != 200:
            item["code"] = body["error"]["code"]
        items.append(item)
    return {"counts": counts, "items": items}
