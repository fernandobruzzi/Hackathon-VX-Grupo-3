"""Continuidade da necessidade após a decisão do cadastro, na mesma transação."""

from uuid import UUID, uuid4

from sqlalchemy import select

from vx_materials_api.db.models import MaterialMaster, MaterialRequest, PurchaseForward
from vx_materials_api.errors import ApiProblem
from vx_materials_api.services.material_request_service import _audit, audit_forward, quantity_text, summary


def resolve_requests(db, caller, role, order, reason, request_id):
    if order.status not in {"REGISTERED", "EXISTING", "REJECTED"}:
        return
    reason = reason or "Identificação revalidada pelas regras do cadastro."
    requests = db.scalars(
        select(MaterialRequest)
        .where(
            MaterialRequest.tenant_id == order.tenant_id,
            MaterialRequest.registration_order_id == order.id,
            MaterialRequest.status == "AGUARDANDO_CADASTRO",
        )
        .order_by(MaterialRequest.id)
        .with_for_update()
    ).all()
    for row in requests:
        if row.requester_user_id != order.requester_user_id or row.center_code != order.center_code:
            raise ApiProblem(
                409, "REGISTRATION_LINK_INVALID", "O cadastro e a solicitação têm dono ou centro diferentes."
            )
        before = summary(row, caller)
        message = reason
        forward = None
        if order.status == "REJECTED":
            row.status, row.closure_reason = "ENCERRADA", "CADASTRO_REJEITADO"
            action = "MATERIAL_REQUEST_REGISTRATION_REJECTED"
            message = (
                f"Cadastro rejeitado: {reason} Próxima ação: crie uma nova solicitação com as correções indicadas."
            )
        else:
            candidates = order.candidate_material_ids or []
            material_id = order.material_id
            if order.status == "EXISTING" and len(candidates) == 1:
                material_id = UUID(str(candidates[0]))
            material = (
                db.scalar(
                    select(MaterialMaster)
                    .where(
                        MaterialMaster.id == material_id,
                        MaterialMaster.tenant_id == row.tenant_id,
                        MaterialMaster.status == "ATIVO",
                    )
                    .with_for_update(read=True)
                )
                if material_id
                else None
            )
            if material is None or material.unit != row.unit:
                row.status = "EM_IDENTIFICACAO"
                action = "MATERIAL_REQUEST_REGISTRATION_REVIEW_REQUIRED"
                message = "Cadastro decidido, mas código ativo único e unidade compatível exigem revisão de Cadastro."
            else:
                row.material_id, row.status = material.id, "EM_ATENDIMENTO"
                action = "MATERIAL_REQUEST_MATERIAL_IDENTIFIED"
                message = f"Cadastro resolvido pelo código ativo {material.material_code}. {reason}"
                if order.status == "REGISTERED":
                    # Código recém-publicado não tem saldo importado: a necessidade confirmada segue para Compras.
                    forward = PurchaseForward(
                        id=uuid4(),
                        tenant_id=row.tenant_id,
                        material_request_id=row.id,
                        request_version=row.version,
                        material_id=material.id,
                        quantity=row.quantity,
                        unit=row.unit,
                        center_code=row.center_code,
                        status="ENCAMINHADO",
                        forwarded_by_user_id=caller.user_id,
                    )
                    db.add(forward)
                    action = "MATERIAL_REQUEST_FORWARDED_TO_PURCHASING"
                    message = (
                        f"Cadastro publicado: {material.material_code}. Encaminhado para compras: "
                        f"{quantity_text(row.quantity)} {row.unit}."
                    )
        row.version += 1
        db.flush()
        if forward is not None:
            audit_forward(db, caller, role, "PURCHASE_FORWARD_CREATED", forward, None, message, request_id)
        _audit(
            db,
            caller,
            role,
            row,
            before,
            message,
            request_id,
            action=action,
            extra={"registration_order_id": str(order.id), "registration_status": order.status},
        )
