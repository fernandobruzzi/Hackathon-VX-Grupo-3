"""Papéis e escopos reais da aplicação; o navegador não concede permissões."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import ChatSession
from vx_materials_api.errors import ApiProblem
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import ROLE_PERMISSIONS, permissions_for
from vx_materials_api.security.rbac import (
    effective_permissions,
    has_permission,
    require_permission,
    require_resource_scope,
)
from vx_materials_api.services.agent_client import AgentClient

EXPECTED = {
    "ROLE_SOLICITANTE": {
        "chat:use",
        "materials:read",
        "inventory:read",
        "orders:create",
        "orders:read_own",
        "orders:update_own",
        "audit:own",
    },
    "ROLE_GOVERNANCA_PDM": {
        "chat:use",
        "materials:read",
        "inventory:read",
        "orders:create",
        "orders:read_own",
        "orders:update_own",
        "orders:decide",
        "queue:read",
        "merge:decide",
        "enrichment:decide",
        "batch:run",
        "metrics:quality",
        "audit:technical",
    },
    "ROLE_AUDITOR_FISCAL": {
        "chat:use",
        "materials:read",
        "inventory:read",
        "orders:create",
        "orders:read_own",
        "orders:update_own",
        "queue:read_audit",
        "ncm:decide",
        "metrics:quality",
        "metrics:financial",
        "audit:fiscal",
    },
    "ROLE_DEV_TI": {
        "chat:use",
        "materials:read",
        "inventory:read",
        "orders:create",
        "orders:read_own",
        "orders:update_own",
        "chat:diagnostics",
    },
}


def test_permissions_cover_the_public_contract():
    spec = json.loads((Path(__file__).parents[1] / "contracts/openapi.json").read_text())
    assert set(ROLE_PERMISSIONS) == set(spec["components"]["schemas"]["Role"]["enum"])
    assert set().union(*ROLE_PERMISSIONS.values()) == set(spec["components"]["schemas"]["Permission"]["enum"])


@pytest.mark.parametrize("role", EXPECTED)
@pytest.mark.parametrize("permission", sorted(set().union(*EXPECTED.values())))
def test_complete_role_matrix(role, permission):
    identity = Identity(uuid4(), uuid4(), (role,), permissions_for((role,)))
    if permission in EXPECTED[role]:
        assert require_permission(identity, permission) == role
    else:
        with pytest.raises(ApiProblem) as error:
            require_permission(identity, permission)
        assert error.value.status == 403


def test_dev_ti_only_adds_diagnostics_to_the_requester_basics():
    # Diagnóstico não concede aprovação, publicação, auditoria, métricas ou execução de batch.
    assert ROLE_PERMISSIONS["ROLE_DEV_TI"] - ROLE_PERMISSIONS["ROLE_SOLICITANTE"] == {"chat:diagnostics"}
    assert all("chat:diagnostics" not in perms for role, perms in ROLE_PERMISSIONS.items() if role != "ROLE_DEV_TI")


def test_permission_claim_without_authorized_role_is_insufficient():
    identity = Identity(uuid4(), uuid4(), ("administrator",), frozenset({"merge:decide"}))
    assert not has_permission(identity, "merge:decide")
    with pytest.raises(ApiProblem):
        require_permission(identity, "merge:decide")


def test_internal_permissions_cannot_exceed_the_users_role():
    identity = Identity(uuid4(), uuid4(), ("ROLE_SOLICITANTE",), frozenset({"chat:use", "metrics:financial"}))
    assert effective_permissions(identity) == {"chat:use"}


def test_both_tenant_and_all_centers_must_be_authorized():
    identity = SimpleNamespace(tenant_id=uuid4(), center_codes={"1100"})
    require_resource_scope(identity, identity.tenant_id, ["1100"])
    for tenant, centers in [(uuid4(), ["1100"]), (identity.tenant_id, ["1100", "1200"])]:
        with pytest.raises(ApiProblem) as error:
            require_resource_scope(identity, tenant, centers)
        assert error.value.status == 404


@pytest.fixture
def local_browser(connection, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")

    def factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    def unexpected_agent_call(request):
        pytest.fail("Acesso recusado não pode chegar ao Agent")

    app = create_app(
        session_factory=factory,
        agent_client=AgentClient("http://agent", transport=httpx.MockTransport(unexpected_agent_call)),
    )
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client, factory


def local_login(client, persona):
    response = client.post(
        "/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": "http://localhost:8000"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def chat_request(client, me, session_id=None, **headers):
    return client.post(
        "/api/v1/chat/message",
        json={
            "session_id": str(session_id) if session_id else None,
            "client_message_id": str(uuid4()),
            "expected_session_version": 1 if session_id else 0,
            "message": "Mensagem privada",
            "center_code": "1100",
        },
        headers={
            "Origin": "http://localhost:8000",
            "X-CSRF-Token": me["csrf_token"],
            "Idempotency-Key": str(uuid4()),
            **headers,
        },
    )


@pytest.mark.parametrize("cross_tenant", [False, True])
def test_governance_cannot_access_conversation_by_knowing_its_uuid(local_browser, cross_tenant):
    client, factory = local_browser
    owner = local_login(client, "SOLICITANTE_OPERACAO")
    session_id = uuid4()
    with factory() as db:
        db.add(
            ChatSession(
                id=session_id,
                tenant_id=uuid4() if cross_tenant else TENANT_ID,
                owner_user_id=UUID(owner["user"]["id"]),
                status="NEEDS_INPUT",
                context={},
            )
        )
        db.commit()
    governance = local_login(client, "GESTOR_CADASTRO")
    response = chat_request(client, governance, session_id, **{"X-Role": "ROLE_SOLICITANTE"})
    assert response.status_code == 404
    assert "Mensagem privada" not in response.text


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.test"},
        {"X-CSRF-Token": ""},
        {"X-CSRF-Token": "wrong", "Authorization": "Bearer forged"},
    ],
)
def test_chat_cookie_writes_check_origin_and_csrf(local_browser, headers):
    client, _ = local_browser
    me = local_login(client, "SOLICITANTE_OPERACAO")
    assert chat_request(client, me, **headers).status_code == 403
