"""Confirmação do chat: três caminhos, uma transação e uma solicitação por conversa."""

import copy
import uuid

import pytest
from sqlalchemy import func, select
from test_chat_submit import ready as ready
from test_chat_submit import ready_agent
from test_orders import case as case
from test_orders import catalog as catalog
from test_orders import headers, login, material

from vx_materials_api.db.models import (
    ChatSession,
    MaterialMaster,
    MaterialRequest,
    OperationRequest,
    RegistrationOrder,
)
from vx_materials_api.services import chat_service, material_request_service


def submit(ready, *, key=None, **values):
    client, _, me, turn, _ = ready
    return client.post(
        f"/api/v1/chat/{turn['session_id']}/request-material",
        headers=headers(me, key),
        json={"expected_session_version": turn["session_version"], "quantity": "10", "unit": "PC", **values},
    )


def test_new_material_creates_linked_request_and_order_atomically(ready):
    client, db, me, turn, _ = ready
    before = db.scalar(select(func.count()).select_from(MaterialMaster))
    response = submit(ready)
    assert response.status_code == 200, response.text
    result = response.json()
    row = result["material_request"]
    assert row["status"] == "AGUARDANDO_CADASTRO" and row["material_id"] is None
    order = db.get(RegistrationOrder, uuid.UUID(row["registration_order_id"]))
    assert order.status == "READY_FOR_REVIEW" and order.requester_user_id == uuid.UUID(me["user"]["id"])
    assert order.original_text == row["original_text"]
    assert row["chat_session_id"] == turn["session_id"] and row["quantity"] == "10.000000"
    assert result["session_version"] == turn["session_version"] + 1
    assert db.scalar(select(func.count()).select_from(MaterialMaster)) == before
    restored = client.get(f"/api/v1/chat/sessions/{turn['session_id']}").json()
    assert restored["material_request_submission"] == result
    assert restored["order_id"] == str(order.id)
    assert len(row["history"]) == 1
    assert (
        client.post(
            "/api/v1/chat/message",
            headers=headers(me),
            json={
                "session_id": turn["session_id"],
                "expected_session_version": result["session_version"],
                "client_message_id": str(uuid.uuid4()),
                "message": "Outro item",
                "center_code": "1200",
            },
        ).status_code
        == 409
    )


def test_replays_same_or_new_key_do_not_duplicate_and_changed_quantity_conflicts(ready):
    _, db, _, _, _ = ready
    key = str(uuid.uuid4())
    first = submit(ready, key=key)
    assert first.status_code == 200, first.text
    assert submit(ready, key=key).json() == first.json()
    assert submit(ready).json() == first.json()
    assert submit(ready, key=key, quantity="11").status_code == 409
    assert submit(ready, quantity="11").status_code == 409
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 1
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 1


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "1e5", "0.0000001", 1.5])
def test_invalid_quantity_is_rejected_before_any_order(ready, quantity):
    response = submit(ready, quantity=quantity)
    assert response.status_code == 422, response.text
    db = ready[1]
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0


@pytest.mark.parametrize("field", ["quantity", "unit"])
def test_missing_need_data_is_rejected(ready, field):
    client, _, me, turn, _ = ready
    body = {"expected_session_version": turn["session_version"], "quantity": "10", "unit": "PC"}
    del body[field]
    response = client.post(f"/api/v1/chat/{turn['session_id']}/request-material", headers=headers(me), json=body)
    assert response.status_code == 422


def test_stale_version_catalog_and_foreign_owner_are_rejected(ready):
    client, db, me, turn, _ = ready
    assert submit(ready, expected_session_version=999).status_code == 409
    other = login(client, "GESTOR_CADASTRO")
    assert (
        client.post(
            f"/api/v1/chat/{turn['session_id']}/request-material",
            headers=headers(other),
            json={"expected_session_version": turn["session_version"], "quantity": "10", "unit": "PC"},
        ).status_code
        == 404
    )
    me = login(client, "SOLICITANTE_OPERACAO")
    ready = (client, db, me, turn, ready[4])
    material(db, "NEW-CATALOG-238")
    db.commit()
    assert submit(ready).status_code == 409
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0


def test_request_failure_rolls_back_registration_order_and_session(ready, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("falha da auditoria da solicitação")

    monkeypatch.setattr(material_request_service, "_audit", fail)
    with pytest.raises(RuntimeError, match="auditoria"):
        submit(ready)
    client, db, _, turn, _ = ready
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0
    session = db.get(ChatSession, uuid.UUID(turn["session_id"]))
    assert session.registration_order_id is None and session.version == turn["session_version"]
    assert (
        db.scalar(select(func.count()).select_from(OperationRequest).where(OperationRequest.operation == "chat.submit"))
        == 0
    )


def existing_turn(ready, *, verified=True, code_claim=False):
    import httpx

    from vx_materials_api.services.agent_client import AgentClient

    client, db, me, turn, key = ready
    active = material(db, "ACTIVE-238")
    active.unit = "PC"
    old = material(db, "BLOCKED-238", status="BLOQUEADO")
    old.active_code_target = active.id
    db.commit()
    agent, validation = ready_agent(client.app.state.pdm_catalog)
    candidate = {
        "material_code": "BLOCKED-238",
        "status": "BLOQUEADO",
        "active_code_target": "ACTIVE-238",
        "identity_verified": verified,
        "match_type": "EXACT_MATERIAL_CODE" if code_claim else "EXACT_IDENTITY" if verified else "TEXT_SIMILARITY",
        "explicit_code_confirmed": code_claim,
        "description": "BUCHA",
        "inventory": [],
        "pending_checks": [] if verified else ["REVISAO_NAO_CONFIRMADA"],
    }
    agent.result["tool_calls"][0]["result"] = {"candidates": [candidate]}
    agent.result["material_card"].update(
        {
            "can_submit": False,
            "duplicate_check_status": "MATCH_FOUND",
            "existing": {
                "material_code": "ACTIVE-238",
                "status": "ATIVO",
                "pdm_description": "BUCHA",
                "match_type": "EXACT_IDENTITY",
                "reason": "Código ativo de destino.",
                "inventory": [],
            },
        }
    )
    client.app.state.agent_client = AgentClient("http://agent", transport=httpx.MockTransport(agent))
    if not verified:
        chosen_card = copy.deepcopy(agent.result["material_card"])
        agent.result["material_card"].pop("existing")
        agent.result["material_card"].update(
            {
                "duplicate_check_status": "PENDING",
                "similar_candidates": [
                    {
                        "material_code": "BLOCKED-238",
                        "status": "BLOQUEADO",
                        "active_code_target": "ACTIVE-238",
                        "pdm_description": "BUCHA",
                    }
                ],
            }
        )
        agent.result["context_patch"]["offered_material_codes"] = ["BLOCKED-238"]
        offered = client.post(
            "/api/v1/chat/message",
            headers=headers(me),
            json={
                "session_id": turn["session_id"],
                "expected_session_version": turn["session_version"],
                "client_message_id": str(uuid.uuid4()),
                "message": "Confirme os candidatos.",
                "center_code": "1200",
            },
        )
        assert offered.status_code == 200, offered.text
        turn = offered.json()
        agent.result["material_card"] = chosen_card
        agent.result["context_patch"]["offered_material_codes"] = []
    result = client.post(
        "/api/v1/chat/message",
        headers=headers(me),
        json={
            "session_id": turn["session_id"],
            "expected_session_version": turn["session_version"],
            "client_message_id": str(uuid.uuid4()),
            "message": "É o item BLOCKED-238",
            "center_code": "1200",
            **({"action": {"type": "PICK_CANDIDATE", "material_code": "BLOCKED-238"}} if not verified else {}),
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "EXISTING"
    return (client, db, me, result.json(), key), active


def test_existing_under_another_code_uses_active_code_without_registration(ready):
    state, active = existing_turn(ready)
    response = submit(state)
    assert response.status_code == 200, response.text
    row = response.json()["material_request"]
    assert row["status"] == "EM_ATENDIMENTO" and row["material_id"] == str(active.id)
    assert row["registration_order_id"] is None
    assert state[1].scalar(select(func.count()).select_from(RegistrationOrder)) == 0
    restored = state[0].get(f"/api/v1/chat/sessions/{state[3]['session_id']}").json()
    assert restored["material_request_submission"]["material_request"]["protocol"] == row["protocol"]


def test_unverified_similar_even_explicitly_selected_stays_for_technical_identification(ready):
    state, _ = existing_turn(ready, verified=False)
    response = submit(state)
    assert response.status_code == 200, response.text
    row = response.json()["material_request"]
    assert row["status"] == "EM_IDENTIFICACAO" and row["material_id"] is None and row["registration_order_id"] is None
    assert state[1].scalar(select(func.count()).select_from(RegistrationOrder)) == 0


def test_incomplete_identification_creates_review_without_registration(ready):
    client, db, _, turn, _ = ready
    session = db.get(ChatSession, uuid.UUID(turn["session_id"]))
    card = copy.deepcopy(session.context["material_card"])
    card.update({"validation_status": "INCOMPLETE", "can_submit": False, "duplicate_check_status": "PENDING"})
    session.context = {**session.context, "material_card": card, chat_service.DUPLICATE_CHECK: None}
    db.commit()
    response = submit(ready)
    assert response.status_code == 200, response.text
    row = response.json()["material_request"]
    assert row["status"] == "EM_IDENTIFICACAO" and row["registration_order_id"] is None
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0


@pytest.mark.parametrize("mixed", [False, True])
def test_concurrent_confirmation_or_public_creation_cannot_duplicate(migrated_url, catalog, mixed):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from vx_materials_api.db.models import AuditLog, ChatMessage, UserSso
    from vx_materials_api.errors import ApiProblem
    from vx_materials_api.schemas.chat import ChatMaterialRequest
    from vx_materials_api.schemas.material_requests import CreateMaterialRequest
    from vx_materials_api.security.identity import Identity
    from vx_materials_api.security.permissions import permissions_for
    from vx_materials_api.services.chat_material_request_service import submit_request

    engine = create_engine(migrated_url)
    factory = sessionmaker(engine)
    user, tenant, sid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    roles = ("ROLE_SOLICITANTE",)
    caller = Identity(user, tenant, roles, permissions_for(roles), frozenset({"1200"}), authentication_method="bearer")
    card = {
        "pdm_class_id": None,
        "attributes": {},
        "pdm_description": None,
        "validation_status": "OUT_OF_SCOPE",
        "missing_attributes": [],
        "ncm": {"suggested": None, "status": "PENDING_VALIDATION"},
        "duplicate_check_status": "PENDING",
        "can_submit": False,
    }
    with factory.begin() as db:
        db.add(UserSso(id=user, tenant_id=tenant, issuer="test-chat-238", subject=str(user)))
        db.flush()
        db.add(
            ChatSession(
                id=sid,
                tenant_id=tenant,
                owner_user_id=user,
                context={"center_code": "1200", "history_center_codes": ["1200"], "material_card": card},
                version=1,
                status="ACTIVE",
                pdm_version=catalog.version,
                ncm_version="ncm-demo-v1",
            )
        )
        db.flush()
        db.add(
            ChatMessage(
                session_id=sid, sequence=1, author_type="USER", actor_user_id=user, content="Peça em identificação"
            )
        )
    key = uuid.uuid4()

    def run(number):
        with factory() as db:
            try:
                if mixed and number == 1:
                    return material_request_service.create_request(
                        db,
                        caller,
                        CreateMaterialRequest(
                            original_text="Peça em identificação",
                            quantity="10",
                            unit="PC",
                            center_code="1200",
                            chat_session_id=sid,
                        ),
                        key,
                        "concurrent",
                    )
                return submit_request(
                    db,
                    caller,
                    catalog,
                    sid,
                    ChatMaterialRequest(expected_session_version=1, quantity="10", unit="PC"),
                    key,
                    "concurrent",
                )
            except ApiProblem as error:
                return error

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        assert any(not isinstance(r, ApiProblem) for r in results)
        assert all(not isinstance(r, ApiProblem) or r.status == 409 for r in results)
        with factory() as db:
            assert (
                db.scalar(
                    select(func.count()).select_from(MaterialRequest).where(MaterialRequest.chat_session_id == sid)
                )
                == 1
            )
            assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant)) == 1
    finally:
        with factory.begin() as db:
            db.execute(OperationRequest.__table__.delete().where(OperationRequest.user_id == user))
            db.execute(AuditLog.__table__.delete().where(AuditLog.tenant_id == tenant))
            db.execute(MaterialRequest.__table__.delete().where(MaterialRequest.tenant_id == tenant))
            db.execute(ChatMessage.__table__.delete().where(ChatMessage.session_id == sid))
            db.execute(ChatSession.__table__.delete().where(ChatSession.id == sid))
            db.execute(UserSso.__table__.delete().where(UserSso.id == user))
        engine.dispose()


def test_csrf_and_client_authority_are_rejected_before_any_creation(ready):
    client, db, me, turn, _ = ready
    url = f"/api/v1/chat/{turn['session_id']}/request-material"
    body = {"expected_session_version": turn["session_version"], "quantity": "10", "unit": "PC"}
    assert (
        client.post(
            url, json=body, headers={"Origin": "http://localhost:8000", "Idempotency-Key": str(uuid.uuid4())}
        ).status_code
        == 403
    )
    for field in ("material_id", "center_code", "role", "actor_id", "registration_order_id"):
        assert client.post(url, json={**body, field: "forjado"}, headers=headers(me)).status_code == 422
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0


def test_unconfirmed_code_match_cannot_replace_user_description(ready):
    state, _ = existing_turn(ready, verified=False, code_claim=True)
    client, db, _, turn, _ = state
    session = db.get(ChatSession, uuid.UUID(turn["session_id"]))
    saved = copy.deepcopy(session.context[chat_service.DUPLICATE_CHECK])
    # O indicador interno só pode ser produzido pela validação da mensagem na API.
    assert not saved["candidates"][0].get("explicit_code_confirmed")
    row = submit(state).json()["material_request"]
    assert row["status"] == "EM_IDENTIFICACAO" and row["material_id"] is None


@pytest.mark.parametrize("text", ["x" * 10001, "   "])
def test_invalid_saved_source_returns_validation_error_and_rolls_back_everything(ready, text):
    from vx_materials_api.db.models import ChatMessage

    _, db, _, turn, _ = ready
    message = db.scalar(
        select(ChatMessage).where(
            ChatMessage.session_id == uuid.UUID(turn["session_id"]), ChatMessage.author_type == "USER"
        )
    )
    message.content = text
    db.commit()
    response = submit(ready)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "REQUEST_SOURCE_INVALID"
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 0
    assert (
        db.scalar(select(func.count()).select_from(OperationRequest).where(OperationRequest.operation == "chat.submit"))
        == 0
    )


def test_existing_open_need_requires_explicit_acknowledgement_in_chat(ready):
    state, active = existing_turn(ready)
    client, db, me, _, _ = state
    first = client.post(
        "/api/v1/material-requests",
        headers=headers(me),
        json={
            "original_text": "Outra necessidade",
            "quantity": "2",
            "unit": "PC",
            "center_code": "1200",
            "material_id": str(active.id),
        },
    )
    assert first.status_code == 201, first.text
    key = str(uuid.uuid4())
    warning = submit(state, key=key)
    assert warning.status_code == 409, warning.text
    assert warning.json()["error"]["code"] == "OPEN_REQUESTS_EXIST"
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 1
    confirmed = submit(state, key=key, acknowledge_open_requests=True)
    assert confirmed.status_code == 200, confirmed.text
    assert submit(state, key=key, acknowledge_open_requests=True).json() == confirmed.json()
    assert "confirmação de 1" in confirmed.json()["material_request"]["history"][0]["reason"]
    assert db.scalar(select(func.count()).select_from(MaterialRequest)) == 2
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0
