"""Continuidade transacional entre decisão do cadastro, solicitação e Compras."""

import uuid

import pytest
from sqlalchemy import func, select
from test_orders import (
    BUCHA,
    decide,
    headers,
    login,
    material,
    set_current_identity,
)
from test_orders import case as case
from test_orders import catalog as catalog
from test_orders import imported as imported
from test_orders import kit_orders as kit_orders

from pipelines.import_orders import OrderRow, analyze_order
from vx_materials_api.db.models import AuditLog, MaterialMaster, MaterialRequest, PurchaseForward
from vx_materials_api.services import registration_request_service


@pytest.fixture
def linked(imported, unit="PC"):
    client, db, version, _, orders = imported
    me = login(client, "SOLICITANTE_OPERACAO")
    order = orders["SC-202600001"]
    order.requester_user_id = uuid.UUID(me["user"]["id"])
    order.center_code = "1200"
    db.commit()
    response = client.post(
        "/api/v1/material-requests",
        headers=headers(me),
        json={
            "original_text": "Preciso de três peças",
            "quantity": "3",
            "unit": unit,
            "center_code": "1200",
            "registration_order_id": str(order.id),
        },
    )
    assert response.status_code == 201, response.text
    return client, db, order, response.json(), version


def publish(linked, *, key=None):
    client, _, order, _, _ = linked
    assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
    fiscal = login(client, "AUDITOR_FISCAL")
    response = decide(client, fiscal, order.id, 2, key=key)
    assert response.status_code == 200, response.text
    return response, fiscal


def request_detail(client, request):
    login(client, "SOLICITANTE_OPERACAO")
    response = client.get(f"/api/v1/material-requests/{request['id']}")
    assert response.status_code == 200, response.text
    return response.json()


def test_publication_links_same_protocol_and_forwards_once_with_audit(linked):
    client, db, order, original, _ = linked
    key = str(uuid.uuid4())
    published, fiscal = publish(linked, key=key)
    assert published.json()["status"] == "REGISTERED"
    assert decide(client, fiscal, order.id, 2, key=key).json() == published.json()
    result = request_detail(client, original)
    assert result["protocol"] == original["protocol"] and result["version"] == 2
    assert result["status"] == "EM_ATENDIMENTO"
    assert result["forwarded_quantity"] == "3.000000" and result["pending_quantity"] == "0.000000"
    assert len(result["purchase_forwards"]) == 1
    assert result["purchase_forwards"][0]["material_code"] == published.json()["material_code"]
    assert result["purchase_forwards"][0]["quantity"] == "3.000000"
    assert result["history"][-1]["action"] == "MATERIAL_REQUEST_FORWARDED_TO_PURCHASING"
    assert db.scalar(select(func.count()).select_from(PurchaseForward)) == 1
    event = db.scalar(select(AuditLog).where(AuditLog.action == "PURCHASE_FORWARD_CREATED"))
    assert event.effective_role == "ROLE_AUDITOR_FISCAL"
    login(client, "COMPRAS")
    queue = client.get("/api/v1/purchase-forwards").json()["items"]
    assert len(queue) == 1 and queue[0]["request_protocol"] == original["protocol"]


@pytest.mark.parametrize("fiscal", [False, True])
def test_rejection_keeps_protocol_reason_and_next_action(linked, fiscal):
    client, db, order, original, _ = linked
    version = 1
    if fiscal:
        assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
        version = 2
    reviewer = login(client, "AUDITOR_FISCAL" if fiscal else "GESTOR_CADASTRO")
    assert decide(client, reviewer, order.id, version, "REJECT").status_code == 200
    result = request_detail(client, original)
    assert result["protocol"] == original["protocol"]
    assert result["status"] == "ENCERRADA" and result["closure_reason"] == "CADASTRO_REJEITADO"
    assert "Conferido no teste." in result["history"][-1]["reason"]
    assert "nova solicitação" in result["history"][-1]["reason"]
    assert db.scalar(select(func.count()).select_from(PurchaseForward)) == 0


@pytest.mark.parametrize("ambiguous", [False, True])
@pytest.mark.parametrize("stage", ["decide", "submit", "complement"])
def test_existing_material_resumes_fulfillment_without_automatic_purchase(linked, ambiguous, stage):
    client, db, order, original, _ = linked
    analysis = analyze_order(
        OrderRow("rival", order.original_text, order.attachment_text, order.center_code, None),
        client.app.state.pdm_catalog,
        *registration_repositories(client),
    )
    rival = set_current_identity(material(db, "80000001", identity=BUCHA, canonical=True), analysis)
    rival.unit = "PC"
    if ambiguous:
        other = set_current_identity(material(db, "80000002", identity=BUCHA), analysis)
        other.unit = "PC"
    db.commit()
    if stage == "decide":
        response = decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1)
    else:
        order.status = "DRAFT"
        db.commit()
        me = login(client, "SOLICITANTE_OPERACAO")
        payload = {"expected_version": 1}
        if stage == "complement":
            payload.update(text="Dados confirmados", source="Solicitante", reason="Conferido")
        response = client.post(f"/api/v1/registration-orders/{order.id}/{stage}", headers=headers(me), json=payload)
    assert response.status_code == 200 and response.json()["status"] == "EXISTING", response.text
    result = request_detail(client, original)
    if ambiguous:
        assert result["status"] == "EM_IDENTIFICACAO" and result["material_id"] is None
        assert result["purchase_forwards"] == []
        return
    assert result["status"] == "EM_ATENDIMENTO" and result["material_id"] == str(rival.id)
    assert result["protocol"] == original["protocol"] and result["pending_quantity"] == "3.000000"
    assert result["purchase_forwards"] == []
    assert result["history"][-1]["action"] == "MATERIAL_REQUEST_MATERIAL_IDENTIFIED"


def registration_repositories(client):
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    return get_classification_repository(client.app.state.pdm_catalog), get_extraction_repository()


def test_cancelled_request_is_not_reopened_by_publication(linked):
    client, db, _, original, _ = linked
    me = login(client, "SOLICITANTE_OPERACAO")
    cancelled = client.post(
        f"/api/v1/material-requests/{original['id']}/cancel",
        headers=headers(me),
        json={"expected_version": 1, "reason": "Não preciso mais"},
    )
    assert cancelled.status_code == 200, cancelled.text
    publish(linked)
    result = request_detail(client, original)
    assert result["status"] == "ENCERRADA" and result["closure_reason"] == "CANCELADA"
    assert result["version"] == 2 and result["purchase_forwards"] == []


def test_incompatible_unit_goes_to_review_without_conversion(linked):
    client, db, _, original, _ = linked
    row = db.get(MaterialRequest, uuid.UUID(original["id"]))
    row.unit = "CX"
    db.commit()
    publish(linked)
    result = request_detail(client, original)
    assert result["status"] == "EM_IDENTIFICACAO" and result["unit"] == "CX"
    assert result["material_id"] is None and result["purchase_forwards"] == []
    assert "unidade" in result["history"][-1]["reason"]


def test_request_audit_failure_rolls_back_material_order_and_forward(linked, monkeypatch):
    client, db, order, original, _ = linked
    assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
    fiscal = login(client, "AUDITOR_FISCAL")

    def fail(*args, **kwargs):
        raise RuntimeError("Falha da auditoria da solicitação")

    monkeypatch.setattr(registration_request_service, "_audit", fail)
    with pytest.raises(RuntimeError, match="auditoria"):
        decide(client, fiscal, order.id, 2)
    db.expire_all()
    assert order.status == "PENDING_FISCAL" and order.material_id is None
    assert db.scalar(select(func.count()).select_from(PurchaseForward)) == 0
    assert (
        db.scalar(select(func.count()).select_from(MaterialMaster).where(MaterialMaster.source_system == "VX-CADASTRO"))
        == 0
    )
    result = request_detail(client, original)
    assert result["status"] == "AGUARDANDO_CADASTRO" and result["version"] == 1
