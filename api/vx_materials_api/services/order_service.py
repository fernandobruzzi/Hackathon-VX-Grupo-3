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
import re
import uuid
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime

from sqlalchemy import BigInteger, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from domain.contracts import AnalyzedMaterial, MaterialRecord
from domain.identity_decision import decide_identity
from domain.ncm_rules import check_ncm_consistency
from domain.pdm_validator import validate_pdm
from pipelines.import_orders import STATUS_READY, OrderAnalysis, OrderRow, analyze_order
from pipelines.search_index import analyze_search_candidate, index_version
from repositories.batch_repository import SearchSource
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_api.db.models import (
    AuditLog,
    MaterialMaster,
    OperationRequest,
    RegistrationOrder,
    UserSso,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.rbac import has_permission, require_permission, require_resource_scope
from vx_materials_api.services.registration_request_service import resolve_requests

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
            "Índice de busca pendente para os materiais atuais: aguarde a atualização e tente novamente.",
            index_version=version,
        )


def _rules(catalog):
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    return classifier, extractor, index_version(catalog, classifier, extractor)


class IdentityReviewRequired(ApiProblem):
    def __init__(self, candidates: dict[str, list[str]]) -> None:
        super().__init__(
            409,
            "IDENTITY_REVIEW_REQUIRED",
            "A identidade exige revisão técnica das evidências antes de confirmar ou publicar.",
            candidate_material_ids=list(candidates),
            reasons=candidates,
        )


def existing_materials(db, tenant_id, catalog, analysis: OrderAnalysis, version: str) -> list[str]:
    """Chaves recuperam candidatos; a decisão compartilhada confirma identidade no mesmo snapshot da cobertura."""
    db.flush()
    state = db.execute(
        text(
            "SELECT count(*) AS total, "
            "count(i.material_id) FILTER (WHERE i.source_version = m.version) AS current, "
            "jsonb_agg(jsonb_build_object("
            "'id', m.id, 'code', m.material_code, 'status', m.status, "
            "'original_description', m.original_description_long, 'pdm_description', m.pdm_description, "
            "'approved_class_id', m.pdm_class_id, 'approved_attributes', m.attributes, "
            "'manufacturer', m.manufacturer, 'reference', m.manufacturer_reference, "
            "'material_version', m.version, 'indexed_class_id', i.proposed_class_id, "
            "'indexed_attributes', i.extracted_attributes, 'indexed_key', i.candidate_identity_key) "
            "ORDER BY m.material_code) FILTER (WHERE m.status = 'ATIVO' AND "
            "(m.identity_key = :identity OR (i.source_version = m.version AND "
            "i.candidate_identity_key = :identity))) AS candidates "
            "FROM materials_master m LEFT JOIN material_search_index i ON i.material_id = m.id "
            "AND i.tenant_id = m.tenant_id AND i.normalization_version = :version "
            "WHERE m.tenant_id = :tenant"
        ),
        {"tenant": tenant_id, "identity": analysis.identity_key, "version": version},
    ).one()
    requested = AnalyzedMaterial(
        MaterialRecord("", "ATIVO", analysis.source_text),
        analysis.pdm_class_id,
        analysis.item_name,
        analysis.attributes,
        analysis.identity_key,
    )
    classifier, extractor, _ = _rules(catalog)
    verified = []
    review = {}
    for row in state.candidates or []:
        approved = row["approved_class_id"] is not None or row["approved_attributes"]
        source = SearchSource(
            MaterialRecord(
                row["code"],
                row["status"],
                (row["pdm_description"] or row["original_description"] or "")
                if approved
                else row["original_description"] or "",
                manufacturer=row["manufacturer"] or "",
                reference=row["reference"] or "",
                version=row["material_version"],
            ),
            row["approved_class_id"],
            row["approved_attributes"] or {},
            row["original_description"],
        )
        candidate = analyze_search_candidate(
            source,
            catalog,
            classifier,
            extractor,
            row["indexed_class_id"],
            row["indexed_attributes"],
            row["indexed_key"],
        )
        decision = decide_identity(catalog, requested, candidate)
        if decision.status == "SAME_MATERIAL":
            verified.append(row["id"])
        elif decision.status == "REVIEW_REQUIRED":
            review[row["id"]] = list(decision.reasons)
    if verified:
        return verified
    if not state.total or state.current != state.total:
        raise SearchIndexMissing(version)
    if review:
        raise IdentityReviewRequired(review)
    return []


def _evaluate(db, tenant_id, catalog, analysis: OrderAnalysis, version: str) -> tuple[str, list[str], tuple[str, ...]]:
    if analysis.status != STATUS_READY:
        return analysis.status, [], analysis.missing_attributes
    try:
        existing = existing_materials(db, tenant_id, catalog, analysis, version)
    except IdentityReviewRequired as error:
        reasons = sorted({reason for values in error.details["reasons"].values() for reason in values})
        return (
            STATUS_READY,
            error.details["candidate_material_ids"],
            tuple("REVISAO DE IDENTIDADE: " + r for r in reasons),
        )
    return ("EXISTING" if existing else STATUS_READY), existing, analysis.missing_attributes


def import_orders(db, tenant_id, catalog, rows: list[OrderRow]) -> dict:
    """Grava os pedidos do kit com origin=IMPORT e sem solicitante. Repetir não duplica nada."""
    classifier, extractor, version = _rules(catalog)
    counts: Counter[str] = Counter()
    values = []
    for row in rows:
        analysis = analyze_order(row, catalog, classifier, extractor)
        status, candidates, missing = _evaluate(db, tenant_id, catalog, analysis, version)
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
                "missing_attributes": list(missing),
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
    if order.tenant_id != identity.tenant_id or (order.center_code and order.center_code not in identity.center_codes):
        return False
    if order.requester_user_id == identity.user_id:
        return True
    in_scope = order.center_code is None or order.center_code in identity.center_codes
    if has_permission(identity, GOVERNANCE):
        return in_scope
    return has_permission(identity, FISCAL) and in_scope and order.status in {"PENDING_FISCAL", "REGISTERED"}


def _can_complement(identity, order):
    if identity is None or order.status not in {"DRAFT", "INCOMPLETE", "OUT_OF_SCOPE"}:
        return False
    if order.tenant_id != identity.tenant_id or (order.center_code and order.center_code not in identity.center_codes):
        return False
    if order.requester_user_id == identity.user_id:
        return has_permission(identity, "orders:update_own")
    return order.origin == "IMPORT" and order.requester_user_id is None and has_permission(identity, GOVERNANCE)


def to_contract(db, order: RegistrationOrder, identity=None) -> dict:
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
        "supplements": list(order.supplements or []),
        "can_complement": _can_complement(identity, order),
    }


def list_orders(db, identity, *, status=None, mine=False, limit=20, cursor=None) -> dict:
    require_permission(identity, "orders:read_own")
    if cursor is not None and not re.fullmatch(r"[0-9]{1,9}", cursor):
        raise ApiProblem(422, "INVALID_CURSOR", "Cursor de pedidos inválido.")
    offset = int(cursor) if cursor is not None else 0
    own = RegistrationOrder.requester_user_id == identity.user_id
    query = select(RegistrationOrder).where(
        RegistrationOrder.tenant_id == identity.tenant_id,
        or_(RegistrationOrder.center_code.is_(None), RegistrationOrder.center_code.in_(identity.center_codes)),
    )
    if mine or not (has_permission(identity, GOVERNANCE) or has_permission(identity, FISCAL)):
        query = query.where(own)
    elif not has_permission(identity, GOVERNANCE):
        query = query.where(or_(own, RegistrationOrder.status.in_(["PENDING_FISCAL", "REGISTERED"])))
    if status:
        query = query.where(RegistrationOrder.status == status)
    rows = db.scalars(
        query.order_by(RegistrationOrder.updated_at.desc(), RegistrationOrder.id).offset(offset).limit(limit + 1)
    ).all()
    return {
        "items": [to_contract(db, order, identity) for order in rows[:limit]],
        "next_cursor": str(offset + limit) if len(rows) > limit else None,
    }


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


def _locked_order(db, identity, order_id, *, replay=False) -> RegistrationOrder:
    order = db.scalar(
        select(RegistrationOrder)
        .where(RegistrationOrder.id == order_id, RegistrationOrder.tenant_id == identity.tenant_id)
        .with_for_update()
    )
    if order is None or (not replay and not _visible(identity, order)):
        raise ApiProblem(404, "NOT_FOUND", "Pedido não encontrado.")
    if replay:
        require_resource_scope(identity, order.tenant_id, [order.center_code] if order.center_code else ())
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


def _audit(db, identity, role, order, action, reason, before, request_id, *, after=None):
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
            after_json=after
            if after is not None
            else {
                "status": order.status,
                "version": order.version,
                "material_id": str(order.material_id) if order.material_id else None,
                "candidate_material_ids": list(order.candidate_material_ids or []),
                "review_data": dict(order.review_data or {}),
                "pdm_class_id": order.pdm_class_id,
                "attributes": dict(order.attributes or {}),
                "missing_attributes": list(order.missing_attributes or []),
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
    order = _locked_order(db, identity, order_id, replay=previous is not None)
    if order.requester_user_id != identity.user_id:
        raise ApiProblem(403, "FORBIDDEN", "Só quem abriu o pedido pode encaminhá-lo.")
    if previous is not None:
        return previous.response["body"]
    _check_version(order, expected_version)
    if order.status not in _SUBMITTABLE:
        raise ApiProblem(409, "INVALID_TRANSITION", "O pedido já foi avaliado.", order_status=order.status)
    before = _state(order)
    classifier, extractor, version = _rules(catalog)
    analysis = _analysis(order, catalog, classifier, extractor)
    order.status, order.candidate_material_ids, missing = _evaluate(db, identity.tenant_id, catalog, analysis, version)
    order.pdm_class_id, order.attributes = analysis.pdm_class_id, analysis.attributes
    order.missing_attributes = list(missing)
    order.version += 1
    db.flush()
    resolve_requests(db, identity, role, order, None, request_id)
    _audit(db, identity, role, order, "ORDER_SUBMITTED", None, before, request_id)
    db.flush()
    db.refresh(order)
    body = to_contract(db, order, identity)
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
    supplements = order.supplements or []
    source_text = "\n".join(
        part for part in (order.original_text, order.attachment_text, *(item["text"] for item in supplements)) if part
    )
    # A ficha confirmada no chat é estruturada: não reextraímos mensagens antigas que foram corrigidas.
    if order.origin == "CHAT" and order.item_name is not None:
        attributes = dict(order.attributes)
        if order.supplements:
            extra = extractor.extract(
                catalog.classes[order.pdm_class_id], "; ".join(item["text"] for item in order.supplements)
            )
            attributes.update({name: value.value for name, value in extra.attributes.items() if name not in attributes})
        validation = validate_pdm(catalog, order.pdm_class_id, attributes, item_name=order.item_name)
        ready = (
            validation.can_submit and validation.identity_key is not None and not validation.not_applicable_attributes
        )
        return OrderAnalysis(
            STATUS_READY if ready else "INCOMPLETE",
            order.pdm_class_id,
            order.item_name,
            attributes,
            tuple(attribute.name for attribute in validation.missing_attributes),
            validation.identity_key,
            validation.formatted_description,
            source_text=source_text,
        )
    # Separadores mantêm os rótulos dos complementos independentes do texto original.
    original = order.original_text + ";" if supplements else order.original_text
    attachment = (
        "; ".join(part for part in [order.attachment_text, *(item["text"] for item in supplements)] if part) or None
    )
    row = OrderRow(order.source_order_id or str(order.id), original, attachment, None, None)

    return replace(analyze_order(row, catalog, classifier, extractor), source_text=source_text)


def _publish(db, order, catalog, analysis: OrderAnalysis) -> MaterialMaster:
    pdm_class = catalog.classes[order.pdm_class_id]
    attributes = dict(analysis.attributes)
    material = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=order.tenant_id,
        source_system=SOURCE_SYSTEM,
        material_code=_next_code(db, order.tenant_id),
        status="ATIVO",
        # Evidência derivada da concatenação ordenada: original, anexo e complementos.
        # Os registros separados permanecem no pedido e na auditoria; isto não é texto corrigido.
        original_description_long=analysis.source_text,
        pdm_description=analysis.formatted_description,
        pdm_class_id=order.pdm_class_id,
        pdm_version=catalog.version,
        attributes=attributes,
        manufacturer=attributes.get("FABRICANTE"),
        manufacturer_reference=attributes.get("REFERENCIA FABRICANTE"),
        unit=pdm_class.default_unit,
        ncm=order.review_data["fiscal"]["ncm_code"],
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
    # A aprovação de materiais usa seed 0; sempre o adquirimos antes do lock dos pedidos (seed 1).
    # Ambos ficam retidos até o commit, inclusive entre a busca final e a publicação.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:t, 0))"), {"t": str(identity.tenant_id)})
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:t, 1))"), {"t": str(identity.tenant_id)})
    previous, payload_hash = _idempotent(
        db, identity, operation, key, {"order_id": str(order_id), **decision.model_dump(mode="json", exclude_none=True)}
    )
    order = _locked_order(db, identity, order_id, replay=previous is not None)
    if previous is not None:
        # A auditoria imutável identifica a etapa original, mesmo após publicação/rejeição.
        original = db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == identity.tenant_id,
                AuditLog.actor_user_id == identity.user_id,
                AuditLog.entity_type == "registration_order",
                AuditLog.entity_id == str(order.id),
                AuditLog.after_json["version"].as_integer() == previous.response["body"]["version"],
            )
        )
        permission = _REVIEWABLE.get((original.before_json or {}).get("status")) if original else None
        if permission is None:
            raise ApiProblem(403, "FORBIDDEN", "Não foi possível autorizar a decisão original.")
        require_permission(identity, permission)
        return previous.response["body"]
    permission = _REVIEWABLE.get(order.status)
    if permission is None:
        raise ApiProblem(409, "INVALID_TRANSITION", "Este pedido não aguarda decisão.", order_status=order.status)
    role = require_permission(identity, permission)
    _check_version(order, decision.expected_version)
    if permission != FISCAL and any((decision.ncm_code, decision.ncm_source, decision.ncm_evaluation_hash)):
        raise ApiProblem(403, "FORBIDDEN", "Só o Fiscal pode definir NCM.")
    before = {**_state(order), "review_data": dict(order.review_data or {})}
    action = "ORDER_REJECTED"
    if decision.decision == "REJECT":
        if any((decision.ncm_code, decision.ncm_source, decision.ncm_evaluation_hash)):
            raise ApiProblem(422, "INVALID_DECISION", "A rejeição não define NCM.")
        order.status = "REJECTED"
    else:
        # Avalia de novo com as regras atuais: aprovar exige o mesmo pedido completo, na mesma classe.
        classifier, extractor, version = _rules(catalog)
        analysis = _analysis(order, catalog, classifier, extractor)
        if analysis.status != STATUS_READY or analysis.pdm_class_id != order.pdm_class_id:
            raise ApiProblem(422, "ORDER_INCOMPLETE", "O pedido não cumpre mais o PDM. Reavalie antes de aprovar.")
        existing = existing_materials(db, identity.tenant_id, catalog, analysis, version)
        if existing:
            order.status, order.candidate_material_ids, action = "EXISTING", existing, "ORDER_FOUND_EXISTING"
        elif order.status == "READY_FOR_REVIEW":
            order.review_data = {
                "technical": {
                    "signature": _review_signature(catalog, analysis, version),
                    "approved_version": order.version,
                    "pdm_class_id": analysis.pdm_class_id,
                    "item_name": analysis.item_name,
                    "attributes": dict(analysis.attributes),
                    "pdm_source_sha256": catalog.source_sha256,
                    "index_version": version,
                    "actor_user_id": str(identity.user_id),
                }
            }
            order.status, action = "PENDING_FISCAL", "ORDER_APPROVED_TECHNICAL"
        else:
            signature = _review_signature(catalog, analysis, version)
            if (order.review_data or {}).get("technical", {}).get("signature") != signature:
                raise ApiProblem(
                    422,
                    "TECHNICAL_REVIEW_CHANGED",
                    "A ficha ou as regras mudaram após a revisão técnica; é necessária nova revisão.",
                )
            code = decision.ncm_code or ncm_for(
                catalog.classes[order.pdm_class_id], analysis.attributes, analysis.item_name
            )
            if code is None:
                raise ApiProblem(
                    422, "NCM_UNDETERMINED", "Informe a escolha fiscal de NCM e sua fonte antes de publicar."
                )
            assessment = check_ncm_consistency(
                catalog, order.pdm_class_id, analysis.attributes, code, item_name=analysis.item_name
            )
            displayed = check_ncm_consistency(
                catalog, order.pdm_class_id, analysis.attributes, None, item_name=analysis.item_name
            )
            if decision.ncm_evaluation_hash and decision.ncm_evaluation_hash != displayed.evaluation_hash:
                raise ApiProblem(
                    409, "NCM_ASSESSMENT_CHANGED", "A avaliação fiscal foi alterada; consulte a ficha novamente."
                )
            if assessment.technical_consistency != "CONSISTENT":
                raise ApiProblem(422, "NCM_REFERENCE_MISMATCH", "NCM incompatível com as condições atuais do PDM.")
            if decision.ncm_code and (not decision.ncm_source or not decision.ncm_source.strip()):
                raise ApiProblem(422, "NCM_SOURCE_REQUIRED", "Informe a fonte que fundamenta a escolha fiscal.")
            if not decision.reason.strip():
                raise ApiProblem(422, "REASON_REQUIRED", "Informe a justificativa fiscal.")
            order.review_data = {
                **order.review_data,
                "fiscal": {
                    "ncm_code": assessment.normalized_ncm,
                    "source": decision.ncm_source or assessment.reference_source,
                    "reason": decision.reason,
                    "actor_user_id": str(identity.user_id),
                    "approved_version": order.version,
                    "assessment": asdict(assessment),
                },
            }
            try:
                with db.begin_nested():
                    material = _publish(db, order, catalog, analysis)
            except IntegrityError:
                # Outro principal com a mesma identidade entrou ao mesmo tempo: não duplica.
                existing = existing_materials(db, identity.tenant_id, catalog, analysis, version)
                if not existing:
                    raise
                order.status, order.candidate_material_ids, action = "EXISTING", existing, "ORDER_FOUND_EXISTING"
            else:
                order.material_id, order.status, action = material.id, "REGISTERED", "ORDER_REGISTERED"
    order.version += 1
    db.flush()
    resolve_requests(db, identity, role, order, decision.reason, request_id)
    _audit(db, identity, role, order, action, decision.reason, before, request_id)
    db.flush()
    db.refresh(order)
    body = to_contract(db, order, identity)
    _remember(db, identity, operation, key, payload_hash, order.id, body)
    db.commit()
    return body


def complement_order(db, identity, catalog, order_id, payload, key, request_id=None):
    """Dono ou Governança nos importados acrescenta informação sem alterar os originais."""
    operation = "registration_order.complement"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:t, 1))"), {"t": str(identity.tenant_id)})
    order = _locked_order(db, identity, order_id)
    require_resource_scope(identity, order.tenant_id, [order.center_code] if order.center_code else ())
    if order.requester_user_id == identity.user_id:
        role = require_permission(identity, "orders:update_own")
    elif order.origin == "IMPORT" and order.requester_user_id is None:
        role = require_permission(identity, GOVERNANCE)
    else:
        raise ApiProblem(403, "FORBIDDEN", "Só o dono ou a Governança nos importados pode complementar.")
    previous, payload_hash = _idempotent(
        db, identity, operation, key, {"order_id": str(order_id), **payload.model_dump(mode="json")}
    )
    if previous is not None:
        return previous.response["body"]
    _check_version(order, payload.expected_version)
    if order.status not in {"DRAFT", "INCOMPLETE", "OUT_OF_SCOPE"}:
        raise ApiProblem(409, "INVALID_TRANSITION", "Este pedido não aceita complementos.", order_status=order.status)
    if not all(value.strip() for value in (payload.text, payload.source, payload.reason)):
        raise ApiProblem(422, "INVALID_COMPLEMENT", "Informe complemento, origem e motivo.")

    def snapshot():
        return {
            **_state(order),
            "pdm_class_id": order.pdm_class_id,
            "attributes": dict(order.attributes or {}),
            "missing_attributes": list(order.missing_attributes or []),
            "supplements": list(order.supplements or []),
            "candidate_material_ids": list(order.candidate_material_ids or []),
        }

    before = snapshot()
    order.supplements = [
        *(order.supplements or []),
        {
            "text": payload.text.strip(),
            "source": payload.source.strip(),
            "reason": payload.reason.strip(),
            "actor_user_id": str(identity.user_id),
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    ]
    classifier, extractor, version = _rules(catalog)
    analysis = _analysis(order, catalog, classifier, extractor)
    order.status, order.candidate_material_ids, missing = _evaluate(db, identity.tenant_id, catalog, analysis, version)
    order.pdm_class_id, order.attributes = analysis.pdm_class_id, analysis.attributes
    order.missing_attributes = list(missing)
    order.version += 1
    db.flush()
    resolve_requests(db, identity, role, order, payload.reason, request_id)
    _audit(db, identity, role, order, "ORDER_COMPLEMENTED", payload.reason, before, request_id, after=snapshot())
    db.flush()
    db.refresh(order)
    body = to_contract(db, order, identity)
    _remember(db, identity, operation, key, payload_hash, order.id, body)
    db.commit()
    return body


def _review_signature(catalog, analysis, version):
    data = {
        "class": analysis.pdm_class_id,
        "item": analysis.item_name,
        "attributes": analysis.attributes,
        "source_text": analysis.source_text,
        "pdm_sha256": catalog.source_sha256,
        "rules": version,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def get_order_review(db, identity, catalog, order_id):
    require_permission(identity, "orders:read_own")
    order = _locked_order(db, identity, order_id)
    require_resource_scope(identity, order.tenant_id, [order.center_code] if order.center_code else ())
    classifier, extractor, version = _rules(catalog)
    analysis = _analysis(order, catalog, classifier, extractor)
    cls = catalog.classes.get(analysis.pdm_class_id)
    ncm = check_ncm_consistency(
        catalog, analysis.pdm_class_id or "", analysis.attributes, None, item_name=analysis.item_name
    )
    _, candidates, missing = _evaluate(db, identity.tenant_id, catalog, analysis, version)
    current_order = {**to_contract(db, order, identity), "missing_attributes": list(missing)}
    fiscal_decision = (order.review_data or {}).get("fiscal")
    if fiscal_decision is not None:
        # Projeta metadados ausentes sem reescrever a avaliação histórica nem seu hash.
        fiscal_decision = dict(fiscal_decision)
        assessment = dict(fiscal_decision["assessment"])
        for field in ("ncm_version", "ncm_source_sha256", "ncm_snapshot_date", "ncm_source_kind"):
            assessment.setdefault(field, None)
        fiscal_decision["assessment"] = assessment
    return {
        "order": current_order,
        "attachment_text": order.attachment_text,
        "item_name": analysis.item_name,
        "attributes": analysis.attributes,
        "formatted_description": analysis.formatted_description,
        "candidate_material_ids": candidates,
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "index_version": version,
        "ncm_assessment": asdict(ncm),
        "ncm_proposed": ncm_for(cls, analysis.attributes, analysis.item_name) if cls else None,
        "ncm_references": [{"codes": list(ref.codes), "condition": ref.rule} for ref in cls.ncm_references]
        if cls
        else [],
        "review_data": dict(order.review_data or {}),
        "fiscal_decision": fiscal_decision,
        "technical_review_current": (order.review_data or {}).get("technical", {}).get("signature")
        == _review_signature(catalog, analysis, version),
    }


def reopen_technical_review(db, identity, catalog, order_id, payload, key, request_id=None):
    """Governança reavalia o pedido pendente fiscal sem fabricar aprovação técnica retroativa."""
    role = require_permission(identity, GOVERNANCE)
    operation = "registration_order.reopen_technical_review"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:t, 1))"), {"t": str(identity.tenant_id)})
    order = _locked_order(db, identity, order_id)
    require_resource_scope(identity, order.tenant_id, [order.center_code] if order.center_code else ())
    previous, payload_hash = _idempotent(
        db, identity, operation, key, {"order_id": str(order_id), **payload.model_dump(mode="json")}
    )
    if previous is not None:
        return previous.response["body"]
    _check_version(order, payload.expected_version)
    if order.status != "PENDING_FISCAL":
        raise ApiProblem(409, "INVALID_TRANSITION", "Só pedidos pendentes fiscais podem voltar à revisão técnica.")
    if not payload.reason.strip():
        raise ApiProblem(422, "REASON_REQUIRED", "Informe o motivo da reavaliação técnica.")
    before = {
        **_state(order),
        "review_data": dict(order.review_data or {}),
        "pdm_class_id": order.pdm_class_id,
        "attributes": dict(order.attributes or {}),
        "missing_attributes": list(order.missing_attributes or []),
    }
    classifier, extractor, version = _rules(catalog)
    analysis = _analysis(order, catalog, classifier, extractor)
    order.status, order.candidate_material_ids, missing = _evaluate(db, identity.tenant_id, catalog, analysis, version)
    order.pdm_class_id, order.attributes = analysis.pdm_class_id, analysis.attributes
    order.missing_attributes = list(missing)
    order.review_data = {}
    order.version += 1
    db.flush()
    _audit(db, identity, role, order, "ORDER_TECHNICAL_REOPENED", payload.reason, before, request_id)
    db.flush()
    db.refresh(order)
    body = to_contract(db, order, identity)
    _remember(db, identity, operation, key, payload_hash, order.id, body)
    db.commit()
    return body
