"""Equivalentes tecnicamente autorizados quando o material pedido está sem saldo (#246, caminho 6).

Equivalência não é identidade: os materiais continuam separados, com códigos e saldos próprios, e
nada aqui unifica materiais nem soma estoques. Só uma equivalência aprovada pela Governança vira
alternativa, e a troca exige confirmação explícita do solicitante, registrada na solicitação.
Produto apenas parecido, sem registro aprovado, nunca é oferecido.
"""

from uuid import uuid4

from sqlalchemy import or_, select

from domain.proposals import canonical_hash
from vx_materials_api.db.models import AuditLog, MaterialEquivalence, MaterialMaster, OperationRequest
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import require_permission
from vx_materials_api.services.material_request_service import (
    _audit,
    _find,
    _previous,
    claim_idempotency,
    detail,
    quantity_text,
    remember_idempotency,
    summary,
)
from vx_materials_api.services.purchase_forward_service import locked_shortage
from vx_materials_api.services.stock_service import compute_availability, fulfillment


def _pair(first, second):
    return (first, second) if str(first) < str(second) else (second, first)


def equivalence_view(row: MaterialEquivalence) -> dict:
    return {
        "id": str(row.id),
        "material_id": str(row.material_id),
        "equivalent_material_id": str(row.equivalent_material_id),
        "basis": row.basis,
        "status": row.status,
        "version": row.version,
    }


def _material(db, caller, material_id):
    material = db.scalar(
        select(MaterialMaster).where(MaterialMaster.id == material_id, MaterialMaster.tenant_id == caller.tenant_id)
    )
    if material is None:
        raise ApiProblem(404, "NOT_FOUND", "Material não encontrado.")
    return material


def register_equivalence(db, caller, payload, key, correlation_id):
    """Governança registra uma equivalência técnica aprovada, com a base da decisão."""
    role = require_permission(caller, "merge:decide")
    digest = canonical_hash(payload.model_dump(mode="json"))
    operation = "material-equivalence.register"
    previous = claim_idempotency(db, caller, operation, key, digest)
    if previous:
        return previous.response
    if payload.material_id == payload.equivalent_material_id:
        raise ApiProblem(422, "SAME_MATERIAL", "Um material não é equivalente a si mesmo.")
    first, second = (_material(db, caller, item) for item in _pair(payload.material_id, payload.equivalent_material_id))
    row = db.scalar(
        select(MaterialEquivalence)
        .where(
            MaterialEquivalence.tenant_id == caller.tenant_id,
            MaterialEquivalence.material_id == first.id,
            MaterialEquivalence.equivalent_material_id == second.id,
        )
        .with_for_update()
    )
    before = equivalence_view(row) if row else None
    if row is None:
        row = MaterialEquivalence(
            id=uuid4(),
            tenant_id=caller.tenant_id,
            material_id=first.id,
            equivalent_material_id=second.id,
            basis=payload.basis.strip(),
            status="APROVADA",
            approved_by_user_id=caller.user_id,
        )
        db.add(row)
    elif row.status == "APROVADA":
        raise ApiProblem(409, "EQUIVALENCE_EXISTS", "A equivalência já está aprovada.")
    else:
        row.status, row.basis, row.approved_by_user_id = "APROVADA", payload.basis.strip(), caller.user_id
        row.version += 1
    db.flush()
    response = equivalence_view(row)
    db.add(
        AuditLog(
            tenant_id=caller.tenant_id,
            actor_user_id=caller.user_id,
            actor_type="USER",
            roles_snapshot=list(caller.roles),
            effective_role=role,
            action="MATERIAL_EQUIVALENCE_APPROVED",
            entity_type="material_equivalence",
            entity_id=str(row.id),
            before_json=before,
            after_json=response,
            reason=row.basis,
            request_id=correlation_id,
        )
    )
    db.add(
        OperationRequest(
            user_id=caller.user_id,
            operation=operation,
            idempotency_key=str(key),
            payload_hash=digest,
            status="SUCCEEDED",
            resource_id=str(row.id),
            response=response,
        )
    )
    db.commit()
    return response


def approved_equivalents(db, tenant_id, material_id):
    """Equivalências aprovadas do material, nos dois sentidos, com o outro material."""
    rows = db.scalars(
        select(MaterialEquivalence).where(
            MaterialEquivalence.tenant_id == tenant_id,
            MaterialEquivalence.status == "APROVADA",
            or_(
                MaterialEquivalence.material_id == material_id,
                MaterialEquivalence.equivalent_material_id == material_id,
            ),
        )
    )
    result = []
    for row in rows:
        other_id = row.equivalent_material_id if row.material_id == material_id else row.material_id
        other = db.scalar(select(MaterialMaster).where(MaterialMaster.id == other_id))
        if other is not None:
            result.append((row, other))
    return sorted(result, key=lambda item: item[1].material_code)


def _block(request_row, other, state) -> str | None:
    """Por que o equivalente não pode substituir o material da solicitação; ou None."""
    if other.status != "ATIVO":
        return "INACTIVE_MATERIAL"
    if other.unit != request_row.unit:
        return "UNIT_MISMATCH"
    if state["blocked_reason"]:
        return state["blocked_reason"]
    return None


def alternatives(db, caller, request_id):
    """Alternativas autorizadas para o próprio solicitante, só quando falta saldo do material pedido."""
    row = _find(db, caller, request_id)
    if row.requester_user_id != caller.user_id:
        raise ApiProblem(404, "NOT_FOUND", "Solicitação não encontrada.")
    result = {"request_id": str(row.id), "request_version": row.version, "shortage": False, "items": []}
    if row.status != "EM_ATENDIMENTO" or row.material_id is None or row.substituted_from_material_id is not None:
        return result
    material = db.get(MaterialMaster, row.material_id)
    pending = fulfillment(db, row)["pending"]
    state = compute_availability(db, row.tenant_id, material, row.center_code)
    result["pending_quantity"] = quantity_text(pending)
    result["available_quantity"] = quantity_text(state["available"])
    if pending <= 0 or state["blocked_reason"] or state["available"] >= pending:
        return result
    result["shortage"] = True
    for equivalence, other in approved_equivalents(db, row.tenant_id, row.material_id):
        other_state = compute_availability(db, row.tenant_id, other, row.center_code)
        reason = _block(row, other, other_state)
        result["items"].append(
            {
                "equivalence_id": str(equivalence.id),
                "material_id": str(other.id),
                "material_code": other.material_code,
                "description": other.pdm_description
                or other.original_description_long
                or other.original_description_short,
                "unit": other.unit,
                "status": other.status,
                "available_quantity": quantity_text(other_state["available"]),
                "basis": equivalence.basis,
                "selectable": reason is None,
                "blocked_reason": reason,
            }
        )
    return result


def substitute(db, caller, request_id, payload, key, correlation_id):
    """Troca o material da solicitação por um equivalente autorizado, com confirmação explícita."""
    role = require_permission(caller, "requests:create")
    if payload.confirm_substitution is not True:
        raise ApiProblem(422, "CONFIRMATION_REQUIRED", "Confirme a troca pelo equivalente.")
    digest = canonical_hash({"id": str(request_id), **payload.model_dump(mode="json")})
    operation = "material-request.substitute"
    previous = _previous(db, caller, operation, key, digest)
    if previous:
        return previous.response
    # Mesma ordem de bloqueio da reserva e do encaminhamento, e só com a falta de saldo confirmada.
    row, material, _, _ = locked_shortage(db, caller, request_id, payload.expected_version)
    if row.substituted_from_material_id is not None:
        raise ApiProblem(409, "ALREADY_SUBSTITUTED", "A solicitação já foi trocada por um equivalente.")
    values = fulfillment(db, row)
    if values["reserved"] or values["delivered"] or values["forwarded"]:
        # Parcelas já atendidas pertencem ao material original: trocar misturaria saldos.
        raise ApiProblem(409, "REQUEST_PARTIALLY_SERVED", "A solicitação já tem parcelas atendidas.")
    match = next(
        (item for item in approved_equivalents(db, row.tenant_id, material.id) if item[1].id == payload.material_id),
        None,
    )
    if match is None:
        raise ApiProblem(422, "EQUIVALENCE_NOT_APPROVED", "Só um equivalente autorizado pode substituir o material.")
    equivalence, other = match
    reason = _block(row, other, compute_availability(db, row.tenant_id, other, row.center_code))
    if reason:
        raise ApiProblem(
            409 if reason not in {"INACTIVE_MATERIAL", "UNIT_MISMATCH"} else 422, reason, "Troca indisponível."
        )
    before = summary(row, caller)
    row.substituted_from_material_id = material.id
    row.substitution_equivalence_id = equivalence.id
    row.material_id = other.id
    row.version += 1
    db.flush()
    substitution = {
        "from_material_id": str(material.id),
        "from_material_code": material.material_code,
        "to_material_id": str(other.id),
        "to_material_code": other.material_code,
        "equivalence_id": str(equivalence.id),
        "basis": equivalence.basis,
    }
    text = (
        f"Troca confirmada pelo solicitante: {material.material_code} por {other.material_code}"
        " (equivalente autorizado)."
    )
    _audit(
        db,
        caller,
        role,
        row,
        before,
        text,
        correlation_id,
        action="MATERIAL_REQUEST_SUBSTITUTED",
        extra={"substitution": substitution},
    )
    response = detail(db, row, caller)
    remember_idempotency(db, caller, operation, key, digest, row, response)
    db.commit()
    return response
