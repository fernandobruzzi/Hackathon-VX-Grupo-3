"""Indicadores da jornada do solicitante no dashboard, com registros persistidos no PostgreSQL."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from test_dashboard import PATH, dashboard_case, login, principal  # noqa: F401

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import (
    AuditLog,
    ChatSession,
    MaterialMaster,
    MaterialRequest,
    PurchaseForward,
    RegistrationOrder,
    UserSso,
)
from vx_materials_api.services import journey_metrics
from vx_materials_api.services.metrics_service import metrics

ORIGIN = "http://localhost:8000"
START = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)
ALL_UNAVAILABLE = [
    {"indicator": name, "reason": "NO_REQUESTS"}
    for name in ("requests", "resolution_time", "registration_avoided", "identified_under_other_code")
]


@pytest.fixture
def journey_case(dashboard_case):  # noqa: F811
    client, db, _, materials, _, _, _ = dashboard_case
    requester = db.scalar(select(UserSso.id).where(UserSso.tenant_id == TENANT_ID).limit(1))
    return client, db, materials, requester


def add_request(db, requester, *, center="1100", status="EM_ATENDIMENTO", reason=None, material=None, **values):
    row = MaterialRequest(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        requester_user_id=requester,
        original_text="Necessidade original",
        quantity=Decimal(10),
        unit="PC",
        center_code=center,
        status=status,
        closure_reason=reason,
        material_id=material.id if material else None,
        created_at=START,
        **values,
    )
    db.add(row)
    db.flush()
    return row


def close(db, row, hours):
    db.add(
        AuditLog(
            tenant_id=TENANT_ID,
            actor_type="USER",
            action="MATERIAL_REQUEST_CLOSED",
            entity_type="material_request",
            entity_id=str(row.id),
            created_at=START + timedelta(hours=hours),
        )
    )


def forward(db, row, material, requester, status, version=1):
    db.add(
        PurchaseForward(
            tenant_id=TENANT_ID,
            material_request_id=row.id,
            request_version=version,
            material_id=material.id,
            quantity=Decimal(10),
            unit="PC",
            center_code=row.center_code,
            status=status,
            reason="Motivo" if status in {"DEVOLVIDO", "CANCELADO"} else None,
            forwarded_by_user_id=requester,
            handled_by_user_id=requester if status in {"ACEITO", "DEVOLVIDO"} else None,
        )
    )


def chat(db, requester, center, existing_code=None):
    check = {"status": "MATCH_FOUND", "existing": {"material_code": existing_code}} if existing_code else None
    session = ChatSession(
        tenant_id=TENANT_ID,
        owner_user_id=requester,
        context={"center_code": center, "duplicate_check": check},
        status="ACTIVE",
    )
    db.add(session)
    db.flush()
    return session.id


def seed_journey(db, materials, requester):
    material = materials[0]
    stock = add_request(db, requester, status="ENCERRADA", reason="ATENDIDA_ESTOQUE", material=material)
    close(db, stock, 2)
    partial = add_request(db, requester, status="ENCERRADA", reason="ATENDIDA_PARCIAL_COMPRAS", material=material)
    close(db, partial, 4)
    forward(db, partial, material, requester, "ACEITO")
    purchasing = add_request(db, requester, status="ENCERRADA", reason="ENCAMINHADA_COMPRAS", material=material)
    close(db, purchasing, 10)
    forward(db, purchasing, material, requester, "ACEITO")
    add_request(db, requester, status="ENCERRADA", reason="CANCELADA")
    waiting = add_request(db, requester, material=material, center="1200")
    forward(db, waiting, material, requester, "ENCAMINHADO")
    returned = add_request(db, requester, material=material)
    forward(db, returned, material, requester, "DEVOLVIDO")
    order = RegistrationOrder(
        tenant_id=TENANT_ID,
        requester_user_id=requester,
        origin="CHAT",
        original_text="Item novo",
        center_code="1100",
        status="REGISTERED",
    )
    db.add(order)
    db.flush()
    registered = add_request(db, requester, material=material, registration_order_id=order.id)
    forward(db, registered, material, requester, "ACEITO")
    add_request(db, requester, status="EM_IDENTIFICACAO")
    # Centro fora do escopo dos principais: nada daqui pode aparecer.
    outside = add_request(db, requester, center="2100", status="ENCERRADA", reason="ATENDIDA_ESTOQUE")
    close(db, outside, 100)
    hidden = add_request(db, requester, center="2100", material=material)
    forward(db, hidden, material, requester, "ENCAMINHADO")
    db.commit()


def test_journey_without_requests_is_unavailable_never_zero_filled(journey_case):
    client, _, _, _ = journey_case
    login(client)
    response = client.get(PATH)
    assert response.status_code == 200, response.text
    journey = response.json()["journey"]
    assert journey == {
        "requests_total": 0,
        "open": None,
        "closed": None,
        "resolution_time": None,
        "registration_avoided": None,
        "identified_under_other_code": None,
        "unavailable": ALL_UNAVAILABLE,
    }
    from test_contracts import validator

    validator({"$ref": "#/components/schemas/DashboardMetrics"}).validate(response.json())


def test_journey_separates_stock_partial_and_purchasing_within_authorized_centers(journey_case):
    _, db, materials, requester = journey_case
    seed_journey(db, materials, requester)
    journey = metrics(db, principal()).journey.model_dump(mode="json")
    assert journey["requests_total"] == 8
    assert journey["open"] == {"em_identificacao": 1, "aguardando_cadastro": 0, "em_atendimento": 3}
    assert journey["closed"] == {
        "atendida_estoque": 1,
        "atendida_parcial_compras": 1,
        "encaminhada_compras": 1,
        "cancelada": 1,
        "cadastro_rejeitado": 0,
    }
    # 2 h, 4 h e 10 h; o centro fora do escopo (100 h) não entra.
    assert journey["resolution_time"] == {"resolved_requests": 3, "median_hours": 4.0, "p90_hours": 10.0}
    # Parcial, compras e aguardando Compras, sem pedido de cadastro; devolvido e cadastrado não contam.
    assert journey["registration_avoided"] == 3
    assert journey["identified_under_other_code"] is None
    assert journey["unavailable"] == [{"indicator": "identified_under_other_code", "reason": "NO_CHAT_LINKED_REQUESTS"}]

    narrow = metrics(db, principal(("1200",))).journey.model_dump(mode="json")
    assert narrow["requests_total"] == 1 and narrow["registration_avoided"] == 1
    assert narrow["closed"]["atendida_estoque"] == 0
    assert narrow["resolution_time"] is None
    assert {"indicator": "resolution_time", "reason": "NO_RESOLVED_REQUESTS"} in narrow["unavailable"]


def test_journey_is_scoped_by_tenant(journey_case):
    _, db, materials, requester = journey_case
    seed_journey(db, materials, requester)
    other = replace(principal(), tenant_id=uuid.uuid4())
    assert journey_metrics.journey(db, other).model_dump(mode="json")["unavailable"] == ALL_UNAVAILABLE


def test_identified_under_other_code_needs_the_identity_match_saved_in_the_linked_chat(journey_case):
    _, db, materials, requester = journey_case
    active, target = materials
    blocked = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        source_system="TEST",
        material_code="BLOQ-1",
        status="BLOQUEADO",
        unit="PC",
        active_code_target=target.id,
    )
    db.add(blocked)
    db.flush()
    add_request(db, requester, material=active, chat_session_id=chat(db, requester, "1100", active.material_code))
    # Código bloqueado comprovado pela identidade aponta para o ativo da solicitação.
    add_request(db, requester, material=target, chat_session_id=chat(db, requester, "1100", "BLOQ-1"))
    # Conversa sem correspondência comprovada e conversa que comprovou outro material não contam.
    add_request(db, requester, material=active, chat_session_id=chat(db, requester, "1100"))
    add_request(db, requester, material=target, chat_session_id=chat(db, requester, "1100", active.material_code))
    add_request(
        db, requester, center="2100", material=active, chat_session_id=chat(db, requester, "2100", active.material_code)
    )
    db.commit()
    journey = metrics(db, principal()).journey
    assert journey.requests_total == 4 and journey.identified_under_other_code == 2
    assert all(item.indicator != "identified_under_other_code" for item in journey.unavailable)


def test_quality_view_keeps_journey_without_financial_values(journey_case):
    client, db, materials, requester = journey_case
    seed_journey(db, materials, requester)
    login(client)
    quality = client.get(PATH).json()
    assert "financial" not in quality
    login(client, "AUDITOR_FISCAL")
    executive = client.get(PATH + "?view=executive").json()
    assert executive["journey"] == quality["journey"]
    text = str(quality["journey"]).lower()
    assert not any(word in text for word in ("price", "value", "quantity", "brl"))


def test_requests_created_and_cancelled_through_the_api_reach_the_dashboard(journey_case):
    client, _, _, _ = journey_case
    me = login_json(client, "SOLICITANTE_OPERACAO")
    body = {"original_text": "Preciso de luvas", "quantity": "2", "unit": "PC", "center_code": "1100"}
    created = client.post(
        "/api/v1/material-requests",
        json=body,
        headers={"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
    )
    assert created.status_code == 201, created.text
    cancelled = client.post(
        f"/api/v1/material-requests/{created.json()['id']}/cancel",
        json={"expected_version": created.json()["version"], "reason": "Não preciso mais"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
    )
    assert cancelled.status_code == 200, cancelled.text
    login(client)
    journey = client.get(PATH).json()["journey"]
    assert journey["requests_total"] == 1 and journey["closed"]["cancelada"] == 1
    assert {"indicator": "resolution_time", "reason": "NO_RESOLVED_REQUESTS"} in journey["unavailable"]


def login_json(client, persona):
    response = client.post("/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()
