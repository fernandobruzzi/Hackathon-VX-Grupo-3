"""Solicitação de material com autenticação local, transação e PostgreSQL reais."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import (
    AuditLog,
    ChatSession,
    MaterialMaster,
    MaterialRequest,
    OperationRequest,
    RegistrationOrder,
    UserSso,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.main import create_app
from vx_materials_api.schemas.material_requests import CreateMaterialRequest
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services.material_request_service import create_request

ORIGIN = "http://localhost:8000"
PATH = "/api/v1/material-requests"


def login(client, persona="SOLICITANTE_OPERACAO"):
    response = client.post("/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()


def headers(me, key=None):
    return {"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": key or str(uuid.uuid4())}


def payload(**values):
    return {
        "original_text": "  Preciso de 10 peças para manutenção.\nUrgente.",
        "quantity": "10",
        "unit": "PC",
        "center_code": "1200",
        **values,
    }


@pytest.fixture
def case(connection, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    app = create_app(session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"))
    with TestClient(app, base_url=ORIGIN) as client:
        me = login(client)
        with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
            yield client, db, me


def add_material(db, **values):
    row = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        source_system="TEST",
        material_code=str(uuid.uuid4()),
        status="ATIVO",
        unit="PC",
    )
    for key, value in values.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    return row


def create(client, me, body=None, key=None):
    response = client.post(PATH, json=body or payload(), headers=headers(me, key))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_persists_original_values_protocol_and_creation_audit(case):
    client, db, me = case
    material = add_material(db)
    body = payload(material_id=str(material.id), quantity="1.234567")
    response = create(client, me, body)
    assert response["protocol"].startswith("SM-")
    assert response["quantity"] == "1.234567"
    assert response["original_text"] == body["original_text"]
    assert response["status"] == "EM_ATENDIMENTO"
    assert response["requester_user_id"] == me["user"]["id"]
    row = db.get(MaterialRequest, uuid.UUID(response["id"]))
    assert row.quantity == Decimal("1.234567") and row.center_code == "1200" and row.unit == "PC"
    assert len(response["history"]) == 1
    assert response["history"][0]["before_status"] is None
    assert response["history"][0]["after_status"] == "EM_ATENDIMENTO"
    assert response["history"][0]["actor_user_id"] == me["user"]["id"]
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == response["id"])) == 1
    assert client.get(f"{PATH}/{row.id}").json() == response
    assert material.unit == "PC"


def test_idempotent_creation_replays_and_rejects_changed_content(case):
    client, db, me = case
    key = str(uuid.uuid4())
    first = create(client, me, key=key)
    assert first["status"] == "EM_IDENTIFICACAO"
    assert create(client, me, key=key) == first
    changed = client.post(PATH, json=payload(quantity="11"), headers=headers(me, key))
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == first["id"])) == 1


@pytest.mark.parametrize(
    "quantity", ["0", "-1", "NaN", "Infinity", "1e5", "1,2", 1.5, "1.1234567", "1000000000000000000.1", "00.1"]
)
def test_invalid_quantity_is_rejected_without_writes(case, quantity):
    client, db, me = case
    response = client.post(PATH, json=payload(quantity=quantity), headers=headers(me))
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0


@pytest.mark.parametrize("field", ["role", "actor_id", "requester_user_id", "tenant_id", "status", "approved_by"])
def test_client_cannot_supply_authority_or_state(case, field):
    client, _, me = case
    assert client.post(PATH, json=payload(**{field: "injetado"}), headers=headers(me)).status_code == 422


@pytest.mark.parametrize(
    "values,code",
    [
        ({"unit": "CX"}, "UNIT_MISMATCH"),
        ({"status": "BLOQUEADO"}, "INACTIVE_MATERIAL"),
        ({"tenant_id": uuid.uuid4()}, "NOT_FOUND"),
    ],
)
def test_material_must_be_active_in_tenant_with_compatible_unit(case, values, code):
    client, db, me = case
    material = add_material(db, **values)
    response = client.post(PATH, json=payload(material_id=str(material.id)), headers=headers(me))
    assert response.status_code in (404, 422)
    assert response.json()["error"]["code"] == code
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0


def test_unauthorized_center_csrf_and_origin_rejected_before_writes(case):
    client, db, me = case
    assert client.post(PATH, json=payload(center_code="9999"), headers=headers(me)).status_code == 403
    assert (
        client.post(PATH, json=payload(), headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())}).status_code
        == 403
    )
    assert (
        client.post(PATH, json=payload(), headers={**headers(me), "Origin": "https://hostil.example"}).status_code
        == 403
    )
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0


def test_requester_cannot_read_others_but_governance_sees_only_its_queue(case):
    client, db, me = case
    pending = create(client, me)
    assert client.get(f"{PATH}/{pending['id']}", params={"mine": "true"}).status_code == 200
    material = add_material(db)
    identified = create(client, me, payload(material_id=str(material.id)))
    fiscal = login(client, "AUDITOR_FISCAL")
    assert client.get(f"{PATH}/{pending['id']}").status_code == 404
    assert client.get(PATH).json()["items"] == []
    assert (
        client.post(
            f"{PATH}/{pending['id']}/cancel",
            json={"expected_version": 1, "reason": "Não é meu."},
            headers=headers(fiscal),
        ).status_code
        == 404
    )
    governance = login(client, "GESTOR_CADASTRO")
    assert client.get(f"{PATH}/{pending['id']}").status_code == 200
    assert client.get(f"{PATH}/{pending['id']}", params={"mine": "true"}).status_code == 404
    assert client.get(f"{PATH}/{identified['id']}").status_code == 404
    items = client.get(PATH).json()["items"]
    assert [item["id"] for item in items] == [pending["id"]]
    assert items[0]["can_cancel"] is False
    assert client.get(PATH, params={"mine": "true"}).json()["items"] == []
    assert (
        client.post(
            f"{PATH}/{pending['id']}/cancel",
            json={"expected_version": 1, "reason": "Outra pessoa."},
            headers=headers(governance),
        ).status_code
        == 404
    )


def test_cancel_is_versioned_idempotent_and_audited(case):
    client, db, me = case
    first = create(client, me)
    url = f"{PATH}/{first['id']}/cancel"
    assert (
        client.post(url, json={"expected_version": 2, "reason": "Não preciso."}, headers=headers(me)).status_code == 409
    )
    key = str(uuid.uuid4())
    body = {"expected_version": 1, "reason": "Não preciso mais."}
    response = client.post(url, json=body, headers=headers(me, key))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ENCERRADA" and result["closure_reason"] == "CANCELADA" and result["version"] == 2
    assert result["history"][-1]["before_status"] == "EM_IDENTIFICACAO"
    assert result["history"][-1]["after_status"] == "ENCERRADA"
    assert result["history"][-1]["reason"] == body["reason"]
    assert len(result["history"]) == 2
    assert client.post(url, json=body, headers=headers(me, key)).json() == result
    assert client.post(url, json={**body, "expected_version": 2}, headers=headers(me)).status_code == 409
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == first["id"])) == 2


def test_pagination_filters_and_unique_protocols(case):
    client, _, me = case
    created = [create(client, me) for _ in range(3)]
    assert len({row["protocol"] for row in created}) == 3
    first = client.get(PATH, params={"limit": 2, "status": "EM_IDENTIFICACAO"}).json()
    second = client.get(PATH, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert {r["id"] for r in first["items"] + second["items"]} == {r["id"] for r in created}
    assert second["next_cursor"] is None
    assert client.get(PATH, params={"cursor": "inválido"}).status_code == 422


def test_chat_and_order_links_require_owner_and_same_center(case):
    client, db, me = case
    chat = ChatSession(
        tenant_id=TENANT_ID,
        owner_user_id=uuid.UUID(me["user"]["id"]),
        context={"center_code": "1200"},
        pdm_version="pdm-kit-v1",
        ncm_version="ncm-demo-v1",
        status="ACTIVE",
    )
    order = RegistrationOrder(
        tenant_id=TENANT_ID,
        requester_user_id=uuid.UUID(me["user"]["id"]),
        origin="CHAT",
        original_text="Necessidade original",
        center_code="1200",
        status="INCOMPLETE",
    )
    db.add_all([chat, order])
    db.flush()
    chat.registration_order_id = order.id
    db.commit()
    request = payload(chat_session_id=str(chat.id), registration_order_id=str(order.id))
    response = create(client, me, request)
    assert response["status"] == "AGUARDANDO_CADASTRO"
    assert response["registration_order_id"] == str(order.id) and response["chat_session_id"] == str(chat.id)
    assert client.post(PATH, json={**request, "center_code": "1100"}, headers=headers(me)).status_code == 422
    other = login(client, "GESTOR_CADASTRO")
    assert client.post(PATH, json=request, headers=headers(other)).status_code == 404


def test_audit_failure_rolls_back_request_and_idempotency(case, monkeypatch):
    client, db, me = case
    from vx_materials_api.services import material_request_service

    def fail(*args):
        raise RuntimeError("falha simulada da auditoria")

    monkeypatch.setattr(material_request_service, "_audit", fail)
    with pytest.raises(RuntimeError, match="auditoria"):
        client.post(PATH, json=payload(), headers=headers(me))
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(OperationRequest)
            .where(OperationRequest.operation == "material-request.create")
        )
        == 0
    )


def test_concurrent_replays_create_one_request_and_one_audit(migrated_url):
    engine = create_engine(migrated_url)
    user_id, tenant = uuid.uuid4(), uuid.uuid4()
    roles = ("ROLE_SOLICITANTE",)
    identity = Identity(
        user_id, tenant, roles, permissions_for(roles), frozenset({"1200"}), authentication_method="bearer"
    )
    factory = sessionmaker(engine)
    with factory.begin() as db:
        db.add(UserSso(id=user_id, tenant_id=tenant, issuer="test-material-request", subject=str(user_id)))
    key = uuid.uuid4()

    def run(_):
        with factory() as db:
            return create_request(db, identity, CreateMaterialRequest.model_validate(payload()), key, "concurrent")

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(run, range(2)))
        assert responses[0] == responses[1]
        with factory() as db:
            assert (
                db.scalar(select(func.count()).select_from(MaterialRequest).where(MaterialRequest.tenant_id == tenant))
                == 1
            )
            assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant)) == 1
        with factory() as db:
            revoked = replace(identity, center_codes=frozenset())
            with pytest.raises(ApiProblem) as error:
                create_request(db, revoked, CreateMaterialRequest.model_validate(payload()), key, "revoked")
            assert error.value.status == 403
    finally:
        with factory.begin() as db:
            for table in (OperationRequest, AuditLog, MaterialRequest):
                column = table.user_id if table is OperationRequest else table.tenant_id
                db.execute(table.__table__.delete().where(column == (user_id if table is OperationRequest else tenant)))
            db.execute(UserSso.__table__.delete().where(UserSso.id == user_id))
        engine.dispose()


def test_get_list_and_replay_follow_revoked_center_scope(case):
    client, db, me = case
    key = str(uuid.uuid4())
    row = create(client, me, key=key)
    identity = Identity(
        uuid.UUID(me["user"]["id"]),
        TENANT_ID,
        ("ROLE_SOLICITANTE",),
        permissions_for(("ROLE_SOLICITANTE",)),
        frozenset({"1100"}),
        authentication_method="bearer",
    )
    client.app.state.request_identity_provider = lambda request, session: identity
    assert client.get(f"{PATH}/{row['id']}").status_code == 404
    assert client.get(PATH).json()["items"] == []
    assert client.post(PATH, json=payload(), headers={"Idempotency-Key": key}).status_code == 403
    client.app.state.request_identity_provider = lambda request, session: replace(
        identity, tenant_id=uuid.uuid4(), center_codes=frozenset({"1200"})
    )
    assert client.get(f"{PATH}/{row['id']}").status_code == 404
    assert client.get(PATH).json()["items"] == []
    assert client.post(PATH, json=payload(), headers={"Idempotency-Key": key}).status_code == 404


@pytest.mark.parametrize("quantity", ["0.000001", "999999999999999999.999999"])
def test_decimal_limits_are_stored_without_rounding(case, quantity):
    client, db, me = case
    row = create(client, me, payload(quantity=quantity))
    assert Decimal(row["quantity"]) == Decimal(quantity)
    assert db.get(MaterialRequest, uuid.UUID(row["id"])).quantity == Decimal(quantity)
    assert client.get(f"{PATH}/{row['id']}").json()["quantity"] == row["quantity"]


def test_database_privileges_and_quantity_constraints(case, connection):
    from sqlalchemy.exc import IntegrityError
    from test_db_schema import as_role, denied

    client, _, me = case
    statement = (
        "INSERT INTO material_requests "
        "(tenant_id, requester_user_id, original_text, quantity, unit, center_code, status) "
        "VALUES (:tenant, :user, 'Necessidade', :quantity, 'PC', '1200', 'EM_IDENTIFICACAO') RETURNING protocol_number"
    )
    parameters = {"tenant": TENANT_ID, "user": me["user"]["id"], "quantity": "1"}
    result = as_role(connection, "api_user", statement, **parameters)
    assert result[0][0] > 0
    denied(connection, "batch_user", "SELECT * FROM material_requests")
    denied(connection, "mcp_reader", "SELECT * FROM material_requests")
    for quantity in ("0", "-1", "NaN"):
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(text(statement), {**parameters, "quantity": quantity})


def test_fiscal_queue_requires_a_linked_order_awaiting_fiscal_review(case):
    client, db, me = case
    order = RegistrationOrder(
        tenant_id=TENANT_ID,
        requester_user_id=uuid.UUID(me["user"]["id"]),
        origin="CHAT",
        original_text="Cadastro",
        center_code="1200",
        status="PENDING_FISCAL",
    )
    db.add(order)
    db.commit()
    row = create(client, me, payload(registration_order_id=str(order.id)))
    login(client, "AUDITOR_FISCAL")
    assert client.get(f"{PATH}/{row['id']}").status_code == 200
    assert [r["id"] for r in client.get(PATH).json()["items"]] == [row["id"]]
    order.status = "READY_FOR_REVIEW"
    db.commit()
    assert client.get(f"{PATH}/{row['id']}").status_code == 404
    assert client.get(PATH).json()["items"] == []


def count_rows(db, table, *conditions):
    return db.scalar(select(func.count()).select_from(table).where(*conditions))


def test_open_request_of_same_material_and_center_warns_owner_with_protocol(case):
    client, db, me = case
    material = add_material(db)
    body = payload(material_id=str(material.id))
    first = create(client, me, body)
    key = str(uuid.uuid4())
    warned = client.post(PATH, json=body, headers=headers(me, key))
    assert warned.status_code == 409, warned.text
    error = warned.json()["error"]
    assert error["code"] == "OPEN_REQUESTS_EXIST"
    shown = error["details"]["open_requests"][0]
    assert datetime.fromisoformat(shown["created_at"]) == datetime.fromisoformat(first["created_at"])
    shown["created_at"] = first["created_at"]
    assert error["details"] == {
        "total_count": 1,
        "hidden_count": 0,
        "open_requests": [
            {
                "id": first["id"],
                "protocol": first["protocol"],
                "status": "EM_ATENDIMENTO",
                "quantity": first["quantity"],
                "unit": "PC",
                "created_at": first["created_at"],
            }
        ],
    }
    assert count_rows(db, MaterialRequest) == 1
    assert count_rows(db, OperationRequest, OperationRequest.idempotency_key == key) == 0
    # O aviso não grava resposta idempotente: a mesma chave pode confirmar.
    confirmed = create(client, me, {**body, "acknowledge_open_requests": True}, key=key)
    assert confirmed["id"] != first["id"] and confirmed["status"] == "EM_ATENDIMENTO"
    assert "1 solicitação(ões) aberta(s)" in confirmed["history"][0]["reason"]
    assert create(client, me, {**body, "acknowledge_open_requests": True}, key=key) == confirmed
    event = db.scalar(select(AuditLog).where(AuditLog.entity_id == confirmed["id"]))
    assert event.action == "MATERIAL_REQUEST_CREATED"
    assert event.after_json["open_request_acknowledgement"] == {
        "total_count": 1,
        "hidden_count": 0,
        "visible_request_ids": [first["id"]],
    }
    first_event = db.scalar(select(AuditLog).where(AuditLog.entity_id == first["id"]))
    assert "open_request_acknowledgement" not in first_event.after_json and first_event.reason is None


def test_warning_for_invisible_requests_reveals_only_the_aggregate_count(case):
    client, db, me = case
    material = add_material(db)
    body = payload(material_id=str(material.id), original_text="Texto privado do solicitante", quantity="7")
    create(client, me, body)
    create(client, me, {**body, "acknowledge_open_requests": True})
    governance = login(client, "GESTOR_CADASTRO")
    warned = client.post(PATH, json=payload(material_id=str(material.id)), headers=headers(governance))
    assert warned.status_code == 409
    assert warned.json()["error"]["details"] == {"total_count": 2, "hidden_count": 2, "open_requests": []}
    assert "Texto privado" not in warned.text and me["user"]["id"] not in warned.text
    confirmed = create(client, governance, payload(material_id=str(material.id), acknowledge_open_requests=True))
    event = db.scalar(select(AuditLog).where(AuditLog.entity_id == confirmed["id"]))
    assert event.after_json["open_request_acknowledgement"] == {
        "total_count": 2,
        "hidden_count": 2,
        "visible_request_ids": [],
    }
    assert "2 solicitação(ões)" in confirmed["history"][0]["reason"]


def test_closed_requests_other_centers_and_unresolved_material_do_not_warn(case):
    client, db, me = case
    material = add_material(db)
    body = payload(material_id=str(material.id))
    cancelled = create(client, me, body)
    response = client.post(
        f"{PATH}/{cancelled['id']}/cancel", json={"expected_version": 1, "reason": "Não preciso."}, headers=headers(me)
    )
    assert response.status_code == 200
    concluded = create(client, me, body)
    row = db.get(MaterialRequest, uuid.UUID(concluded["id"]))
    row.status, row.closure_reason = "ENCERRADA", "ATENDIDA_ESTOQUE"
    db.commit()
    fresh = create(client, me, body)
    assert fresh["history"][0]["reason"] is None
    create(client, me, payload(material_id=str(material.id), center_code="1100"))
    create(client, me)
    assert create(client, me)["status"] == "EM_IDENTIFICACAO"
    event = db.scalar(select(AuditLog).where(AuditLog.entity_id == fresh["id"]))
    assert "open_request_acknowledgement" not in event.after_json
