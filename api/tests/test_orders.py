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
def case(order_database, connection, catalog, monkeypatch):
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
    from pipelines.import_orders import analyze_order

    analysis = analyze_order(
        kit_orders[0], client.app.state.pdm_catalog, *get_repositories(client.app.state.pdm_catalog)
    )
    existing = set_current_identity(material(db, "90000002"), analysis)
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
    from pipelines.import_orders import OrderRow, analyze_order

    row = OrderRow("rival", order.original_text, order.attachment_text, order.center_code, None)
    analysis = analyze_order(row, client.app.state.pdm_catalog, *get_repositories(client.app.state.pdm_catalog))
    rival = set_current_identity(material(db, "80000001", identity=BUCHA, canonical=True), analysis)
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
    existing.pdm_class_id = analysis.pdm_class_id
    existing.attributes = dict(analysis.attributes)
    existing.pdm_description = analysis.formatted_description
    existing.original_description_long = analysis.source_text
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


def test_complement_audits_reclassified_order(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    order.status, order.pdm_class_id = "OUT_OF_SCOPE", None
    db.commit()
    response = complement(client, login(client, "GESTOR_CADASTRO"), order)
    assert response.status_code == 200, response.text
    assert response.json()["pdm_class_id"] == "PDM001"
    audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == str(order.id)))
    assert audit.before_json["pdm_class_id"] is None
    assert audit.after_json["pdm_class_id"] == "PDM001"


def test_owner_cannot_submit_orders_after_losing_center_access(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600001"]
    me = login(client, "SOLICITANTE_OPERACAO")
    owner = db.scalar(select(UserSso).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    order.origin, order.requester_user_id, order.status = "CHAT", owner.id, "DRAFT"
    order.center_code = "9999"
    db.commit()
    assert client.get(PATH).json()["items"] == []
    response = client.post(f"{PATH}/{order.id}/submit", json={"expected_version": 1}, headers=headers(me))
    assert response.status_code in {403, 404}, response.text
    db.refresh(order)
    assert order.status == "DRAFT" and order.version == 1
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(order.id))) == 0


@pytest.mark.parametrize("revoked", [None, "role", "center", "tenant", "ownership"])
def test_complement_replay_rechecks_current_access(imported, revoked):
    from dataclasses import replace

    from vx_materials_api.schemas.orders import OrderComplementRequest
    from vx_materials_api.security.identity import Identity
    from vx_materials_api.security.permissions import permissions_for
    from vx_materials_api.services.order_service import complement_order

    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    login(client, "GESTOR_CADASTRO")
    actor = db.scalar(select(UserSso).where(UserSso.subject == "GESTOR_CADASTRO"))
    roles = tuple(actor.roles_snapshot)
    identity = Identity(actor.id, TENANT_ID, roles, permissions_for(roles), frozenset({order.center_code}))
    listed = client.get(PATH).json()["items"]
    assert next(row for row in listed if row["id"] == str(order.id))["can_complement"] is True
    payload = OrderComplementRequest(
        expected_version=1, text="BITOLA: M12", source="Desenho do fornecedor", reason="Conferido no desenho"
    )
    key = uuid.uuid4()

    def run():
        return complement_order(db, identity, client.app.state.pdm_catalog, order.id, payload, key)

    original = run()
    count = db.scalar(select(func.count()).select_from(AuditLog))
    if revoked == "role":
        identity = replace(identity, roles=(), permissions=frozenset())
    elif revoked == "center":
        identity = replace(identity, center_codes=frozenset())
    elif revoked == "tenant":
        identity = replace(identity, tenant_id=uuid.uuid4())
    elif revoked == "ownership":
        login(client, "SOLICITANTE_OPERACAO")
        order.requester_user_id = db.scalar(select(UserSso.id).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
        db.commit()
    if revoked:
        with pytest.raises(ApiProblem) as error:
            run()
        assert error.value.status in {403, 404}
    else:
        assert run() == original
    db.refresh(order)
    assert order.version == 2 and len(order.supplements) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == count


def test_review_exposes_technical_card_and_unknown_official_ncm_status(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600010"]
    login(client, "GESTOR_CADASTRO")
    result = client.get(f"{PATH}/{order.id}")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["order"]["original_text"] == order.original_text
    assert body["attachment_text"] == order.attachment_text
    assert body["attributes"] and body["formatted_description"]
    assert body["pdm_version"] and body["pdm_source_sha256"] and body["index_version"]
    assert body["ncm_references"] and body["ncm_proposed"] is None
    assert body["ncm_assessment"]["exists_in_snapshot"] is None
    assert body["ncm_assessment"]["valid_in_snapshot"] is None
    from test_contracts import validator

    validator({"$ref": "#/components/schemas/OrderReview"}).validate(body)
    login(client, "SOLICITANTE_OPERACAO")
    assert client.get(f"{PATH}/{order.id}").status_code == 404
    login(client, "GESTOR_CADASTRO")
    order.center_code = "9999"
    db.commit()
    assert client.get(f"{PATH}/{order.id}").status_code == 404


def test_explicit_fiscal_choice_publishes_exact_persisted_ncm_once(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600010"]
    assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
    me = login(client, "AUDITOR_FISCAL")
    review = client.get(f"{PATH}/{order.id}").json()
    code = review["ncm_assessment"]["suggested_ncm_codes"][0]
    payload = {
        "expected_version": 2,
        "decision": "APPROVE",
        "reason": "Condição do filtro conferida na ficha técnica",
        "ncm_code": code.replace(".", ""),
        "ncm_source": "Ficha técnica do fabricante",
        "ncm_evaluation_hash": review["ncm_assessment"]["evaluation_hash"],
    }
    key = str(uuid.uuid4())
    response = client.post(f"{PATH}/{order.id}/decide", json=payload, headers=headers(me, key))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REGISTERED"
    assert client.post(f"{PATH}/{order.id}/decide", json=payload, headers=headers(me, key)).json() == response.json()
    db.refresh(order)
    created = db.get(MaterialMaster, order.material_id)
    assert created.ncm == order.review_data["fiscal"]["ncm_code"] == code
    assert order.review_data["fiscal"]["source"] == payload["ncm_source"]
    audit = db.scalar(
        select(AuditLog).where(AuditLog.entity_id == str(order.id), AuditLog.action == "ORDER_REGISTERED")
    )
    assert audit.after_json["review_data"]["fiscal"]["assessment"]["exists_in_snapshot"] is None
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(order.id))) == 2


@pytest.mark.parametrize("invalid", ["condition", "source", "hash", "version", "role"])
def test_fiscal_choice_refuses_incompatible_or_stale_decisions(imported, invalid):
    client, db, _, _, orders = imported
    order = orders["SC-202600010"]
    governance = login(client, "GESTOR_CADASTRO")
    if invalid != "role":
        assert decide(client, governance, order.id, 1).status_code == 200
        me = login(client, "AUDITOR_FISCAL")
    else:
        me = governance
    review = client.get(f"{PATH}/{order.id}").json()
    code = review["ncm_assessment"]["suggested_ncm_codes"][0]
    payload = {
        "expected_version": 1 if invalid == "role" else 2,
        "decision": "APPROVE",
        "reason": "Conferido",
        "ncm_code": code,
        "ncm_source": "Fabricante",
        "ncm_evaluation_hash": review["ncm_assessment"]["evaluation_hash"],
    }
    if invalid == "condition":
        # Código da mesma classe, mas de outro tipo de filtro: a união de referências não basta.
        payload["ncm_code"] = next(
            code for ref in review["ncm_references"] for code in ref["codes"] if code != payload["ncm_code"]
        )
    elif invalid == "source":
        payload["ncm_source"] = None
    elif invalid == "hash":
        payload["ncm_evaluation_hash"] = "0" * 64
    elif invalid == "version":
        payload["expected_version"] = 1
    response = client.post(f"{PATH}/{order.id}/decide", json=payload, headers=headers(me))
    assert response.status_code == ({"role": 403, "hash": 409, "version": 409}.get(invalid, 422)), response.text
    db.refresh(order)
    assert order.material_id is None and "fiscal" not in order.review_data


def test_changed_structured_card_invalidates_the_technical_approval(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600010"]
    governance = login(client, "GESTOR_CADASTRO")
    owner = db.scalar(select(UserSso).where(UserSso.subject == "GESTOR_CADASTRO"))
    review = client.get(f"{PATH}/{order.id}").json()
    order.origin, order.requester_user_id, order.item_name = "CHAT", owner.id, review["item_name"]
    db.commit()
    assert decide(client, governance, order.id, 1).status_code == 200
    db.refresh(order)
    order.attributes = {**order.attributes, "REFERENCIA FABRICANTE": "OUTRA-REFERENCIA"}
    db.commit()
    me = login(client, "AUDITOR_FISCAL")
    response = client.post(
        f"{PATH}/{order.id}/decide",
        json={
            "expected_version": 2,
            "decision": "APPROVE",
            "reason": "Conferido",
            "ncm_code": review["ncm_assessment"]["suggested_ncm_codes"][0],
            "ncm_source": "Fabricante",
        },
        headers=headers(me),
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "TECHNICAL_REVIEW_CHANGED"
    db.refresh(order)
    assert order.material_id is None


def test_single_ncm_reference_is_persisted_with_the_fiscal_approval(imported):
    client, db, _, _, _ = imported
    row = next(
        row
        for row in read_orders((KIT / "02_pedidos_cadastro.csv").read_bytes())
        if row.source_order_id == "SC-202600004"
    )
    import_orders(db, TENANT_ID, client.app.state.pdm_catalog, [row])
    order = db.scalar(select(RegistrationOrder).where(RegistrationOrder.source_order_id == row.source_order_id))
    assert order.pdm_class_id == "PDM002"
    assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1).status_code == 200
    assert decide(client, login(client, "AUDITOR_FISCAL"), order.id, 2).status_code == 200
    detail = client.get(f"{PATH}/{order.id}").json()
    db.refresh(order)
    created = db.get(MaterialMaster, order.material_id)
    expected = client.app.state.pdm_catalog.classes["PDM002"].ncm_references[0].codes[0]
    assert created.ncm == detail["fiscal_decision"]["ncm_code"] == expected
    assert detail["fiscal_decision"]["assessment"]["valid_in_snapshot"] is None


def test_governance_can_recover_legacy_pending_fiscal_orders(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600001"]
    governance = login(client, "GESTOR_CADASTRO")
    assert decide(client, governance, order.id, 1).status_code == 200
    db.refresh(order)
    order.review_data = {}  # Pedido pendente fiscal anterior à nova ficha auditada.
    db.commit()
    fiscal = login(client, "AUDITOR_FISCAL")
    refused = decide(client, fiscal, order.id, 2)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "TECHNICAL_REVIEW_CHANGED"
    path = f"{PATH}/{order.id}/reopen-technical-review"
    payload = {"expected_version": 2, "reason": "Conferir ficha legada com as regras atuais"}
    assert client.post(path, json=payload, headers=headers(fiscal)).status_code == 403
    governance = login(client, "GESTOR_CADASTRO")
    assert client.post(path, json={**payload, "expected_version": 1}, headers=headers(governance)).status_code == 409
    key = str(uuid.uuid4())
    reopened = client.post(path, json=payload, headers=headers(governance, key))
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "READY_FOR_REVIEW" and reopened.json()["version"] == 3
    assert client.post(path, json=payload, headers=headers(governance, key)).json() == reopened.json()
    audit = db.scalar(
        select(AuditLog).where(AuditLog.entity_id == str(order.id), AuditLog.action == "ORDER_TECHNICAL_REOPENED")
    )
    assert audit.before_json["status"] == "PENDING_FISCAL"
    assert audit.after_json["pdm_class_id"] == "PDM110" and audit.after_json["review_data"] == {}
    assert decide(client, governance, order.id, 3).status_code == 200
    assert decide(client, login(client, "AUDITOR_FISCAL"), order.id, 4).status_code == 200
    assert (
        client.post(
            path, json={**payload, "expected_version": 5}, headers=headers(login(client, "GESTOR_CADASTRO"))
        ).status_code
        == 409
    )


def test_order_review_and_reopened_result_preserve_current_actor_complement_permission(imported):
    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    me = login(client, "GESTOR_CADASTRO")
    detail = client.get(f"{PATH}/{order.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["order"]["can_complement"] is True
    order.status = "PENDING_FISCAL"
    db.commit()
    reopened = client.post(
        f"{PATH}/{order.id}/reopen-technical-review",
        json={"expected_version": 1, "reason": "Ficha incompleta precisa de complemento"},
        headers=headers(me),
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "INCOMPLETE"
    assert reopened.json()["can_complement"] is True


@pytest.mark.parametrize("pending", ["new_material", "stale_revision", "foreign_index"])
def test_negative_duplicate_check_requires_complete_current_tenant_index(case, pending):
    from vx_materials_api.services.order_service import SearchIndexMissing, existing_materials

    client, db, version = case
    row = material(db, "90000001")
    index(db, version, row, "PDM999|OUTRO")
    if pending == "new_material":
        material(db, "90000002")
    elif pending == "stale_revision":
        row.version += 1
    else:
        db.scalar(select(MaterialSearchIndex)).tenant_id = uuid.uuid4()
    db.flush()
    with pytest.raises(SearchIndexMissing):
        existing_materials(
            db, TENANT_ID, client.app.state.pdm_catalog, complete_part_analysis(client.app.state.pdm_catalog), version
        )


def test_published_canonical_duplicate_stays_visible_while_index_update_is_pending(case):
    from vx_materials_api.services.order_service import existing_materials

    client, db, version = case
    analysis = complete_part_analysis(client.app.state.pdm_catalog)
    canonical = current_part(db, version, analysis)
    db.delete(db.scalar(select(MaterialSearchIndex).where(MaterialSearchIndex.material_id == canonical.id)))
    material(db, "90000001")
    assert existing_materials(db, TENANT_ID, client.app.state.pdm_catalog, analysis, version) == [str(canonical.id)]


def test_publication_serializes_with_material_approval_and_order_decisions(imported, monkeypatch):
    from sqlalchemy import text

    from vx_materials_api.services import order_service

    client, db, _, _, orders = imported
    order = orders["SC-202600001"]
    technical = decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1)
    assert technical.status_code == 200, technical.text
    publish = order_service._publish
    observed = False

    def locked_publish(*args):
        nonlocal observed
        with db.get_bind().engine.connect() as competing:
            for seed in (0, 1):
                assert not competing.scalar(
                    text("SELECT pg_try_advisory_xact_lock(hashtextextended(:tenant, :seed))"),
                    {"tenant": str(TENANT_ID), "seed": seed},
                ), f"A publicação não excluiu a operação concorrente do tenant (seed={seed})"
        observed = True
        return publish(*args)

    monkeypatch.setattr(order_service, "_publish", locked_publish)
    response = decide(client, login(client, "AUDITOR_FISCAL"), order.id, 2)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REGISTERED" and observed


def complete_part_analysis(catalog, noun="MANTO", reference="N1234567", manufacturer="METSO"):
    from domain.pdm_validator import validate_pdm
    from pipelines.import_orders import OrderAnalysis

    attributes = {
        "FABRICANTE": manufacturer,
        "REFERENCIA FABRICANTE": reference,
        "APLICACAO": "BRITADOR CONICO",
        "MODELO EQUIPAMENTO": "HP400",
    }
    validation = validate_pdm(catalog, "PDM110", attributes, item_name=noun)
    assert validation.can_submit
    return OrderAnalysis(
        "READY_FOR_REVIEW", "PDM110", noun, attributes, (), validation.identity_key, validation.formatted_description
    )


def set_current_identity(row, analysis):
    row.pdm_class_id = analysis.pdm_class_id
    row.attributes = analysis.attributes
    row.pdm_description = analysis.formatted_description
    row.original_description_long = analysis.formatted_description
    row.manufacturer = analysis.attributes["FABRICANTE"]
    row.manufacturer_reference = analysis.attributes["REFERENCIA FABRICANTE"]
    return row


def current_part(db, version, analysis):
    row = set_current_identity(material(db, "80000001", identity=analysis.identity_key, canonical=True), analysis)
    index(db, version, row, analysis.identity_key)
    return row


@pytest.mark.parametrize("difference", ["noun", "suffix", "attribute", "revision", "structured", "ambiguous"])
def test_order_identity_does_not_confirm_a_matching_key_with_unresolved_evidence(case, difference):
    from vx_materials_api.services.order_service import _evaluate

    client, db, version = case
    analysis = complete_part_analysis(client.app.state.pdm_catalog)
    candidate = complete_part_analysis(
        client.app.state.pdm_catalog,
        noun="CONCAVO" if difference == "noun" else "MANTO",
        reference="N1234567-00" if difference == "suffix" else "N1234567",
    )
    row = current_part(db, version, candidate)
    if difference == "attribute":
        row.attributes = {**row.attributes, "MODELO EQUIPAMENTO": "HP300"}
    elif difference == "revision":
        row.original_description_long += " REV A"
    elif difference == "structured":
        row.manufacturer_reference = "N9999999"
    elif difference == "ambiguous":
        row.pdm_description = "MANTO EIXO METSO N1234567"
    db.commit()
    result = _evaluate(db, TENANT_ID, client.app.state.pdm_catalog, analysis, version)
    assert result[0] == "READY_FOR_REVIEW"
    assert result[1] == [str(row.id)]
    assert "REVISAO DE IDENTIDADE" in ", ".join(result[2])


@pytest.mark.parametrize("difference", ["candidate_noun", "requested_revision"])
def test_order_decision_does_not_override_a_shared_identity_review(case, difference):
    client, db, version = case
    analysis = complete_part_analysis(client.app.state.pdm_catalog)
    candidate = current_part(
        db,
        version,
        complete_part_analysis(
            client.app.state.pdm_catalog, noun="CONCAVO" if difference == "candidate_noun" else "MANTO"
        ),
    )
    login(client, "SOLICITANTE_OPERACAO")
    owner = db.scalar(select(UserSso.id).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    order = RegistrationOrder(
        tenant_id=TENANT_ID,
        origin="CHAT",
        requester_user_id=owner,
        original_text=analysis.formatted_description + ("; REV A" if difference == "requested_revision" else ""),
        center_code="1100",
        status="READY_FOR_REVIEW",
        pdm_class_id=analysis.pdm_class_id,
        item_name=analysis.item_name,
        attributes=analysis.attributes,
    )
    db.add(order)
    db.commit()
    materials_before = db.scalar(select(func.count()).select_from(MaterialMaster))
    audit_before = db.scalar(select(func.count()).select_from(AuditLog))
    response = decide(client, login(client, "GESTOR_CADASTRO"), order.id, 1)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "IDENTITY_REVIEW_REQUIRED"
    assert response.json()["error"]["details"]["candidate_material_ids"] == [str(candidate.id)]
    db.refresh(order)
    assert order.status == "READY_FOR_REVIEW" and order.version == 1
    assert db.scalar(select(func.count()).select_from(MaterialMaster)) == materials_before
    assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_before


def get_repositories(catalog):
    return get_classification_repository(catalog), get_extraction_repository()


def test_real_sulzer_cover_pair_is_routed_to_identity_review(case):
    import csv

    from pipelines.import_orders import OrderRow, analyze_order
    from vx_materials_api.services.order_service import _evaluate

    client, db, version = case
    catalog = client.app.state.pdm_catalog
    with (KIT / "01_base_materiais.csv").open(encoding="utf-8-sig") as stream:
        original = {
            row["CODIGO_MATERIAL"]: row
            for row in csv.DictReader(stream)
            if row["CODIGO_MATERIAL"] in {"25187467", "21290535"}
        }
    analyses = {
        code: analyze_order(
            OrderRow(code, row["DESCRICAO_LONGA"], None, "1100", None), catalog, *get_repositories(catalog)
        )
        for code, row in original.items()
    }
    assert all(analysis.status == "READY_FOR_REVIEW" for analysis in analyses.values())
    candidate = material(db, "21290535")
    candidate.original_description_long = original["21290535"]["DESCRICAO_LONGA"]
    candidate.manufacturer = original["21290535"]["FABRICANTE"]
    candidate.manufacturer_reference = original["21290535"]["REFERENCIA_FABRICANTE"]
    index(db, version, candidate, analyses["21290535"].identity_key)
    status, candidates, reasons = _evaluate(db, TENANT_ID, catalog, analyses["25187467"], version)
    assert status == "READY_FOR_REVIEW" and candidates == [str(candidate.id)]
    assert any("SUBSTANTIVO_CONTRADIZ_REFERENCIA" in reason for reason in reasons)


def test_import_preserves_review_candidate_and_visible_identity_reason(case):
    from pipelines.import_orders import OrderRow

    client, db, version = case
    catalog = client.app.state.pdm_catalog
    requested = complete_part_analysis(catalog)
    candidate = current_part(db, version, complete_part_analysis(catalog, noun="CONCAVO"))
    imported = import_orders(
        db, TENANT_ID, catalog, [OrderRow("IDENTITY_REVIEW", requested.formatted_description, None, "1100", None)]
    )
    assert imported["by_status"] == {"READY_FOR_REVIEW": 1}
    order = db.scalar(select(RegistrationOrder).where(RegistrationOrder.source_order_id == "IDENTITY_REVIEW"))
    assert order.candidate_material_ids == [str(candidate.id)]
    login(client, "GESTOR_CADASTRO")
    row = next(item for item in client.get(PATH).json()["items"] if item["id"] == str(order.id))
    assert row["status"] == "READY_FOR_REVIEW"
    assert any("REVISAO DE IDENTIDADE" in reason for reason in row["missing_attributes"])


def test_confirmed_different_current_material_does_not_become_existing_from_an_index_key(case):
    from vx_materials_api.services.order_service import _evaluate

    client, db, version = case
    analysis = complete_part_analysis(client.app.state.pdm_catalog)
    other = complete_part_analysis(client.app.state.pdm_catalog, manufacturer="SANDVIK")
    candidate = current_part(db, version, other)
    db.scalar(
        select(MaterialSearchIndex).where(MaterialSearchIndex.material_id == candidate.id)
    ).candidate_identity_key = analysis.identity_key
    db.commit()
    status, candidates, reasons = _evaluate(db, TENANT_ID, client.app.state.pdm_catalog, analysis, version)
    assert status == "READY_FOR_REVIEW" and candidates == [] and reasons == ()


@pytest.mark.parametrize(
    "source", ["request", "attachment", "structured_chat", "structured_chat_attachment", "structured_chat_supplement"]
)
def test_requested_original_revision_cannot_become_plain_existing_material(case, source):
    from types import SimpleNamespace

    from pipelines.import_orders import OrderRow, analyze_order
    from vx_materials_api.services.order_service import _analysis, _evaluate

    client, db, version = case
    catalog = client.app.state.pdm_catalog
    plain = complete_part_analysis(catalog)
    candidate = current_part(db, version, plain)
    raw = plain.formatted_description + ("; REV A" if source in {"request", "structured_chat"} else "")
    attachment = "REV A" if source in {"attachment", "structured_chat_attachment"} else None
    if attachment:
        raw += ";"
    if source.startswith("structured_chat"):
        order = SimpleNamespace(
            origin="CHAT",
            item_name=plain.item_name,
            pdm_class_id=plain.pdm_class_id,
            attributes=plain.attributes,
            original_text=raw,
            attachment_text=attachment,
            supplements=[{"text": "REV A"}] if source == "structured_chat_supplement" else [],
        )
        analysis = _analysis(order, catalog, *get_repositories(catalog))
    else:
        analysis = analyze_order(OrderRow("REV", raw, attachment, "1100", None), catalog, *get_repositories(catalog))
    assert analysis.status == "READY_FOR_REVIEW" and analysis.identity_key == plain.identity_key
    assert "REV A" not in analysis.formatted_description
    status, candidates, reasons = _evaluate(db, TENANT_ID, catalog, analysis, version)
    assert status == "READY_FOR_REVIEW" and candidates == [str(candidate.id)]
    assert any("REVISAO_DE_PECA_NAO_CONFIRMADA" in reason for reason in reasons)


@pytest.mark.parametrize("origin", ["IMPORT", "CHAT"])
def test_combined_analysis_keeps_raw_original_attachment_and_supplement(catalog, origin):
    from types import SimpleNamespace

    from vx_materials_api.services.order_service import _analysis

    plain = complete_part_analysis(catalog)
    original = plain.formatted_description + "\nVER DESENHO"
    attachment = "Fonte original: fabricante"
    supplement = "REV A"
    order = SimpleNamespace(
        origin=origin,
        source_order_id="COMBINED",
        item_name=plain.item_name,
        pdm_class_id=plain.pdm_class_id,
        attributes=plain.attributes,
        original_text=original,
        attachment_text=attachment,
        supplements=[{"text": supplement}],
    )
    analyzed = _analysis(order, catalog, *get_repositories(catalog))
    assert analyzed.source_text == "\n".join((original, attachment, supplement))
    assert order.original_text == original and order.attachment_text == attachment
    if origin == "CHAT":
        assert analyzed.attributes == plain.attributes


def test_technical_signature_binds_raw_source_evidence(catalog):
    from dataclasses import replace

    from vx_materials_api.services.order_service import _review_signature

    plain = complete_part_analysis(catalog)
    original = replace(plain, source_text="MANTO METSO N1234567")
    revised = replace(original, source_text=original.source_text + "\nREV A")
    assert _review_signature(catalog, original, "current-rules") != _review_signature(catalog, revised, "current-rules")


def test_supplement_identity_review_survives_detail_and_reopen(case):
    client, db, version = case
    catalog = client.app.state.pdm_catalog
    plain = complete_part_analysis(catalog)
    candidate = current_part(db, version, plain)
    me = login(client, "SOLICITANTE_OPERACAO")
    owner = db.scalar(select(UserSso.id).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    order = RegistrationOrder(
        tenant_id=TENANT_ID,
        origin="CHAT",
        requester_user_id=owner,
        original_text="MANTO METSO, APLICACAO: BRITADOR CONICO, MODELO EQUIPAMENTO: HP400",
        center_code="1100",
        status="INCOMPLETE",
        pdm_class_id=plain.pdm_class_id,
        item_name=plain.item_name,
        attributes={name: value for name, value in plain.attributes.items() if name != "REFERENCIA FABRICANTE"},
        missing_attributes=["REFERENCIA FABRICANTE"],
    )
    db.add(order)
    db.commit()
    source = (order.original_text, order.attachment_text)
    result = complement(client, me, order, "REFERENCIA FABRICANTE: N1234567; REV A")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "READY_FOR_REVIEW"
    assert any("REVISAO_DE_PECA_NAO_CONFIRMADA" in value for value in result.json()["missing_attributes"])
    db.refresh(order)
    assert (order.original_text, order.attachment_text) == source
    me = login(client, "GESTOR_CADASTRO")
    detail = client.get(f"{PATH}/{order.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["candidate_material_ids"] == [str(candidate.id)]
    assert any("REVISAO_DE_PECA_NAO_CONFIRMADA" in value for value in detail.json()["order"]["missing_attributes"])
    refused = decide(client, me, order.id, 2)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "IDENTITY_REVIEW_REQUIRED"
    # A pending fiscal record must return through current identity evaluation, never a fabricated approval.
    order.status = "PENDING_FISCAL"
    db.commit()
    reopened = client.post(
        f"{PATH}/{order.id}/reopen-technical-review",
        json={"expected_version": 2, "reason": "Reavaliar evidência da revisão de peça"},
        headers=headers(me),
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "READY_FOR_REVIEW"
    assert any("REVISAO_DE_PECA_NAO_CONFIRMADA" in value for value in reopened.json()["missing_attributes"])
    db.refresh(order)
    assert order.review_data == {} and order.material_id is None


@pytest.mark.parametrize("source_changed", [False, True])
def test_supplement_to_fiscal_cycle_binds_current_source_and_rules(imported, source_changed):
    client, db, _, _, orders = imported
    order = orders["SC-202600011"]
    original = (order.original_text, order.attachment_text)
    governance = login(client, "GESTOR_CADASTRO")
    completed = complement(client, governance, order)
    assert completed.status_code == 200 and completed.json()["status"] == "READY_FOR_REVIEW"
    technical = decide(client, governance, order.id, 2)
    assert technical.status_code == 200 and technical.json()["status"] == "PENDING_FISCAL"
    db.refresh(order)
    signature = order.review_data["technical"]["signature"]
    if source_changed:
        # Simulate a concurrent source correction without changing the extracted technical attributes.
        order.supplements = [{**order.supplements[0], "text": order.supplements[0]["text"] + "; REV A"}]
        db.commit()
    fiscal = login(client, "AUDITOR_FISCAL")
    detail = client.get(f"{PATH}/{order.id}")
    assert detail.status_code == 200, detail.text
    review = detail.json()
    assert review["technical_review_current"] is (not source_changed)
    code = review["ncm_assessment"]["suggested_ncm_codes"][0]
    payload = {
        "expected_version": 3,
        "decision": "APPROVE",
        "reason": "Conferência fiscal da ficha complementada",
        "ncm_code": code,
        "ncm_source": "Referência PDM e documento do fornecedor",
        "ncm_evaluation_hash": review["ncm_assessment"]["evaluation_hash"],
    }
    key = str(uuid.uuid4())
    response = client.post(f"{PATH}/{order.id}/decide", json=payload, headers=headers(fiscal, key))
    db.refresh(order)
    assert (order.original_text, order.attachment_text) == original
    assert order.review_data["technical"]["signature"] == signature
    if source_changed:
        assert response.status_code == 422 and response.json()["error"]["code"] == "TECHNICAL_REVIEW_CHANGED"
        assert order.status == "PENDING_FISCAL" and order.material_id is None and order.version == 3
        assert "fiscal" not in order.review_data
    else:
        assert response.status_code == 200 and response.json()["status"] == "REGISTERED", response.text
        assert db.get(MaterialMaster, order.material_id).ncm == order.review_data["fiscal"]["ncm_code"] == code
        assert (
            client.post(f"{PATH}/{order.id}/decide", json=payload, headers=headers(fiscal, key)).json()
            == response.json()
        )
        actions = list(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(order.id))))
        assert sorted(actions) == sorted(["ORDER_COMPLEMENTED", "ORDER_APPROVED_TECHNICAL", "ORDER_REGISTERED"])


def test_published_supplement_evidence_remains_in_current_index_identity_lookup(imported):
    from dataclasses import replace

    from vx_materials_api.services.order_service import IdentityReviewRequired, _evaluate, existing_materials

    client, db, version, _, _ = imported
    catalog = client.app.state.pdm_catalog
    plain = complete_part_analysis(catalog)
    plain = replace(plain, source_text=plain.formatted_description)
    me = login(client, "SOLICITANTE_OPERACAO")
    owner = db.scalar(select(UserSso.id).where(UserSso.subject == "SOLICITANTE_OPERACAO"))
    original = "MANTO METSO; APLICACAO: BRITADOR CONICO; MODELO EQUIPAMENTO: HP400"
    attachment = "Documento original do fornecedor"
    order = RegistrationOrder(
        tenant_id=TENANT_ID,
        origin="CHAT",
        requester_user_id=owner,
        original_text=original,
        attachment_text=attachment,
        center_code="1100",
        status="INCOMPLETE",
        pdm_class_id=plain.pdm_class_id,
        item_name=plain.item_name,
        attributes={k: v for k, v in plain.attributes.items() if k != "REFERENCIA FABRICANTE"},
        missing_attributes=["REFERENCIA FABRICANTE"],
    )
    db.add(order)
    db.commit()
    raw_supplement = "REFERENCIA FABRICANTE: N1234567; REV A"
    filled = complement(client, me, order, raw_supplement)
    assert filled.status_code == 200 and filled.json()["status"] == "READY_FOR_REVIEW"
    assert decide(client, login(client, "GESTOR_CADASTRO"), order.id, 2).status_code == 200
    fiscal = login(client, "AUDITOR_FISCAL")
    review = client.get(f"{PATH}/{order.id}").json()
    response = client.post(
        f"{PATH}/{order.id}/decide",
        json={
            "expected_version": 3,
            "decision": "APPROVE",
            "reason": "Referência fiscal conferida",
            "ncm_code": review["ncm_assessment"]["suggested_ncm_codes"][0],
            "ncm_source": "Documento fiscal do fornecedor",
            "ncm_evaluation_hash": review["ncm_assessment"]["evaluation_hash"],
        },
        headers=headers(fiscal),
    )
    assert response.status_code == 200 and response.json()["status"] == "REGISTERED", response.text
    db.refresh(order)
    published = db.get(MaterialMaster, order.material_id)
    assert (order.original_text, order.attachment_text) == (original, attachment)
    assert order.supplements[0]["text"] == raw_supplement
    # This is a derived, ordered concatenation of separately retained source records, not a corrected description.
    assert published.original_description_long == "\n".join((original, attachment, raw_supplement))
    index(db, version, published, published.identity_key)
    # Query the actual current SQL index/master join and shared identity decision after publication.
    with pytest.raises(IdentityReviewRequired):
        existing_materials(db, TENANT_ID, catalog, plain, version)
    state, candidates, reasons = _evaluate(db, TENANT_ID, catalog, plain, version)
    assert state == "READY_FOR_REVIEW" and candidates == [str(published.id)]
    assert any("REVISAO_DE_PECA_NAO_CONFIRMADA" in value for value in reasons)
