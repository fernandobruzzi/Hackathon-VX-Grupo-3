"""Pedidos de cadastro (#24): importação do kit, submissão, decisão e publicação do novo material.

Estados da Arquitetura:

- Avaliação: DRAFT → INCOMPLETE | READY_FOR_REVIEW | EXISTING | OUT_OF_SCOPE.
- Depois da submissão: READY_FOR_REVIEW → PENDING_FISCAL | REGISTERED | REJECTED.

A Governança aprova a parte técnica e o pedido vai para o Fiscal, porque um material novo precisa de
NCM aprovado. Só a aprovação fiscal publica. Antes de cada aprovação a duplicidade é verificada de
novo: se surgiu um material com a mesma identidade, o pedido vira EXISTING e nada é publicado.
"""

import hashlib
import json
import uuid
from collections import Counter

from sqlalchemy import BigInteger, cast, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from domain.pdm_validator import validate_pdm
from pipelines.import_orders import STATUS_READY, OrderAnalysis, OrderRow, analyze_order
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_api.db.models import (
    AuditLog,
    MaterialMaster,
    MaterialSearchIndex,
    OperationRequest,
    RegistrationOrder,
    UserSso,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import has_permission, require_permission

GOVERNANCE = "orders:decide"
FISCAL = "ncm:decide"
SOURCE_SYSTEM = "VX-CADASTRO"
_REVIEWABLE = {"READY_FOR_REVIEW": GOVERNANCE, "PENDING_FISCAL": FISCAL}
_SUBMITTABLE = {"DRAFT", "INCOMPLETE"}


class SearchIndexMissing(ApiProblem):
    def __init__(self, version: str):
        super().__init__(
            503,
            "SEARCH_INDEX_MISSING",
            "Índice de busca ausente para as regras atuais: rode o batch antes de verificar duplicidade.",
            index_version=version,
        )


def _rules(catalog):
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    return classifier, extractor, index_version(catalog, classifier, extractor)


def existing_materials(db, tenant_id, identity_key: str, version: str) -> list[str]:
    """Ativos com a mesma identidade, no índice da versão atual ou já publicados como principais."""
    indexed = db.scalar(
        select(func.count())
        .select_from(MaterialSearchIndex)
        .where(MaterialSearchIndex.tenant_id == tenant_id, MaterialSearchIndex.normalization_version == version)
    )
    if not indexed:
        # Sem índice não dá para afirmar que o item é novo; duplicar custa mais que esperar.
        raise SearchIndexMissing(version)
    from_index = select(MaterialSearchIndex.material_id).where(
        MaterialSearchIndex.tenant_id == tenant_id,
        MaterialSearchIndex.normalization_version == version,
        MaterialSearchIndex.candidate_identity_key == identity_key,
    )
    rows = db.scalars(
        select(MaterialMaster.id)
        .where(
            MaterialMaster.tenant_id == tenant_id,
            MaterialMaster.status == "ATIVO",
            (MaterialMaster.id.in_(from_index)) | (MaterialMaster.identity_key == identity_key),
        )
        .order_by(MaterialMaster.material_code)
    )
    return [str(material_id) for material_id in rows]


def _evaluate(db, tenant_id, analysis: OrderAnalysis, version: str) -> tuple[str, list[str]]:
    if analysis.status != STATUS_READY:
        return analysis.status, []
    existing = existing_materials(db, tenant_id, analysis.identity_key, version)
    return ("EXISTING", existing) if existing else (STATUS_READY, [])


def import_orders(db, tenant_id, catalog, rows: list[OrderRow]) -> dict:
    """Grava os pedidos do kit com origin=IMPORT e sem solicitante. Repetir não duplica nada."""
    classifier, extractor, version = _rules(catalog)
    counts: Counter[str] = Counter()
    values = []
    for row in rows:
        analysis = analyze_order(row, catalog, classifier, extractor)
        status, candidates = _evaluate(db, tenant_id, analysis, version)
        counts[status] += 1
        values.append(
            {
                "tenant_id": tenant_id,
                "source_order_id": row.source_order_id,
                "requester_user_id": None,
                "origin": "IMPORT",
                "original_text": row.original_text,
                "attachment_text": row.attachment_text,
                "center_code": row.center_code,
                "urgency": row.urgency,
                "pdm_class_id": analysis.pdm_class_id,
                "attributes": analysis.attributes,
                "missing_attributes": list(analysis.missing_attributes),
                "candidate_material_ids": candidates,
                "status": status,
            }
        )
    inserted = 0
    for start in range(0, len(values), 500):
        statement = (
            insert(RegistrationOrder)
            .on_conflict_do_nothing(index_elements=["tenant_id", "source_order_id"])
            .returning(RegistrationOrder.id)
        )
        inserted += len(db.execute(statement, values[start : start + 500]).all())
    db.commit()
    return {"orders": len(rows), "inserted": inserted, "by_status": dict(sorted(counts.items())), "index": version}


def _visible(identity, order: RegistrationOrder) -> bool:
    if order.tenant_id != identity.tenant_id:
        return False
    if order.requester_user_id == identity.user_id:
        return True
    in_scope = order.center_code is None or order.center_code in identity.center_codes
    if has_permission(identity, GOVERNANCE):
        return in_scope
    return has_permission(identity, FISCAL) and in_scope and order.status in {"PENDING_FISCAL", "REGISTERED"}


def to_contract(db, order: RegistrationOrder) -> dict:
    requester = db.get(UserSso, order.requester_user_id) if order.requester_user_id else None
    material = db.get(MaterialMaster, order.material_id) if order.material_id else None
    return {
        "id": str(order.id),
        "origin": order.origin,
        "requester": requester.display_name if requester else None,
        "original_text": order.original_text,
        "center_code": order.center_code or "",
        "pdm_class_id": order.pdm_class_id,
        "status": order.status,
        "missing_attributes": list(order.missing_attributes or []),
        "material_code": material.material_code if material else None,
        "updated_at": order.updated_at.isoformat().replace("+00:00", "Z"),
        "version": order.version,
    }


def list_orders(db, identity, *, status=None, limit=20, cursor=None) -> dict:
    require_permission(identity, "orders:read_own")
    query = select(RegistrationOrder).where(RegistrationOrder.tenant_id == identity.tenant_id)
    if status:
        query = query.where(RegistrationOrder.status == status)
    if not (has_permission(identity, GOVERNANCE) or has_permission(identity, FISCAL)):
        query = query.where(RegistrationOrder.requester_user_id == identity.user_id)
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    rows = db.scalars(
        query.order_by(RegistrationOrder.updated_at.desc(), RegistrationOrder.id).offset(offset).limit(limit * 4 + 1)
    ).all()
    visible = [order for order in rows if _visible(identity, order)]
    items = visible[:limit]
    more = len(visible) > limit or len(rows) > limit * 4
    return {"items": [to_contract(db, order) for order in items], "next_cursor": str(offset + limit) if more else None}


def _idempotent(db, identity, operation: str, key: uuid.UUID, payload: dict):
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(
        select(OperationRequest).where(
            OperationRequest.user_id == identity.user_id,
            OperationRequest.operation == operation,
            OperationRequest.idempotency_key == str(key),
        )
    )
    if previous is not None and previous.payload_hash != payload_hash:
        raise ApiProblem(409, "IDEMPOTENCY_CONFLICT", "A chave já foi usada com outra solicitação.")
    return previous, payload_hash


def _remember(db, identity, operation, key, payload_hash, order_id, body):
    db.add(
        OperationRequest(
            user_id=identity.user_id,
            operation=operation,
            idempotency_key=str(key),
            payload_hash=payload_hash,
            status="COMPLETED",
            resource_id=str(order_id),
            response={"status_code": 200, "body": body},
        )
    )


def _locked_order(db, identity, order_id) -> RegistrationOrder:
    order = db.scalar(
        select(RegistrationOrder)
        .where(RegistrationOrder.id == order_id, RegistrationOrder.tenant_id == identity.tenant_id)
        .with_for_update()
    )
    if order is None or not _visible(identity, order):
        raise ApiProblem(404, "NOT_FOUND", "Pedido não encontrado.")
    return order


def _check_version(order, expected_version):
    if order.version != expected_version:
        raise ApiProblem(
            409,
            "VERSION_CONFLICT",
            "O pedido foi alterado. Atualize antes de continuar.",
            expected_version=expected_version,
            current_version=order.version,
        )


def _audit(db, identity, role, order, action, reason, before, request_id):
    db.add(
        AuditLog(
            id=uuid.uuid4(),
            tenant_id=identity.tenant_id,
            actor_user_id=identity.user_id,
            actor_type="USER",
            roles_snapshot=list(identity.roles),
            effective_role=role,
            action=action,
            entity_type="registration_order",
            entity_id=str(order.id),
            before_json=before,
            after_json={
                "status": order.status,
                "version": order.version,
                "material_id": str(order.material_id) if order.material_id else None,
                "candidate_material_ids": list(order.candidate_material_ids or []),
            },
            reason=reason,
            request_id=request_id,
        )
    )


def _state(order) -> dict:
    return {"status": order.status, "version": order.version}


def submit_order(db, identity, catalog, order_id, expected_version, key, request_id=None) -> dict:
    """Dono encaminha o pedido: a API avalia de novo texto, PDM e duplicidade."""
    role = require_permission(identity, "orders:update_own")
    operation = "registration_order.submit"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:t, 1))"), {"t": str(identity.tenant_id)})
    previous, payload_hash = _idempotent(
        db, identity, operation, key, {"order_id": str(order_id), "expected_version": expected_version}
    )
    if previous is not None:
        return previous.response["body"]
    order = _locked_order(db, identity, order_id)
    if order.requester_user_id != identity.user_id:
        raise ApiProblem(403, "FORBIDDEN", "Só quem abriu o pedido pode encaminhá-lo.")
    _check_version(order, expected_version)
    if order.status not in _SUBMITTABLE:
        raise ApiProblem(409, "INVALID_TRANSITION", "O pedido já foi avaliado.", order_status=order.status)
    before = _state(order)
    classifier, extractor, version = _rules(catalog)
    analysis = _analysis(order, catalog, classifier, extractor)
    order.status, order.candidate_material_ids = _evaluate(db, identity.tenant_id, analysis, version)
    order.pdm_class_id, order.attributes = analysis.pdm_class_id, analysis.attributes
    order.missing_attributes = list(analysis.missing_attributes)
    order.version += 1
    db.flush()
    _audit(db, identity, role, order, "ORDER_SUBMITTED", None, before, request_id)
    db.flush()
    db.refresh(order)
    body = to_contract(db, order)
    _remember(db, identity, operation, key, payload_hash, order.id, body)
    db.commit()
    return body


def _next_code(db, tenant_id) -> str:
    current = db.scalar(
        select(func.max(cast(MaterialMaster.material_code, BigInteger))).where(
            MaterialMaster.tenant_id == tenant_id, MaterialMaster.material_code.op("~")("^[0-9]{1,18}$")
        )
    )
    return str((current or 0) + 1)


def ncm_for(pdm_class, attributes: dict, item_name: str | None) -> str | None:
    """NCM só quando o PDM não deixa escolha; senão o pedido fica parado no Fiscal.

    Vale um código único na classe, a exceção do próprio item ou o sobressalente da aplicação
    informada (`sobressalente de BRITADOR CONICO`). Qualquer outra situação fica sem NCM.
    """
    references = pdm_class.ncm_references
    if len(references) == 1 and len(references[0].codes) == 1:
        return references[0].codes[0]
    single = [reference for reference in references if len(reference.codes) == 1]
    if item_name:
        exceptions = [r for r in single if r.rule.startswith("exceção") and r.rule.endswith(f" {item_name}")]
        if exceptions:
            return exceptions[0].codes[0]
    application = attributes.get("APLICACAO")
    matches = {r.codes[0] for r in single if application and r.rule == f"sobressalente de {application}"}
    return matches.pop() if len(matches) == 1 else None


def _analysis(order, catalog, classifier, extractor) -> OrderAnalysis:
    # A ficha confirmada no chat é estruturada: não reextraímos mensagens antigas que foram corrigidas.
    if order.origin == "CHAT" and order.item_name is not None:
        validation = validate_pdm(catalog, order.pdm_class_id, order.attributes, item_name=order.item_name)
        ready = (
            validation.can_submit and validation.identity_key is not None and not validation.not_applicable_attributes
        )
        return OrderAnalysis(
            STATUS_READY if ready else "INCOMPLETE",
            order.pdm_class_id,
            order.item_name,
            dict(order.attributes),
            tuple(attribute.name for attribute in validation.missing_attributes),
            validation.identity_key,
            validation.formatted_description,
        )
    row = OrderRow(order.source_order_id or str(order.id), order.original_text, order.attachment_text, None, None)
    return analyze_order(row, catalog, classifier, extractor)


def _publish(db, order, catalog, analysis: OrderAnalysis) -> MaterialMaster:
    pdm_class = catalog.classes[order.pdm_class_id]
    attributes = dict(analysis.attributes)
    material = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=order.tenant_id,
        source_system=SOURCE_SYSTEM,
        material_code=_next_code(db, order.tenant_id),
        status="ATIVO",
        original_description_long=order.original_text,
        pdm_description=analysis.formatted_description,
        pdm_class_id=order.pdm_class_id,
        pdm_version=catalog.version,
        attributes=attributes,
        manufacturer=attributes.get("FABRICANTE"),
        manufacturer_reference=attributes.get("REFERENCIA FABRICANTE"),
        unit=pdm_class.default_unit,
        ncm=ncm_for(pdm_class, attributes, analysis.item_name),
        ncm_review_status="APPROVED",
        identity_key=analysis.identity_key,
        is_canonical=True,
    )
    db.add(material)
    db.flush()
    return material


def decide_order(db, identity, catalog, order_id, decision, key, request_id=None) -> dict:
    """Governança aprova a parte técnica; o Fiscal aprova o NCM e publica. Rejeição encerra o pedido."""
    operation = "registration_order.decide"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:t, 1))"), {"t": str(identity.tenant_id)})
    previous, payload_hash = _idempotent(
        db, identity, operation, key, {"order_id": str(order_id), **decision.model_dump(mode="json")}
    )
    if previous is not None:
        return previous.response["body"]
    order = _locked_order(db, identity, order_id)
    permission = _REVIEWABLE.get(order.status)
    if permission is None:
        raise ApiProblem(409, "INVALID_TRANSITION", "Este pedido não aguarda decisão.", order_status=order.status)
    role = require_permission(identity, permission)
    _check_version(order, decision.expected_version)
    before = _state(order)
    action = "ORDER_REJECTED"
    if decision.decision == "REJECT":
        order.status = "REJECTED"
    else:
        # Avalia de novo com as regras atuais: aprovar exige o mesmo pedido completo, na mesma classe.
        classifier, extractor, version = _rules(catalog)
        analysis = _analysis(order, catalog, classifier, extractor)
        if analysis.status != STATUS_READY or analysis.pdm_class_id != order.pdm_class_id:
            raise ApiProblem(422, "ORDER_INCOMPLETE", "O pedido não cumpre mais o PDM. Reavalie antes de aprovar.")
        existing = existing_materials(db, identity.tenant_id, analysis.identity_key, version)
        if existing:
            order.status, order.candidate_material_ids, action = "EXISTING", existing, "ORDER_FOUND_EXISTING"
        elif order.status == "READY_FOR_REVIEW":
            order.status, action = "PENDING_FISCAL", "ORDER_APPROVED_TECHNICAL"
        else:
            if ncm_for(catalog.classes[order.pdm_class_id], analysis.attributes, analysis.item_name) is None:
                raise ApiProblem(
                    422, "NCM_UNDETERMINED", "A classe tem mais de um NCM possível; ainda não dá para publicar."
                )
            try:
                with db.begin_nested():
                    material = _publish(db, order, catalog, analysis)
            except IntegrityError:
                # Outro principal com a mesma identidade entrou ao mesmo tempo: não duplica.
                existing = existing_materials(db, identity.tenant_id, analysis.identity_key, version)
                order.status, order.candidate_material_ids, action = "EXISTING", existing, "ORDER_FOUND_EXISTING"
            else:
                order.material_id, order.status, action = material.id, "REGISTERED", "ORDER_REGISTERED"
    order.version += 1
    db.flush()
    _audit(db, identity, role, order, action, decision.reason, before, request_id)
    db.flush()
    db.refresh(order)
    body = to_contract(db, order)
    _remember(db, identity, operation, key, payload_hash, order.id, body)
    db.commit()
    return body
