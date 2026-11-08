"""Aprovacao atomica: o chamador confirma a transacao somente apos obter o resultado."""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from domain.contracts import (
    AnalyzedMaterial,
    ClassificationInput,
    FieldStatus,
    MaterialRecord,
    PdmCatalog,
    ValidationStatus,
)
from domain.identity import item_name_review_reasons, reference_key, resolve_item_name
from domain.identity_decision import decide_identity
from domain.ncm_rules import requires_snapshot_fiscal_review
from domain.pdm_validator import validate_pdm
from domain.proposal_validation import is_approvable
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository
from vx_materials_api.db.models import (
    AuditLog,
    Dataset,
    EnrichmentSource,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialMaster,
    OperationRequest,
    SanitizationProposal,
)
from vx_materials_api.errors import ApiError, error_body
from vx_materials_api.schemas.proposals import (
    MemberInterpretation,
    ProposalChangeset,
    ProposalDecision,
    evidence_hash,
    proposal_hash,
)
from vx_materials_api.security.approval_identity import Principal, require_reviewer
from vx_materials_api.security.automatic_actor import AutomaticActor
from vx_materials_api.services.enrichment_validation import (
    check_source_environment,
    validate_enrichment_context,
    validate_internal_sources,
)
from vx_materials_api.services.ncm_validation import evaluate_proposed_ncm


def writes_only_ncm(proposal) -> bool:
    """Correção fiscal aprovada grava só o NCM; a revisão usa o mesmo predicado para não prometer mais."""
    return proposal.proposal_type == "NCM_CORRECTION"


def decode_proposal(proposal: SanitizationProposal):
    try:
        members = [MemberInterpretation.model_validate_json(json.dumps(m)) for m in proposal.members]
        changes = ProposalChangeset.model_validate_json(json.dumps(proposal.changeset))
    except (ValidationError, TypeError, ValueError):
        raise ApiError(422, "INVALID_PROPOSAL", "Contrato da proposta persistida e invalido.") from None
    if not members or len({m.material_id for m in members}) != len(members):
        raise ApiError(422, "INVALID_PROPOSAL", "Membros ausentes ou repetidos na proposta.")
    return members, changes


def exact_product(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(28, len(left.as_tuple().digits) + len(right.as_tuple().digits) + 1)
        return left * right


def _attribute_matches(name: str, left: str | None, right: str | None) -> bool:
    if name == "REFERENCIA FABRICANTE" and isinstance(left, str) and isinstance(right, str):
        return reference_key(left) == reference_key(right)
    return left == right


def _attributes_match(first: dict, second: dict) -> bool:
    return first.keys() == second.keys() and all(_attribute_matches(k, v, second[k]) for k, v in first.items())


def exact_sum(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(
            28, max(left.adjusted(), right.adjusted()) - min(left.as_tuple().exponent, right.as_tuple().exponent) + 2
        )
        return left + right


def material_state(material: MaterialMaster) -> dict:
    return {
        "id": str(material.id),
        "material_code": material.material_code,
        "version": material.version,
        "status": material.status,
        "active_code_target": str(material.active_code_target) if material.active_code_target else None,
        "pdm_description": material.pdm_description,
        "pdm_class_id": material.pdm_class_id,
        "pdm_version": material.pdm_version,
        "attributes": material.attributes,
        "unit": material.unit,
        "ncm": material.ncm,
        "ncm_review_status": material.ncm_review_status,
        "original_merchandise_group": material.original_merchandise_group,
        "merchandise_group": material.merchandise_group,
        "identity_key": material.identity_key,
        "manufacturer": material.manufacturer,
        "manufacturer_reference": material.manufacturer_reference,
        "is_canonical": material.is_canonical,
    }


def proposal_state(proposal: SanitizationProposal) -> dict:
    return {
        "proposal_id": str(proposal.id),
        "version": proposal.version,
        "status": proposal.status,
        "technical_review_status": proposal.technical_review_status,
        "fiscal_review_status": proposal.fiscal_review_status,
        "changeset_hash": proposal.changeset_hash,
        "primary_material_id": str(proposal.primary_material_id) if proposal.primary_material_id else None,
        "evidence_ids": proposal.evidence_ids,
        "application_mode": proposal.application_mode,
    }


def load_members(db: Session, proposal: SanitizationProposal, principal: Principal, *, lock=False):
    interpretations, changes = decode_proposal(proposal)
    if (
        db.scalar(select(Dataset.id).where(Dataset.id == changes.dataset_id, Dataset.tenant_id == principal.tenant_id))
        is None
    ):
        raise ApiError(404, "NOT_FOUND", "Proposta nao encontrada no seu escopo.")
    statement = (
        select(MaterialMaster)
        .where(
            MaterialMaster.tenant_id == principal.tenant_id,
            MaterialMaster.id.in_([m.material_id for m in interpretations]),
        )
        .order_by(MaterialMaster.id)
    )
    materials = list(db.scalars(statement.with_for_update() if lock else statement))
    if len(materials) != len(interpretations):
        raise ApiError(404, "NOT_FOUND", "Proposta nao encontrada no seu escopo.")
    snapshots = list(
        db.scalars(
            select(MaterialInventorySnapshot)
            .where(
                MaterialInventorySnapshot.tenant_id == principal.tenant_id,
                MaterialInventorySnapshot.dataset_id == changes.dataset_id,
                or_(
                    MaterialInventorySnapshot.material_id.in_([m.id for m in materials]),
                    MaterialInventorySnapshot.id.in_(
                        select(InventoryConsolidation.source_snapshot_id).where(
                            InventoryConsolidation.tenant_id == principal.tenant_id,
                            InventoryConsolidation.primary_material_id.in_([m.id for m in materials]),
                        )
                    ),
                ),
            )
            .order_by(MaterialInventorySnapshot.id)
        )
    )
    if any(row.center_code not in principal.center_codes for row in snapshots):
        raise ApiError(404, "NOT_FOUND", "Proposta nao encontrada no seu escopo.")
    return interpretations, changes, materials, snapshots


def inventory_rows(db: Session, snapshots, target_unit: str | None, changes: ProposalChangeset):
    conversions = {}
    for conversion in changes.conversions:
        key = (conversion.from_unit, conversion.to_unit)
        if key in conversions:
            raise ApiError(422, "INVALID_CONVERSION", "Conversao duplicada na proposta.")
        if conversion.from_unit == conversion.to_unit and Decimal(conversion.factor) != 1:
            raise ApiError(422, "INVALID_CONVERSION", "Mesma unidade nao pode alterar a quantidade.")
        conversions[key] = conversion
    links = (
        {
            link.source_snapshot_id: link
            for link in db.scalars(
                select(InventoryConsolidation).where(
                    InventoryConsolidation.source_snapshot_id.in_([s.id for s in snapshots])
                )
            )
        }
        if snapshots
        else {}
    )
    result = []
    for snapshot in snapshots:
        if not snapshot.quantity.is_finite() or (
            snapshot.total_value is not None and not snapshot.total_value.is_finite()
        ):
            raise ApiError(422, "INVALID_INVENTORY", "Saldo ou valor de estoque nao e finito.")
        link = links.get(snapshot.id)
        current_unit = link.unit if link else snapshot.unit
        factor = link.factor if link else Decimal(1)
        source = link.conversion_source if link else "mesma unidade"
        if target_unit is not None and current_unit != target_unit:
            # O importador conserva ausência como NULL; o contrato representa a origem ausente por "".
            # A correspondência ainda exige fator e fonte explícitos; o snapshot original não muda.
            conversion = conversions.get((current_unit or "", target_unit))
            if conversion is None:
                raise ApiError(
                    422, "UNIT_FACTOR_REQUIRED", "Unidade de embalagem sem fator conhecido impede consolidacao."
                )
            factor = exact_product(factor, Decimal(conversion.factor))
            source = conversion.source
        result.append(
            {
                "snapshot": snapshot,
                "owner": link.primary_material_id if link else snapshot.material_id,
                "factor": factor,
                "unit": target_unit or current_unit,
                "source": source,
                "quantity": exact_product(snapshot.quantity, factor),
                "total_value": snapshot.total_value,
            }
        )
    return result


def consolidated_inventory(rows, *, financial=False):
    grouped = defaultdict(lambda: {"quantity": Decimal(0), "value": Decimal(0), "known": True})
    for row in rows:
        snapshot = row["snapshot"]
        key = (str(snapshot.dataset_id), snapshot.center_code, row["unit"])
        group = grouped[key]
        group["quantity"] = exact_sum(group["quantity"], row["quantity"])
        if row["total_value"] is None:
            group["known"] = False
        else:
            group["value"] = exact_sum(group["value"], row["total_value"])
    result = []
    for (dataset, center, unit), value in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or "")
    ):
        item = {"dataset_id": dataset, "center_code": center, "unit": unit, "quantity": str(value["quantity"])}
        if financial:
            item["total_value"] = str(value["value"]) if value["known"] else None
        result.append(item)
    return result


def _audit(db, principal, proposal, request_id, action, reason, before, after, role, lot=None):
    automatic = isinstance(principal, AutomaticActor)
    if automatic:
        action = "PROPOSAL_AUTO_APPLY" if action == "PROPOSAL_APPROVE_TECHNICAL" else action
        after = {**after, "automatic_correction": principal.execution}
    if lot is not None:
        # Aprovação em lote: o evento de cada item aponta para a revisão do lote e sua amostra.
        after = {**after, "lot_review": lot}
    audit = AuditLog(
        id=uuid4(),
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_type="SYSTEM" if automatic else "USER",
        roles_snapshot=[] if automatic else list(principal.roles),
        effective_role=None if automatic else role,
        action=action,
        entity_type="sanitization_proposal",
        entity_id=str(proposal.id),
        before_json=before,
        after_json=after,
        reason=reason,
        request_id=request_id,
        job_id=proposal.job_id,
    )
    db.add(audit)
    return audit


def _validation(catalog, item, unit=None, *, allow_incomplete=False):
    validation = validate_pdm(catalog, item.pdm_class_id, item.attributes, item_name=item.item_name, unit=unit)
    if not is_approvable(validation, allow_incomplete=allow_incomplete):
        raise ApiError(422, "PDM_INVALID", "A proposta nao atende aos atributos e unidade do PDM.")
    return validation


def merchandise_group(material: MaterialMaster) -> str | None:
    """Grupo vigente: o revisado, se aprovado, senão o original da carga."""
    return material.merchandise_group or material.original_merchandise_group


def _group_changed_since_proposal(changes: ProposalChangeset, materials) -> bool:
    proposed = next((change for change in changes.changes if change.field == "merchandise_group"), None)
    return proposed is not None and any(merchandise_group(m) != proposed.before for m in materials)


def _check_group(catalog, proposal, changes, materials):
    group = changes.after.merchandise_group
    if group is None:
        return None
    if proposal.proposal_type != "PDM_CORRECTION" or len(materials) != 1:
        raise ApiError(422, "INVALID_PROPOSAL", "Grupo de mercadorias so muda por correcao de PDM de um material.")
    pdm_class = catalog.classes.get(changes.after.pdm_class_id)
    if pdm_class is None or pdm_class.group != group:
        raise ApiError(422, "GROUP_MISMATCH", "O grupo proposto difere do grupo da classe PDM confirmada.")
    if merchandise_group(materials[0]) != group and not changes.sources.get("merchandise_group", "").strip():
        raise ApiError(
            422, "SOURCE_REQUIRED", "Toda alteracao deve registrar sua regra ou fonte.", field="merchandise_group"
        )
    return group


def _ncm(code: str | None) -> str | None:
    """A base traz `84314390` ou `8431.4390`; o PDM, `8431.43.90`. Compara pela mesma grafia."""
    return get_normalization_repository().normalize_ncm(code).value or code


def _apply_unit_correction(principal, proposal, catalog, changes, materials):
    """Grafia da mesma unidade (PCA, UN, PÇ para PC): muda só a unidade de um material.

    Não depende de classe nem de PDM completo, porque não publica identidade, descrição nem NCM.
    Quantidades não mudam: é a mesma unidade escrita de outro jeito. Conversão entre unidades
    diferentes nunca passa por aqui.
    """
    if changes.conflicts:
        raise ApiError(422, "PROPOSAL_CONFLICT", "Resolva os conflitos antes de aprovar.")
    if changes.pdm_version != catalog.version or changes.pdm_source_sha256 != catalog.source_sha256:
        raise ApiError(409, "REFERENCE_CHANGED", "A referencia PDM mudou. Gere uma nova proposta.")
    if len(materials) != 1 or [change.field for change in changes.changes] != ["unit"]:
        raise ApiError(422, "INVALID_PROPOSAL", "Correcao de unidade altera so a unidade de um material.")
    if proposal.fiscal_review_status != "NOT_REQUIRED":
        raise ApiError(422, "INVALID_PROPOSAL", "Correcao de unidade nao altera NCM.")
    material, change = materials[0], changes.changes[0]
    if material.status != "ATIVO":
        raise ApiError(422, "INVALID_PRIMARY", "O principal deve ser um membro ativo da proposta.")
    unit = get_normalization_repository().normalize_unit(material.unit)
    if (
        unit.status is not FieldStatus.NORMALIZED
        or unit.value != changes.after.unit
        or (change.before, change.after) != (material.unit, unit.value)
    ):
        raise ApiError(
            422, "UNIT_NOT_ALIAS", "A correcao so troca a grafia da mesma unidade; conversao exige outra revisao."
        )
    if not change.source.strip():
        raise ApiError(422, "SOURCE_REQUIRED", "Toda alteracao deve registrar sua regra ou fonte.", field="unit")
    material.unit = unit.value
    material.version += 1
    proposal.technical_review_status = "APPROVED"
    proposal.technical_reviewer_id = principal.user_id
    proposal.status = "APPLIED"
    return {"primary_material_code": material.material_code, "blocked_material_codes": []}


def _same_inventory_link(db, row, primary_id) -> bool:
    """Não grava vínculo redundante numa correção exclusivamente textual."""
    snapshot = row["snapshot"]
    link = db.get(InventoryConsolidation, snapshot.id)
    owner = link.primary_material_id if link else snapshot.material_id
    unit = link.unit if link else snapshot.unit
    factor = link.factor if link else Decimal(1)
    return owner == primary_id and row["unit"] == unit and row["factor"] == factor


def _check_review_bindings(db, proposal):
    for area, status in [("TECHNICAL", proposal.technical_review_status), ("FISCAL", proposal.fiscal_review_status)]:
        if status != "APPROVED":
            continue
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == proposal.tenant_id,
                AuditLog.entity_id == str(proposal.id),
                AuditLog.entity_type == "sanitization_proposal",
                AuditLog.action == f"PROPOSAL_APPROVE_{area}",
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        )
        if audit is None or audit.after_json.get("changeset_hash") != proposal.changeset_hash:
            return False
    return True


def decide_proposal(
    db: Session,
    principal: Principal,
    proposal_id: UUID,
    decision: ProposalDecision,
    idempotency_key: UUID,
    request_id: str,
    catalog: PdmCatalog,
    *,
    lot: dict | None = None,
) -> tuple[int, dict]:
    require_reviewer(principal, decision.review_area)
    # Serializacao por tenant simplifica a concorrencia entre propostas sobre os mesmos materiais.
    # Idempotencia, locks de linhas e o evento sao confirmados juntos pelo chamador.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 0))"), {"tenant": str(principal.tenant_id)})
    operation = "sanitization.decide"
    body_hash = hashlib.sha256(
        json.dumps(
            {"proposal_id": str(proposal_id), **decision.model_dump(mode="json")},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    previous = db.scalar(
        select(OperationRequest).where(
            OperationRequest.user_id == principal.user_id,
            OperationRequest.operation == operation,
            OperationRequest.idempotency_key == str(idempotency_key),
        )
    )
    proposal = db.scalar(
        select(SanitizationProposal)
        .where(
            SanitizationProposal.id == proposal_id,
            SanitizationProposal.tenant_id == principal.tenant_id,
            SanitizationProposal.changeset["schema_version"].astext == "proposal-v1",
        )
        .with_for_update()
    )
    if proposal is None:
        raise ApiError(404, "NOT_FOUND", "Proposta nao encontrada.")
    interpretations, changes, materials, snapshots = load_members(db, proposal, principal, lock=True)
    if previous:
        if previous.payload_hash != body_hash:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "A chave ja foi usada com outra solicitacao.")
        return previous.response["status_code"], previous.response["body"]
    if proposal.version != decision.expected_version:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "A proposta foi alterada. Atualize a revisao.",
            expected_version=decision.expected_version,
            current_version=proposal.version,
        )
    if proposal.status != "PENDING":
        raise ApiError(409, "PROPOSAL_FINALIZED", "A proposta ja foi decidida ou esta desatualizada.")
    review_field = "technical_review_status" if decision.review_area == "TECHNICAL" else "fiscal_review_status"
    if getattr(proposal, review_field) != "PENDING":
        raise ApiError(409, "REVIEW_FINALIZED", "Esta revisao ja foi decidida ou nao e necessaria.")
    before = {
        **proposal_state(proposal),
        "members": proposal.members,
        "changeset": proposal.changeset,
        "snapshot_ids": [str(snapshot.id) for snapshot in snapshots],
        "materials": [material_state(m) for m in materials],
        "inventory": consolidated_inventory(inventory_rows(db, snapshots, None, changes), financial=True),
    }
    role = "ROLE_AUDITOR_FISCAL" if decision.review_area == "FISCAL" else "ROLE_GOVERNANCA_PDM"
    stale = (
        proposal_hash(proposal.members, proposal.changeset, proposal.evidence_ids) != proposal.changeset_hash
        or any(
            m.version != next(i.expected_version for i in interpretations if i.material_id == m.id) for m in materials
        )
        or not _check_review_bindings(db, proposal)
        or _group_changed_since_proposal(changes, materials)
    )
    if stale:
        proposal.status = "STALE"
        proposal.version += 1
        _audit(
            db,
            principal,
            proposal,
            request_id,
            "PROPOSAL_STALE",
            decision.reason,
            before,
            proposal_state(proposal),
            role,
            lot,
        )
        status, response = (
            409,
            error_body("STALE_PROPOSAL", "Materiais ou alteracoes mudaram. Gere uma nova proposta.", request_id),
        )
    else:
        status, response = _decide_current(
            db,
            principal,
            proposal,
            decision,
            catalog,
            interpretations,
            changes,
            materials,
            snapshots,
            request_id,
            before,
            role,
            lot,
        )
    db.add(
        OperationRequest(
            user_id=principal.user_id,
            operation=operation,
            idempotency_key=str(idempotency_key),
            payload_hash=body_hash,
            status="COMPLETED",
            resource_id=str(proposal_id),
            response={"status_code": status, "body": response},
        )
    )
    db.flush()
    return status, response


def _decide_current(
    db,
    principal,
    proposal,
    decision,
    catalog,
    interpretations,
    changes,
    materials,
    snapshots,
    request_id,
    before,
    role,
    lot=None,
):
    result = None
    after_inventory = []
    verified_sources = []
    ncm_evaluation = None
    if decision.decision == "REJECT":
        setattr(
            proposal,
            "technical_review_status" if decision.review_area == "TECHNICAL" else "fiscal_review_status",
            "REJECTED",
        )
        proposal.status = "REJECTED"
    elif proposal.proposal_type == "UNIT_CORRECTION":
        result = _apply_unit_correction(principal, proposal, catalog, changes, materials)
    else:
        if changes.conflicts:
            raise ApiError(422, "PROPOSAL_CONFLICT", "Resolva os conflitos antes de aprovar.")
        if changes.pdm_version != catalog.version or changes.pdm_source_sha256 != catalog.source_sha256:
            raise ApiError(409, "REFERENCE_CHANGED", "A referencia PDM mudou. Gere uma nova proposta.")
        partial_enrichment = proposal.proposal_type == "ENRICHMENT" and changes.enrichment_context is not None
        # Correção fiscal grava só o NCM: o código precisa estar resolvido pela classe e pelos
        # atributos que o decidem, mas lacunas do PDM e a unidade não são publicadas por ela.
        ncm_only = writes_only_ncm(proposal)
        if changes.origin == "LLM_AUDITOR" and not ncm_only:
            raise ApiError(422, "INVALID_PROPOSAL", "Sugestao do auditor LLM so corrige NCM.")
        validation = _validation(
            catalog,
            changes.after,
            changes.after.unit
            if proposal.technical_review_status != "NOT_REQUIRED" and not partial_enrichment and not ncm_only
            else None,
            allow_incomplete=partial_enrichment or ncm_only,
        )
        group = _check_group(catalog, proposal, changes, materials)
        # Enriquecimento parcial reavalia, mas preserva o NCM original sem certificá-lo.
        # O contexto abaixo impede qualquer alteração fiscal por esse caminho.
        ncm_evaluation = evaluate_proposed_ncm(catalog, changes, require_consistency=not partial_enrichment)
        fiscal_change = any(_ncm(m.ncm) != _ncm(changes.after.ncm) for m in materials)
        fiscal_basis_changed = any(
            (m.pdm_class_id is not None and m.pdm_class_id != changes.after.pdm_class_id)
            or (bool(m.attributes) and not _attributes_match(m.attributes, changes.after.attributes))
            for m in materials
        )
        if (fiscal_change or fiscal_basis_changed or requires_snapshot_fiscal_review(ncm_evaluation)) and (
            proposal.fiscal_review_status == "NOT_REQUIRED"
        ):
            raise ApiError(422, "FISCAL_REVIEW_REQUIRED", "A alteracao de NCM exige revisao fiscal.")
        technical_change = len(materials) > 1 or any(
            m.pdm_class_id != changes.after.pdm_class_id
            or m.attributes != changes.after.attributes
            or m.unit != changes.after.unit
            or m.pdm_description != validation.formatted_description
            or (group is not None and merchandise_group(m) != group)
            for m in materials
        )
        if (
            technical_change or proposal.proposal_type != "NCM_CORRECTION"
        ) and proposal.technical_review_status == "NOT_REQUIRED":
            raise ApiError(422, "TECHNICAL_REVIEW_REQUIRED", "A alteracao tecnica exige revisao da Governanca.")
        if (
            not partial_enrichment
            and changes.after.ncm is not None
            and _ncm(changes.after.ncm)
            not in {
                _ncm(code)
                for reference in catalog.classes[changes.after.pdm_class_id].ncm_references
                for code in reference.codes
            }
        ):
            raise ApiError(422, "NCM_REFERENCE_MISMATCH", "NCM nao consta nas referencias desta classe do PDM.")
        if len(materials) > 1 and proposal.proposal_type not in {"MERGE", "COMPOSITE"}:
            raise ApiError(422, "INVALID_PROPOSAL", "Tipo de proposta nao permite unificacao.")
        if proposal.proposal_type == "MERGE" and len(materials) < 2:
            raise ApiError(422, "INVALID_PROPOSAL", "Unificacao exige ao menos dois materiais.")
        if len(materials) > 1:
            classifier = get_classification_repository(catalog)
            extractor = get_extraction_repository()
            target = AnalyzedMaterial(
                MaterialRecord("", "ATIVO", ""),
                changes.after.pdm_class_id,
                changes.after.item_name,
                {k: v for k, v in changes.after.attributes.items() if v},
                validation.identity_key,
            )
            for interpretation, material in [
                (i, next(m for m in materials if m.id == i.material_id)) for i in interpretations
            ]:
                checked = _validation(catalog, interpretation)
                if checked.identity_key != validation.identity_key:
                    raise ApiError(422, "IDENTITY_CONFLICT", "Materiais diferentes nao podem ser unificados.")
                record = MaterialRecord(
                    material.material_code,
                    material.status,
                    material.original_description_long or "",
                    manufacturer=material.manufacturer or "",
                    reference=material.manufacturer_reference or "",
                )
                classification = classifier.classify(ClassificationInput(record.description))
                pdm_class = catalog.classes[interpretation.pdm_class_id]
                matched_names = [e.matched_name for e in classification.evidence if e.class_id == pdm_class.id]
                evidence_item = resolve_item_name(pdm_class, matched_names)
                extraction = extractor.extract(pdm_class, record.description)
                current = AnalyzedMaterial(
                    record,
                    classification.pdm_class_id or interpretation.pdm_class_id,
                    evidence_item or interpretation.item_name,
                    {
                        **{k: v for k, v in interpretation.attributes.items() if v},
                        **{k: v.value for k, v in extraction.attributes.items()},
                    },
                    checked.identity_key,
                    item_name_review_reasons(pdm_class, matched_names),
                )
                # A interpretação proposta e a evidência original não podem se contradizer.
                proposed = AnalyzedMaterial(
                    record,
                    interpretation.pdm_class_id,
                    interpretation.item_name,
                    {k: v for k, v in interpretation.attributes.items() if v},
                    checked.identity_key,
                )
                for candidate in (proposed, current):
                    identity = decide_identity(catalog, target, candidate)
                    if identity.status != "SAME_MATERIAL":
                        code = (
                            "IDENTITY_REVIEW_REQUIRED" if identity.status == "REVIEW_REQUIRED" else "IDENTITY_CONFLICT"
                        )
                        raise ApiError(422, code, "Identidade nao confirmada: " + ", ".join(identity.reasons))
                if any(
                    value is not None and not _attribute_matches(name, value, changes.after.attributes.get(name))
                    for name, value in interpretation.attributes.items()
                ):
                    raise ApiError(
                        422, "ATTRIBUTE_CONFLICT", "A proposta descarta ou contradiz atributos de um membro."
                    )
                if material.pdm_class_id and material.pdm_class_id != interpretation.pdm_class_id:
                    raise ApiError(422, "IDENTITY_CONFLICT", "A classe atual diverge da interpretacao proposta.")
                for field, attribute in [
                    ("manufacturer", "FABRICANTE"),
                    ("manufacturer_reference", "REFERENCIA FABRICANTE"),
                ]:
                    if getattr(material, field) and not _attribute_matches(
                        attribute, getattr(material, field), interpretation.attributes.get(attribute)
                    ):
                        raise ApiError(
                            422, "IDENTITY_CONFLICT", "Fabricante ou referencia atuais divergem da proposta."
                        )
                if material.attributes and any(
                    not _attribute_matches(k, v, interpretation.attributes.get(k))
                    for k, v in material.attributes.items()
                ):
                    raise ApiError(422, "IDENTITY_CONFLICT", "Atributos atuais divergem da identidade proposta.")
        rows = inventory_rows(
            db,
            snapshots,
            changes.after.unit
            if proposal.technical_review_status != "NOT_REQUIRED" and proposal.proposal_type != "ENRICHMENT"
            else None,
            changes,
        )
        if decision.primary_material_code:
            if decision.review_area != "TECHNICAL":
                raise ApiError(422, "INVALID_PRIMARY", "Somente a revisao tecnica escolhe o principal.")
            primary = next((m for m in materials if m.material_code == decision.primary_material_code), None)
        else:
            primary = next((m for m in materials if m.id == proposal.primary_material_id), None)
        # NCM é dado fiscal do item em qualquer status; as demais propostas exigem principal ativo.
        if primary is None or (primary.status != "ATIVO" and not (ncm_only and len(materials) == 1)):
            raise ApiError(422, "INVALID_PRIMARY", "O principal deve ser um membro ativo da proposta.")
        for field in ("pdm_class_id", "attributes", "unit", "ncm"):
            if getattr(primary, field) != getattr(changes.after, field) and not changes.sources.get(field, "").strip():
                raise ApiError(422, "SOURCE_REQUIRED", "Toda alteracao deve registrar sua regra ou fonte.", field=field)
        if proposal.proposal_type == "ENRICHMENT":
            dataset = db.get(Dataset, changes.dataset_id)
            baseline = validate_enrichment_context(changes, primary, dataset, catalog)
            changed = {k: v for k, v in changes.after.attributes.items() if baseline.get(k) != v}
            if changes.enrichment_context is not None and not changed:
                raise ApiError(422, "EVIDENCE_REQUIRED", "Nenhum atributo novo com evidencia faz parte da proposta.")
            try:
                evidence_ids = [UUID(value) for value in proposal.evidence_ids]
            except (TypeError, ValueError):
                raise ApiError(422, "EVIDENCE_REQUIRED", "Identificadores de evidencia invalidos.") from None
            sources = list(
                db.scalars(
                    select(EnrichmentSource).where(
                        EnrichmentSource.tenant_id == principal.tenant_id,
                        EnrichmentSource.material_id == primary.id,
                        EnrichmentSource.id.in_(evidence_ids),
                    )
                )
            )
            if len(sources) != len(set(evidence_ids)) or any(
                changes.evidence_hashes.get(str(source.id)) != evidence_hash(source) for source in sources
            ):
                raise ApiError(409, "EVIDENCE_CHANGED", "A evidencia mudou. Gere uma nova proposta.")
            if any(
                not any(
                    source.attribute_name == key and source.proposed_value == value and source.source_url
                    for source in sources
                )
                for key, value in changed.items()
            ):
                raise ApiError(422, "EVIDENCE_REQUIRED", "Enriquecimento exige evidencia por atributo.")
            validate_internal_sources(changes, dataset, sources, primary, catalog)
            check_source_environment(sources)
            if partial_enrichment and any(
                not source.source_excerpt
                or not source.source_excerpt.strip()
                or not source.source_sha256
                or not source.s3_object_key
                or not source.confidence_basis
                or source.confidence_level not in {"HIGH", "MEDIUM", "LOW"}
                for source in sources
            ):
                raise ApiError(
                    422, "EVIDENCE_REQUIRED", "Cada valor exige trecho, documento e fundamento da confianca."
                )
            verified_sources = [
                source for source in sources if changed.get(source.attribute_name) == source.proposed_value
            ]
            if any(source.status == "REJECTED" for source in verified_sources):
                raise ApiError(422, "EVIDENCE_REJECTED", "Evidencia rejeitada exige nova proposta com outra evidencia.")
        if not ncm_only and any(m.status == "OBSOLETO" for m in materials):
            raise ApiError(422, "OBSOLETE_MEMBER", "Material obsoleto exige revisao separada.")
        ids = {m.id for m in materials}
        dependents = list(
            db.scalars(
                select(MaterialMaster)
                .where(
                    MaterialMaster.tenant_id == principal.tenant_id,
                    MaterialMaster.active_code_target.in_(ids - {primary.id}),
                )
                .with_for_update()
            )
        )
        if any(m.id not in ids for m in dependents) or any(
            m.active_code_target and m.active_code_target not in ids for m in materials
        ):
            raise ApiError(
                422, "DEPENDENT_MEMBERS_REQUIRED", "A proposta deve incluir os dependentes e seus principais."
            )
        if decision.review_area == "TECHNICAL":
            proposal.technical_review_status = "APPROVED"
            proposal.technical_reviewer_id = principal.user_id
            proposal.primary_material_id = primary.id
        else:
            proposal.fiscal_review_status = "APPROVED"
            proposal.fiscal_reviewer_id = principal.user_id
        if all(
            s in {"APPROVED", "NOT_REQUIRED"} for s in (proposal.technical_review_status, proposal.fiscal_review_status)
        ):
            # Libera primeiro as chaves canonicas dos membros bloqueados.
            for material in materials:
                if material.id != primary.id:
                    material.status = "BLOQUEADO"
                    material.active_code_target = primary.id
                    material.block_reason = "DUPLICIDADE_APROVADA"
                    material.is_canonical = False
                    material.version += 1
            db.flush()
            if proposal.technical_review_status == "APPROVED" and not ncm_only:
                primary.pdm_class_id = changes.after.pdm_class_id
                primary.pdm_version = changes.pdm_version
                primary.attributes = changes.after.attributes
                primary.pdm_description = validation.formatted_description or primary.pdm_description
                if partial_enrichment:
                    primary.is_canonical = primary.is_canonical and validation.status is ValidationStatus.VALID
                    primary.identity_key = validation.identity_key if primary.is_canonical else None
                else:
                    primary.identity_key = validation.identity_key
                    primary.is_canonical = True
                primary.unit = changes.after.unit
                primary.manufacturer = changes.after.attributes.get("FABRICANTE", primary.manufacturer)
                primary.manufacturer_reference = changes.after.attributes.get(
                    "REFERENCIA FABRICANTE", primary.manufacturer_reference
                )
                if group is not None:
                    # O original continua em original_merchandise_group e no snapshot da carga.
                    primary.merchandise_group = group
            primary.ncm = changes.after.ncm
            if proposal.fiscal_review_status == "APPROVED" and not partial_enrichment:
                primary.ncm_review_status = "APPROVED" if primary.ncm is not None else "MISSING"
            primary.version += 1
            for source in verified_sources:
                source.status = "APPROVED"
                source.validated_by_user_id = proposal.technical_reviewer_id
                source.validated_at = datetime.now(UTC)
            description_only = (
                proposal.proposal_type == "PDM_CORRECTION"
                and len(materials) == 1
                and ([change.field for change in changes.changes] == ["description"])
            )
            for row in rows:
                if description_only and _same_inventory_link(db, row, primary.id):
                    continue
                if proposal.proposal_type == "ENRICHMENT":
                    continue
                if proposal.technical_review_status != "APPROVED":
                    continue
                snapshot = row["snapshot"]
                link = db.get(InventoryConsolidation, snapshot.id)
                if link is None:
                    link = InventoryConsolidation(source_snapshot_id=snapshot.id, tenant_id=principal.tenant_id)
                    db.add(link)
                link.primary_material_id, link.proposal_id = primary.id, proposal.id
                link.factor, link.unit, link.conversion_source = row["factor"], row["unit"], row["source"]
            proposal.status = "APPLIED"
            result = {
                "primary_material_code": primary.material_code,
                "blocked_material_codes": [m.material_code for m in materials if m.id != primary.id],
            }
            after_inventory = consolidated_inventory(rows, financial=True)
    proposal.version += 1
    audit = _audit(
        db,
        principal,
        proposal,
        request_id,
        f"PROPOSAL_{decision.decision}_{decision.review_area}",
        decision.reason,
        before,
        {
            **proposal_state(proposal),
            "materials": [material_state(m) for m in materials],
            "inventory": after_inventory,
            "ncm_assessment": ncm_evaluation if decision.decision == "APPROVE" else None,
            "evidence": [
                {
                    "id": str(source.id),
                    "attribute_name": source.attribute_name,
                    "proposed_value": source.proposed_value,
                    "source_url": source.source_url,
                    "source_sha256": source.source_sha256,
                    "source_excerpt": source.source_excerpt,
                    "source_title": source.source_title,
                    "source_page": source.source_page,
                    "retrieved_at": source.retrieved_at.isoformat(),
                    "s3_object_key": source.s3_object_key,
                    "confidence_level": source.confidence_level,
                    "confidence_basis": source.confidence_basis,
                }
                for source in verified_sources
            ],
        },
        role,
        lot,
    )
    return 200, {
        "proposal_id": str(proposal.id),
        "version": proposal.version,
        "status": proposal.status,
        "technical_review_status": proposal.technical_review_status,
        "fiscal_review_status": proposal.fiscal_review_status,
        "result": result,
        "audit_event_id": str(audit.id),
    }
