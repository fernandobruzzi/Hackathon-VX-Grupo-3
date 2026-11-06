"""Pedidos de cadastro com sessão local real e banco real (#24)."""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from domain.pdm_loader import load_pdm
from pipelines.import_orders import read_orders
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import (
    AuditLog,
    MaterialMaster,
    MaterialSearchIndex,
    RegistrationOrder,
    UserSso,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.main import create_app
from vx_materials_api.services.order_service import import_orders

KIT = Path(__file__).parents[2] / "data" / "desafio01"
ORIGIN = "http://localhost:8000"
PATH = "/api/v1/registration-orders"
# Pronto (PDM110, aplicação BRITADOR CONICO), incompleto (sem bitola), fora de escopo (cadeira)
# e filtro pronto cuja classe tem quatro NCMs possíveis.
CODES = ("SC-202600001", "SC-202600011", "SC-202600021", "SC-202600010")
BUCHA = "PDM110|FLSMIDTH|1626003064"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def kit_orders():
    rows = {row.source_order_id: row for row in read_orders((KIT / "02_pedidos_cadastro.csv").read_bytes())}
    return [rows[code] for code in CODES]


@pytest.fixture
def case(connection, catalog, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    version = index_version(catalog, get_classification_repository(catalog), get_extraction_repository())
    app = create_app(session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"))
    app.state.pdm_catalog = catalog
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, db, version
    db.close()


def material(db, code, *, identity=None, status="ATIVO", canonical=False):
    row = MaterialMaster(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        source_system="ERP",
        material_code=code,
        status=status,
        identity_key=identity,
        is_canonical=canonical,
    )
    db.add(row)
    db.flush()
    return row


def index(db, version, row, identity=None):
    db.add(
        MaterialSearchIndex(
            tenant_id=TENANT_ID, material_id=row.id, normalization_version=version, candidate_identity_key=identity
        )
    )
    db.commit()


@pytest.fixture
def imported(case, kit_orders):
    client, db, version = case
    index(db, version, material(db, "90000001"), "PDM999|OUTRO")
    result = import_orders(db, TENANT_ID, client.app.state.pdm_catalog, kit_orders)
    orders = {
        o.source_order_id: o
        for o in db.scalars(select(RegistrationOrder).where(RegistrationOrder.tenant_id == TENANT_ID))
    }
    return client, db, version, result, orders


def login(client, persona):
    response = client.post("/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()


def headers(me, key=None):
    return {"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": key or str(uuid.uuid4())}


def decide(client, me, order_id, version, decision="APPROVE", key=None):
    return client.post(
        f"{PATH}/{order_id}/decide",
        json={"expected_version": version, "decision": decision, "reason": "Conferido no teste."},
        headers=headers(me, key),
    )


def test_import_needs_the_search_index(case, kit_orders):
    client, db, _ = case
    with pytest.raises(ApiProblem) as error:
        import_orders(db, TENANT_ID, client.app.state.pdm_catalog, kit_orders)
    assert error.value.code == "SEARCH_INDEX_MISSING"


def test_import_distinguishes_statuses_and_repeats_nothing(imported, kit_orders):
    client, db, _, result, orders = imported
    assert result["inserted"] == 4
    assert result["by_status"] == {"INCOMPLETE": 1, "OUT_OF_SCOPE": 1, "READY_FOR_REVIEW": 2}
    assert {o.origin for o in orders.values()} == {"IMPORT"}
    assert all(o.requester_user_id is None for o in orders.values())
    assert orders["SC-202600011"].missing_attributes == ["BITOLA"]
    assert import_orders(db, TENANT_ID, client.app.state.pdm_catalog, kit_orders)["inserted"] == 0


def test_import_marks_orders_that_already_exist(case, kit_orders):
    client, db, version = case
    existing = material(db, "90000002")
    index(db, version, existing, BUCHA)
    result = import_orders(db, TENANT_ID, client.app.state.pdm_catalog, kit_orders)
    assert result["by_status"]["EXISTING"] == 1
    order = db.scalar(select(RegistrationOrder).where(RegistrationOrder.source_order_id == "SC-202600001"))
    assert order.candidate_material_ids == [str(existing.id)]


def test_only_reviewers_see_imported_orders(imported):
    client, *_ = imported
    login(client, "SOLICITANTE_OPERACAO")
    assert client.get(PATH).json()["items"] == []
    login(client, "GESTOR_CADASTRO")
    items = client.get(PATH).json()["items"]
    assert len(items) == 4 and {item["requester"] for item in items} == {None}
    from test_contracts import validator

    validator({"$ref": "#/components/schemas/OrderList"}).validate(client.get(PATH).json())
    login(client, "AUDITOR_FISCAL")
    assert client.get(PATH).json()["items"] == []  # Nada aguarda o Fiscal ainda.


def test_technical_then_fiscal_approval_publishes_the_material(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600001"]
    governance = login(client, "GESTOR_CADASTRO")
    technical = decide(client, governance, order.id, 1)
    assert technical.status_code == 200, technical.text
    assert technical.json()["status"] == "PENDING_FISCAL" and technical.json()["material_code"] is None
    assert decide(client, governance, order.id, 2).status_code == 403  # Governança não publica sozinha.
    fiscal = login(client, "AUDITOR_FISCAL")
    published = decide(client, fiscal, order.id, 2)
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["status"] == "REGISTERED" and body["material_code"] == "90000002"
    created = db.scalar(select(MaterialMaster).where(MaterialMaster.material_code == "90000002"))
    assert (created.status, created.is_canonical, created.identity_key) == ("ATIVO", True, BUCHA)
    assert (created.ncm, created.ncm_review_status, created.unit) == ("8474.90.00", "APPROVED", "PC")
    assert created.original_description_long == order.original_text
    # No teste, tudo roda numa só transação externa: now() é igual nos dois eventos, então a ordem
    # por created_at depende da posição física das linhas. A sequência já foi verificada pelas respostas.
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(order.id))).all()
    assert sorted(actions) == ["ORDER_APPROVED_TECHNICAL", "ORDER_REGISTERED"]


def test_duplicate_found_before_publishing_stops_the_order(imported):
    client, db, version, _, orders = imported
    order = orders["SC-202600001"]
    governance = login(client, "GESTOR_CADASTRO")
    assert decide(client, governance, order.id, 1).status_code == 200
    rival = material(db, "80000001", identity=BUCHA, canonical=True)
    db.commit()
    fiscal = login(client, "AUDITOR_FISCAL")
    response = decide(client, fiscal, order.id, 2)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "EXISTING" and response.json()["material_code"] is None
    db.refresh(order)
    assert order.candidate_material_ids == [str(rival.id)]
    assert db.scalar(select(func.count()).select_from(MaterialMaster).where(MaterialMaster.identity_key == BUCHA)) == 1


def test_class_with_several_ncms_is_not_published(imported):
    client, _, _, _, orders = imported
    order = orders["SC-202600010"]
    assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
    response = decide(client, login(client, "AUDITOR_FISCAL"), order.id, 2)
    assert response.status_code == 422 and response.json()["error"]["code"] == "NCM_UNDETERMINED"


def test_rejection_ends_the_order_and_versions_are_checked(imported):
    client, _, _, _, orders = imported
    governance = login(client, "GESTOR_CADASTRO")
    order = orders["SC-202600001"]
    assert decide(client, governance, order.id, 7).status_code == 409
    rejected = decide(client, governance, order.id, 1, "REJECT")
    assert rejected.json()["status"] == "REJECTED"
    assert decide(client, governance, order.id, 2).status_code == 409
    incomplete = orders["SC-202600011"]
    assert decide(client, governance, incomplete.id, 1).status_code == 409


def test_decision_is_idempotent(imported):
    client, _, _, _, orders = imported
    governance = login(client, "GESTOR_CADASTRO")
    key = str(uuid.uuid4())
    order = orders["SC-202600001"]
    first = decide(client, governance, order.id, 1, key=key)
    again = decide(client, governance, order.id, 1, key=key)
    assert first.status_code == again.status_code == 200 and first.json() == again.json()
    conflict = decide(client, governance, order.id, 1, "REJECT", key=key)
    assert conflict.status_code == 409


def test_writes_require_csrf_and_requester_cannot_decide(imported):
    client, _, _, _, orders = imported
    order = orders["SC-202600001"]
    governance = login(client, "GESTOR_CADASTRO")
    response = client.post(
        f"{PATH}/{order.id}/decide",
        json={"expected_version": 1, "decision": "APPROVE", "reason": "x"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 403
    assert governance
    requester = login(client, "SOLICITANTE_OPERACAO")
    assert decide(client, requester, order.id, 1).status_code == 404


def test_owner_submits_draft_and_others_cannot(case, kit_orders):
    client, db, version = case
    index(db, version, material(db, "90000001"), "PDM999|OUTRO")
    me = login(client, "SOLICITANTE_OPERACAO")
    owner = db.scalar(select(UserSso).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    draft = RegistrationOrder(
        tenant_id=TENANT_ID,
        origin="CHAT",
        requester_user_id=owner.id,
        original_text=kit_orders[0].original_text,
        center_code="1300",
        status="DRAFT",
    )
    db.add(draft)
    db.commit()
    submitted = client.post(f"{PATH}/{draft.id}/submit", json={"expected_version": 1}, headers=headers(me))
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["status"] == "READY_FOR_REVIEW" and body["pdm_class_id"] == "PDM110" and body["version"] == 2
    assert body["requester"] == owner.display_name
    assert client.get(PATH).json()["items"][0]["id"] == str(draft.id)
    again = client.post(f"{PATH}/{draft.id}/submit", json={"expected_version": 2}, headers=headers(me))
    assert again.status_code == 409
    governance = login(client, "GESTOR_CADASTRO")
    other = client.post(f"{PATH}/{draft.id}/submit", json={"expected_version": 2}, headers=headers(governance))
    assert other.status_code == 403


@pytest.mark.parametrize("operation", ["technical", "fiscal", "submit"])
@pytest.mark.parametrize("revoked", [None, "role", "center", "tenant"])
def test_replay_rechecks_current_access(imported, operation, revoked):
    from dataclasses import replace

    from vx_materials_api.schemas.orders import OrderDecisionRequest
    from vx_materials_api.security.identity import Identity
    from vx_materials_api.security.permissions import permissions_for
    from vx_materials_api.services.order_service import decide_order, submit_order

    client, db, _, _, orders = imported
    order = orders["SC-202600001"]
    persona = "AUDITOR_FISCAL" if operation == "fiscal" else "GESTOR_CADASTRO"
    if operation == "fiscal":
        assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
    db.refresh(order)
    login(client, persona)
    actor = db.scalar(select(UserSso).where(UserSso.subject == persona))
    roles = tuple(actor.roles_snapshot)
    identity = Identity(actor.id, TENANT_ID, roles, permissions_for(roles), frozenset({order.center_code}))
    if operation == "submit":
        order.requester_user_id, order.status = actor.id, "DRAFT"
        db.commit()
    key = uuid.uuid4()
    expected = order.version

    def run(caller):
        if operation == "submit":
            return submit_order(db, caller, client.app.state.pdm_catalog, order.id, expected, key)
        return decide_order(
            db,
            caller,
            client.app.state.pdm_catalog,
            order.id,
            OrderDecisionRequest(expected_version=expected, decision="APPROVE", reason="Conferido"),
            key,
        )

    original = run(identity)
    if operation == "technical":
        assert decide(client, login(client, "AUDITOR_FISCAL"), order.id, 2).status_code == 200
        db.refresh(order)
    count = db.scalar(select(func.count()).select_from(AuditLog))
    if revoked == "role":
        identity = replace(identity, roles=(), permissions=frozenset())
    elif revoked == "center":
        identity = replace(identity, center_codes=frozenset())
    elif revoked == "tenant":
        identity = replace(identity, tenant_id=uuid.uuid4())
    if revoked:
        with pytest.raises(ApiProblem) as error:
            run(identity)
        assert error.value.status in {403, 404}
    else:
        assert run(identity) == original
    assert db.scalar(select(func.count()).select_from(AuditLog)) == count


@pytest.mark.parametrize("persona", ["GESTOR_CADASTRO", "AUDITOR_FISCAL"])
def test_rejected_decision_replays_under_its_original_role(imported, persona):
    client, db, _, _, orders = imported
    order = orders["SC-202600001"]
    if persona == "AUDITOR_FISCAL":
        assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
    me = login(client, persona)
    key = str(uuid.uuid4())
    expected = 2 if persona == "AUDITOR_FISCAL" else 1
    first = decide(client, me, order.id, expected, "REJECT", key=key)
    again = decide(client, me, order.id, expected, "REJECT", key=key)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert first.json()["status"] == "REJECTED"
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(order.id))) == expected


def test_order_pagination_filters_before_paging_and_uses_owner_ids(case):
    from datetime import UTC, datetime, timedelta

    client, db, _ = case
    governance = login(client, "GESTOR_CADASTRO")
    owner = db.scalar(select(UserSso).where(UserSso.subject == "GESTOR_CADASTRO"))
    twin = UserSso(tenant_id=TENANT_ID, issuer="test", subject="twin", display_name=owner.display_name)
    db.add(twin)
    db.flush()
    now = datetime.now(UTC)
    expected = []
    for i in range(230):
        authorized = i % 2 == 0
        row = RegistrationOrder(
            tenant_id=TENANT_ID,
            origin="CHAT",
            requester_user_id=owner.id if i >= 100 else twin.id,
            original_text=f"Pedido {i}",
            center_code="1300" if authorized else "9999",
            status="INCOMPLETE" if i % 4 == 0 else "READY_FOR_REVIEW",
            updated_at=now - timedelta(seconds=i),
        )
        db.add(row)
        db.flush()
        if authorized:
            expected.append(str(row.id))
    db.commit()

    def pages(**query):
        found, cursor = [], None
        for _ in range(250):
            response = client.get(PATH, params={"limit": 7, **query, **({"cursor": cursor} if cursor else {})})
            assert response.status_code == 200, response.text
            body = response.json()
            found.extend(item["id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                return found
        pytest.fail("A paginação não terminou")

    assert pages() == expected
    assert pages(mine="true") == expected[50:]
    assert pages(status="INCOMPLETE") == expected[::2]
    assert client.get(PATH, params={"cursor": "nope"}).status_code == 422
    assert client.get(PATH, params={"cursor": "-1"}).status_code == 422
    assert client.get(PATH, params={"cursor": "99999999999999999999"}).status_code == 422
    assert governance


def test_orders_page_is_empty_when_all_centers_are_outside_scope(case):
    client, db, _ = case
    login(client, "GESTOR_CADASTRO")
    db.add_all(
        [
            RegistrationOrder(
                tenant_id=TENANT_ID,
                origin="IMPORT",
                original_text="Fora",
                center_code="9999",
                status="READY_FOR_REVIEW",
            )
            for _ in range(30)
        ]
    )
    db.commit()
    assert client.get(PATH, params={"limit": 2}).json() == {"items": [], "next_cursor": None}


def test_order_lifecycle_is_visible_in_authorized_audit(case, kit_orders):
    client, db, version = case
    index(db, version, material(db, "90000001"), "PDM999|OUTRO")
    requester = login(client, "SOLICITANTE_OPERACAO")
    owner = db.scalar(select(UserSso).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    draft = RegistrationOrder(
        tenant_id=TENANT_ID,
        origin="CHAT",
        requester_user_id=owner.id,
        original_text=kit_orders[0].original_text,
        center_code="1300",
        status="DRAFT",
    )
    db.add(draft)
    db.commit()
    assert (
        client.post(f"{PATH}/{draft.id}/submit", json={"expected_version": 1}, headers=headers(requester)).status_code
        == 200
    )
    own = client.get("/api/v1/audit").json()["items"]
    assert [event["action"] for event in own] == ["ORDER_SUBMITTED"]
    assert own[0]["entity"] == f"pedido {draft.id}"
    assert own[0]["actor_type"] == "USER"
    assert own[0]["request_id"]
    assert own[0]["before"]["status"] == "DRAFT"
    governance = login(client, "GESTOR_CADASTRO")
    assert decide(client, governance, draft.id, 2).status_code == 200
    fiscal = login(client, "AUDITOR_FISCAL")
    assert decide(client, fiscal, draft.id, 3).status_code == 200
    events = client.get("/api/v1/audit").json()["items"]
    assert {event["action"] for event in events} == {"ORDER_SUBMITTED", "ORDER_APPROVED_TECHNICAL", "ORDER_REGISTERED"}
    assert all(event["created_at"] and event["request_id"] for event in events)
    login(client, "GESTOR_CADASTRO")
    assert "ORDER_REGISTERED" not in {event["action"] for event in client.get("/api/v1/audit").json()["items"]}
    login(client, "SOLICITANTE_OPERACAO")
    assert [event["action"] for event in client.get("/api/v1/audit").json()["items"]] == ["ORDER_SUBMITTED"]
def complement(client, me, order, text="BITOLA: M12", *, version=None, key=None):
    return client.post(
        f"{PATH}/{order.id}/complement",
        json={
            "expected_version": version or order.version,
            "text": text,
            "source": "Ficha técnica do fornecedor",
            "reason": "Bitola conferida no desenho",
        },
        headers=headers(me, key),
    )


def test_governance_complements_imported_order_without_changing_originals(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    original = (order.original_text, order.attachment_text)
    me = login(client, "GESTOR_CADASTRO")
    key = str(uuid.uuid4())
    first = complement(client, me, order, key=key)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "READY_FOR_REVIEW"
    assert first.json()["missing_attributes"] == []
    again = complement(client, me, order, version=1, key=key)
    assert again.status_code == 200 and again.json() == first.json()
    db.refresh(order)
    assert (order.original_text, order.attachment_text) == original
    assert order.requester_user_id is None and order.material_id is None
    assert order.attributes["BITOLA"] == "M12" and order.version == 2
    audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == str(order.id)))
    assert audit.action == "ORDER_COMPLEMENTED" and audit.request_id
    assert audit.before_json["missing_attributes"] == ["BITOLA"]
    assert audit.after_json["supplements"][0]["source"] == "Ficha técnica do fornecedor"
    assert audit.after_json["supplements"][0]["actor_user_id"] == str(audit.actor_user_id)
    assert complement(client, me, order).status_code == 409


@pytest.mark.parametrize("text", ["BITOLA: banana", "Informação ainda insuficiente"])
def test_insufficient_complement_keeps_order_incomplete(imported, text):
    client, _, _, _, orders = imported
    response = complement(client, login(client, "GESTOR_CADASTRO"), orders["SC-202600011"], text)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "INCOMPLETE"
    assert "BITOLA" in response.json()["missing_attributes"]


def test_complement_permissions_scope_and_versions(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    requester = login(client, "SOLICITANTE_OPERACAO")
    assert complement(client, requester, order).status_code == 404
    owner = db.scalar(select(UserSso).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    order.requester_user_id, order.origin = owner.id, "CHAT"
    db.commit()
    governance = login(client, "GESTOR_CADASTRO")
    assert complement(client, governance, order).status_code == 403
    requester = login(client, "SOLICITANTE_OPERACAO")
    assert complement(client, requester, order, version=7).status_code == 409
    order.center_code = "9999"
    db.commit()
    assert complement(client, requester, order).status_code == 404
    order.center_code = "2200"
    db.commit()
    result = complement(client, requester, order)
    assert result.status_code == 200 and result.json()["status"] == "READY_FOR_REVIEW"


def test_complement_finds_existing_identity_and_does_not_publish(imported):
    from vx_materials_api.services.order_service import _analysis, _rules

    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    order.supplements = [{"text": "BITOLA: M12"}]
    classifier, extractor, _ = _rules(client.app.state.pdm_catalog)
    analysis = _analysis(order, client.app.state.pdm_catalog, classifier, extractor)
    order.supplements = []
    existing = material(db, "90000003", identity=analysis.identity_key, canonical=True)
    db.commit()
    result = complement(client, login(client, "GESTOR_CADASTRO"), order)
    assert result.status_code == 200 and result.json()["status"] == "EXISTING"
    db.refresh(order)
    assert order.candidate_material_ids == [str(existing.id)] and order.material_id is None


def test_complement_preserves_the_confirmed_chat_card(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    requester = login(client, "SOLICITANTE_OPERACAO")
    owner = db.scalar(select(UserSso).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    order.origin, order.requester_user_id = "CHAT", owner.id
    order.item_name = "PARAFUSO SEXTAVADO"
    order.original_text = "Conversa com informações antigas já corrigidas"
    original_attributes = dict(order.attributes)
    db.commit()
    result = complement(client, requester, order)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "READY_FOR_REVIEW"
    db.refresh(order)
    assert order.attributes == {**original_attributes, "BITOLA": "M12"}
    assert order.attributes["ROSCA"] == "METRICA FINA"


@pytest.mark.parametrize("status", ["READY_FOR_REVIEW", "PENDING_FISCAL", "REGISTERED", "REJECTED", "EXISTING"])
def test_complements_cannot_reopen_reviewed_orders(imported, status):
    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    order.status = status
    db.commit()
    response = complement(client, login(client, "GESTOR_CADASTRO"), order)
    assert response.status_code == 409
    db.refresh(order)
    assert order.supplements == []
