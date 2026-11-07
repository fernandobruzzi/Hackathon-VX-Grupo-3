"""Envio explícito de ficha do chat com sessão local, banco real e revisão posterior."""

import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from test_chat import FakeAgent
from test_chat import factory as factory
from test_contracts import validator
from test_orders import case as case
from test_orders import catalog as catalog
from test_orders import decide, headers, index, login, material

from domain.identity import identity_signature
from domain.pdm_validator import validate_pdm
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import AuditLog, ChatSession, MaterialMaster, RegistrationOrder
from vx_materials_api.services.agent_client import AgentClient

ATTRIBUTES = {
    "FABRICANTE": "FLSMIDTH",
    "REFERENCIA FABRICANTE": "VX136001",
    "APLICACAO": "BRITADOR CONICO",
    "MODELO EQUIPAMENTO": "RAPTOR 450",
}


def ready_agent(catalog):
    agent = FakeAgent()
    validation = validate_pdm(catalog, "PDM110", ATTRIBUTES, item_name="BUCHA")
    assert validation.can_submit
    agent.result = {
        "assistant_message": "Ficha pronta para envio.",
        "tool_calls": [
            {
                "id": "search",
                "name": "search_similar_materials",
                "transport": "MCP_STDIO",
                "input": {},
                "status": "SUCCEEDED",
                "result": {"candidates": []},
            }
        ],
        "context_patch": {"item_name": "BUCHA", "confirmed_attributes": ATTRIBUTES},
        "material_card": {
            "pdm_class_id": "PDM110",
            "attributes": ATTRIBUTES,
            "pdm_description": validation.formatted_description,
            "validation_status": "VALID",
            "missing_attributes": [],
            "ncm": {"suggested": None, "status": "PENDING_VALIDATION"},
            "duplicate_check_status": "NO_MATCH",
            "can_submit": True,
        },
    }
    return agent, validation


def index_current_catalog(db, catalog, version):
    """Índice real na transação do teste; a suíte completa pode deixar materiais de outras fixtures."""
    from pipelines.search_index import analyze_source, search_text
    from repositories.batch_repository import read_search_sources, write_search_index
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    connection = db.connection()
    engine = SimpleNamespace(connect=lambda: nullcontext(connection), begin=lambda: nullcontext(connection))
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    rows = []
    for source in read_search_sources(engine, str(TENANT_ID), version, only_stale=True):
        analyzed = analyze_source(source, catalog, classifier, extractor)
        rows.append(
            {
                "material_id": source.record.database_id,
                "source_version": source.record.version,
                "proposed_class_id": analyzed.pdm_class_id,
                "extracted_attributes": analyzed.attributes,
                "search_text": search_text(analyzed),
                "candidate_identity_key": analyzed.identity_key,
                "embedding": None,
                "embedding_model": None,
            }
        )
    write_search_index(engine, str(TENANT_ID), version, rows)


@pytest.fixture
def ready(case, monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", "test-only-chat-submit-secret-with-32-bytes")
    client, db, version = case
    index_current_catalog(db, client.app.state.pdm_catalog, version)
    index(db, version, material(db, "90000001"), "PDM999|OUTRO")
    agent, validation = ready_agent(client.app.state.pdm_catalog)
    client.app.state.agent_client = AgentClient("http://agent", transport=httpx.MockTransport(agent))
    me = login(client, "SOLICITANTE_OPERACAO")
    # O texto inicial difere da ficha final: a publicação deve preservar o que foi confirmado.
    response = client.post(
        "/api/v1/chat/message",
        headers=headers(me),
        json={
            "session_id": None,
            "expected_session_version": 0,
            "client_message_id": str(uuid.uuid4()),
            "message": "Preciso de BUCHA, a referência anterior estava errada; confirmo VX136001.",
            "center_code": "1200",
        },
    )
    assert response.status_code == 200, response.text
    turn = response.json()
    assert turn["status"] == "READY_TO_SUBMIT"
    return client, db, me, turn, validation.identity_key


def submit(ready, *, version=None, key=None, extra=None):
    client, _, me, turn, _ = ready
    return client.post(
        f"/api/v1/chat/{turn['session_id']}/submit",
        headers=headers(me, key),
        json={
            "expected_session_version": turn["session_version"] if version is None else version,
            **(extra or {}),
        },
    )


def test_chat_submission_lists_for_owner_and_governance_and_requires_both_approvals(ready):
    client, db, _, turn, identity_key = ready
    before = db.scalar(select(func.count()).select_from(MaterialMaster))
    response = submit(ready)
    assert response.status_code == 200, response.text
    body = response.json()
    validator({"$ref": "#/components/schemas/ChatSubmitResponse"}).validate(body)
    assert body["status"] == "READY_FOR_REVIEW" and body["session_version"] == turn["session_version"] + 1
    restored = client.get(f"/api/v1/chat/sessions/{turn['session_id']}").json()
    assert restored["submission"] == body
    assert restored["order_id"] == body["order_id"]
    assert restored["session_version"] == body["session_version"]
    assert db.scalar(select(func.count()).select_from(MaterialMaster)) == before
    order = db.get(RegistrationOrder, uuid.UUID(body["order_id"]))
    session = db.get(ChatSession, uuid.UUID(turn["session_id"]))
    assert order.requester_user_id == session.owner_user_id and session.registration_order_id == order.id
    assert order.attributes == ATTRIBUTES and order.item_name == "BUCHA" and order.center_code == "1200"
    assert client.get("/api/v1/registration-orders").json()["items"][0]["id"] == body["order_id"]
    event = db.scalar(select(AuditLog).where(AuditLog.entity_id == str(order.id)))
    assert event.action == "ORDER_SUBMITTED" and event.actor_user_id == session.owner_user_id
    assert event.before_json["session_id"] == turn["session_id"] and event.request_id
    governance = login(client, "GESTOR_CADASTRO")
    assert client.get("/api/v1/registration-orders?status=READY_FOR_REVIEW").json()["items"][0]["id"] == str(order.id)
    assert decide(client, governance, order.id, 1).json()["status"] == "PENDING_FISCAL"
    fiscal = login(client, "AUDITOR_FISCAL")
    assert decide(client, fiscal, order.id, 2).json()["status"] == "REGISTERED"
    db.expire_all()
    created = db.scalar(select(MaterialMaster).where(MaterialMaster.identity_key == identity_key))
    assert created and created.attributes == ATTRIBUTES and created.ncm_review_status == "APPROVED"
    assert created.original_description_long == order.original_text


def test_retries_with_same_or_new_key_do_not_duplicate_and_keys_bind_the_payload(ready):
    _, db, _, _, _ = ready
    key = str(uuid.uuid4())
    first = submit(ready, key=key)
    assert first.status_code == 200, first.text
    assert submit(ready, key=key).json() == first.json()
    assert submit(ready).json() == first.json()
    assert submit(ready, key=key, version=5).status_code == 409
    assert submit(ready, version=5).status_code == 409
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


@pytest.mark.parametrize(
    "change,code",
    [
        ("incomplete", "CHAT_NOT_READY"),
        ("invalid", "PDM_INVALID"),
        ("changed_signature", "CHAT_NOT_READY"),
        ("similar", "CHAT_NOT_READY"),
        ("active", "TURN_IN_PROGRESS"),
        ("center", "FORBIDDEN"),
    ],
)
def test_submission_rechecks_saved_state_and_current_domain(ready, change, code):
    _, db, _, turn, _ = ready
    session = db.get(ChatSession, uuid.UUID(turn["session_id"]))
    context = dict(session.context)
    if change == "incomplete":
        context["material_card"] = {**context["material_card"], "validation_status": "INCOMPLETE"}
    elif change == "invalid":
        context["material_card"]["attributes"]["FABRICANTE"] = ""
        context["duplicate_check"]["signature"] = identity_signature(
            "PDM110", context["material_card"].get("pdm_class_name"), context["material_card"]["attributes"]
        )
    elif change == "changed_signature":
        context["material_card"]["attributes"]["FABRICANTE"] = "SKF"
    elif change == "similar":
        context["duplicate_check"]["candidates"] = [{"material_code": "123", "status": "ATIVO"}]
    elif change == "center":
        context["center_code"] = "9999"
    else:
        session.active_turn_id = uuid.uuid4()
    session.context = context
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(session, "context")
    db.commit()
    result = submit(ready)
    assert result.status_code in {403, 409, 422}, result.text
    assert result.json()["error"]["code"] == code
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0


def test_changed_version_and_forged_payload_are_refused(ready):
    assert submit(ready, version=9).status_code == 409
    for field in ("attributes", "role", "actor_id", "can_submit", "center_code"):
        assert submit(ready, extra={field: "forged"}).status_code == 422


def test_duplicate_created_after_chat_is_not_forwarded_for_new_registration(ready):
    _, db, _, _, identity_key = ready
    from test_orders import set_current_identity

    from pipelines.import_orders import OrderAnalysis

    catalog = ready[0].app.state.pdm_catalog
    analysis = OrderAnalysis(
        "READY_FOR_REVIEW",
        "PDM110",
        "BUCHA",
        ATTRIBUTES,
        (),
        identity_key,
        validate_pdm(catalog, "PDM110", ATTRIBUTES, item_name="BUCHA").formatted_description,
    )
    rival = set_current_identity(material(db, "80000001", identity=identity_key, canonical=True), analysis)
    db.commit()
    response = submit(ready)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "EXISTING"
    order = db.get(RegistrationOrder, uuid.UUID(response.json()["order_id"]))
    assert order.candidate_material_ids == [str(rival.id)] and order.material_id is None


def test_other_owner_csrf_and_missing_index_are_refused(ready):
    client, db, me, turn, _ = ready
    path = f"/api/v1/chat/{turn['session_id']}/submit"
    body = {"expected_session_version": turn["session_version"]}
    assert client.post(path, json=body, headers={"Idempotency-Key": str(uuid.uuid4())}).status_code == 403
    assert client.post(path, json=body, headers={**headers(me), "Origin": "https://other.example"}).status_code == 403
    login(client, "GESTOR_CADASTRO")
    assert client.post(path, json=body, headers=headers(login(client, "GESTOR_CADASTRO"))).status_code == 404
    me = login(client, "SOLICITANTE_OPERACAO")
    ready = (client, db, me, turn, ready[4])
    from sqlalchemy import delete

    from vx_materials_api.db.models import MaterialSearchIndex

    db.execute(delete(MaterialSearchIndex))
    db.commit()
    response = submit(ready)
    assert response.status_code == 503 and response.json()["error"]["code"] == "SEARCH_INDEX_MISSING"


def test_audit_failure_rolls_back_order_link_and_idempotency(ready, monkeypatch):
    _, db, _, turn, _ = ready
    from vx_materials_api.services import order_service

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(order_service, "_audit", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        submit(ready)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(RegistrationOrder)) == 0
    assert db.get(ChatSession, uuid.UUID(turn["session_id"])).registration_order_id is None


def test_current_pdm_is_revalidated_before_creating_the_order(ready):
    from dataclasses import replace

    client = ready[0]
    catalog = client.app.state.pdm_catalog
    pdm_class = catalog.classes["PDM110"]
    changed = replace(
        pdm_class,
        attributes=tuple(
            replace(attribute, required=True) if attribute.name == "MATERIAL" else attribute
            for attribute in pdm_class.attributes
        ),
    )
    client.app.state.pdm_catalog = replace(catalog, classes={**catalog.classes, "PDM110": changed})
    response = submit(ready)
    assert response.status_code == 422 and response.json()["error"]["code"] == "PDM_INVALID"


def test_submitted_conversation_cannot_silently_change_the_order(ready):
    response = submit(ready)
    assert response.status_code == 200
    client, _, me, turn, _ = ready
    response = client.post(
        "/api/v1/chat/message",
        headers=headers(me),
        json={
            "session_id": turn["session_id"],
            "expected_session_version": response.json()["session_version"],
            "client_message_id": str(uuid.uuid4()),
            "message": "Trocar a referência",
            "center_code": "1200",
        },
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "CHAT_ALREADY_SUBMITTED"


def test_conversation_from_another_tenant_is_hidden(ready):
    _, db, _, turn, _ = ready
    session = db.get(ChatSession, uuid.UUID(turn["session_id"]))
    session.tenant_id = uuid.uuid4()
    db.commit()
    response = submit(ready)
    assert response.status_code == 404


def test_simultaneous_requests_with_different_keys_create_one_order(factory, catalog, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi.testclient import TestClient
    from sqlalchemy import delete
    from test_chat import _new_identity

    from vx_materials_api.db.models import ChatMessage, MaterialSearchIndex, OperationRequest, UserSso
    from vx_materials_api.main import create_app

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "false")
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", "test-only-chat-submit-secret-with-32-bytes")
    identity = _new_identity(factory, frozenset({"chat:use", "orders:create"}))
    agent, _ = ready_agent(catalog)
    app = create_app(
        session_factory=factory,
        identity_provider=lambda db: identity,
        agent_client=AgentClient("http://agent", transport=httpx.MockTransport(agent)),
    )
    app.state.pdm_catalog = catalog
    from vx_materials_api.services.order_service import _rules

    version = _rules(catalog)[2]
    try:
        with factory() as db:
            row = MaterialMaster(
                tenant_id=identity.tenant_id, source_system="TEST", material_code="136", status="ATIVO"
            )
            db.add(row)
            db.flush()
            db.add(MaterialSearchIndex(tenant_id=identity.tenant_id, material_id=row.id, normalization_version=version))
            db.commit()
        client = TestClient(app)
        write_headers = {"Origin": "http://localhost:8000", "X-CSRF-Token": identity.csrf_token}
        turn = client.post(
            "/api/v1/chat/message",
            headers=write_headers,
            json={
                "session_id": None,
                "expected_session_version": 0,
                "client_message_id": str(uuid.uuid4()),
                "message": "BUCHA confirmada",
                "center_code": "1200",
            },
        ).json()
        gate = Barrier(2)

        def send(_):
            gate.wait(timeout=10)
            return client.post(
                f"/api/v1/chat/{turn['session_id']}/submit",
                headers={**write_headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"expected_session_version": turn["session_version"]},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, range(2)))
        assert [result.status_code for result in results] == [200, 200]
        assert results[0].json() == results[1].json()
        with factory() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(RegistrationOrder)
                    .where(RegistrationOrder.tenant_id == identity.tenant_id)
                )
                == 1
            )
            assert (
                db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == identity.tenant_id))
                == 1
            )
    finally:
        with factory() as db:
            sessions = select(ChatSession.id).where(ChatSession.tenant_id == identity.tenant_id)
            db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(sessions)))
            for model in (ChatSession, AuditLog, RegistrationOrder, MaterialSearchIndex, MaterialMaster):
                db.execute(delete(model).where(model.tenant_id == identity.tenant_id))
            db.execute(delete(OperationRequest).where(OperationRequest.user_id == identity.user_id))
            db.execute(delete(UserSso).where(UserSso.id == identity.user_id))
            db.commit()


def test_same_reference_with_another_noun_is_submitted_for_review_without_verified_reuse(ready):
    from test_orders import index, set_current_identity

    from pipelines.import_orders import OrderAnalysis
    from vx_materials_api.services.order_service import _rules

    client, db, _, _, key = ready
    catalog = client.app.state.pdm_catalog
    candidate = OrderAnalysis(
        "READY_FOR_REVIEW",
        "PDM110",
        "RODA GUIA",
        ATTRIBUTES,
        (),
        key,
        validate_pdm(catalog, "PDM110", ATTRIBUTES, item_name="RODA GUIA").formatted_description,
    )
    rival = set_current_identity(material(db, "80000001", identity=key, canonical=True), candidate)
    index(db, _rules(catalog)[2], rival, key)
    response = submit(ready)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY_FOR_REVIEW"
    order = db.get(RegistrationOrder, uuid.UUID(response.json()["order_id"]))
    assert order.material_id is None and order.candidate_material_ids == [str(rival.id)]
    assert any("REVISAO DE IDENTIDADE" in reason for reason in order.missing_attributes)


@pytest.mark.parametrize("revision", [False, True])
def test_chat_submission_preserves_raw_identity_warning_without_reextracting_old_corrected_pn(ready, revision):
    from test_orders import index, set_current_identity

    from pipelines.import_orders import OrderAnalysis
    from vx_materials_api.db.models import ChatMessage
    from vx_materials_api.services.order_service import _rules

    client, db, _, turn, key = ready
    catalog = client.app.state.pdm_catalog
    text = "Preciso de BUCHA; PN anterior VX136000 estava errado; confirmo VX136001" + ("; REV A" if revision else "")
    message = db.scalar(
        select(ChatMessage).where(
            ChatMessage.session_id == uuid.UUID(turn["session_id"]), ChatMessage.author_type == "USER"
        )
    )
    message.content = text
    candidate = OrderAnalysis(
        "READY_FOR_REVIEW",
        "PDM110",
        "BUCHA",
        ATTRIBUTES,
        (),
        key,
        validate_pdm(catalog, "PDM110", ATTRIBUTES, item_name="BUCHA").formatted_description,
    )
    rival = set_current_identity(material(db, "80000001", identity=key, canonical=True), candidate)
    index(db, _rules(catalog)[2], rival, key)
    response = submit(ready)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ("READY_FOR_REVIEW" if revision else "EXISTING")
    order = db.get(RegistrationOrder, uuid.UUID(response.json()["order_id"]))
    assert order.original_text == text and order.attributes["REFERENCIA FABRICANTE"] == "VX136001"
    assert any("REVISAO_DE_PECA_NAO_CONFIRMADA" in reason for reason in order.missing_attributes) is revision
