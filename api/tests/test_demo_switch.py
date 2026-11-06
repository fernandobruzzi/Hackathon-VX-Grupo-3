"""Troca rápida de persona entre sessões Cognito reais do mesmo navegador (#8)."""

import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_auth import oidc, signing_key  # noqa: F401 - fixtures compartilhadas

from vx_materials_api.db.models import AuditLog, AuthSession
from vx_materials_api.main import create_app
from vx_materials_api.security.sessions import CONTEXT_COOKIE, SESSION_COOKIE, digest

ORIGIN = "https://app.test"
ACCOUNTS = {
    "SOLICITANTE_OPERACAO": ("op-sub", "op@demo.test", "ROLE_SOLICITANTE"),
    "GESTOR_CADASTRO": ("gov-sub", "gov@demo.test", "ROLE_GOVERNANCA_PDM"),
    "AUDITOR_FISCAL": ("fiscal-sub", "fiscal@demo.test", "ROLE_AUDITOR_FISCAL"),
}
SWITCH = "/api/v1/auth/demo/switch"


@pytest.fixture
def demo(connection, oidc, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_ACCOUNTS", ",".join(f"{p}={email}" for p, (_, email, _) in ACCOUNTS.items()))
    config, cognito, token = oidc

    def factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    app = create_app(session_factory=factory, cognito_config=config, cognito_client=cognito)
    client = TestClient(app, base_url=ORIGIN)

    def login(persona, *, email=None, group=None):
        sub, default_email, role = ACCOUNTS[persona]
        start = client.get("/api/v1/auth/sso-start", params={"prompt": "login"}, follow_redirects=False)
        query = parse_qs(urlsplit(start.headers["location"]).query)
        assert query["prompt"] == ["login"]
        groups = [group or role]
        issued = {
            "access_token": token(sub=sub, **{"cognito:groups": groups}),
            "id_token": token("id", sub=sub, nonce=query["nonce"][0], email=email or default_email, name=persona),
            "token_type": "Bearer",
        }
        cognito.transport = httpx.MockTransport(lambda request: httpx.Response(200, json=issued))
        response = client.post(
            "/api/v1/auth/sso-callback",
            headers={"Origin": ORIGIN},
            json={"code": "code-" + persona, "state": query["state"][0]},
        )
        assert response.status_code == 200, response.text
        return client.get("/api/v1/auth/me").json()

    yield client, login, factory
    client.close()


def switch(client, me, handle, **headers):
    return client.post(
        SWITCH,
        json={"session_handle": handle},
        headers={"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], **headers},
    )


def test_switch_changes_the_authenticated_session_and_audit_actor(demo):
    client, login, factory = demo
    fiscal = login("AUDITOR_FISCAL")
    governance = login("GESTOR_CADASTRO")
    assert governance["demo"] == {"enabled": True, "active_persona": "GESTOR_CADASTRO"}
    response = switch(client, governance, "AUDITOR_FISCAL")
    assert response.status_code == 200, response.text
    switched = response.json()
    assert switched["user"]["id"] == fiscal["user"]["id"]
    assert switched["user"]["roles"] == ["ROLE_AUDITOR_FISCAL"]
    assert switched["csrf_token"] == fiscal["csrf_token"] != governance["csrf_token"]
    me = client.get("/api/v1/auth/me").json()
    assert me["user"]["id"] == fiscal["user"]["id"] and me["demo"]["active_persona"] == "AUDITOR_FISCAL"


def test_approval_after_switching_is_audited_with_the_real_user(demo):
    from approval_fixtures import seed_case

    from vx_materials_api.bootstrap import TENANT_ID

    client, login, factory = demo
    with factory() as db:
        catalog, *_, proposal, _ = seed_case(db, TENANT_ID)
        proposal_id = proposal.id
    client.app.state.pdm_catalog = catalog
    governance = login("GESTOR_CADASTRO")
    fiscal = login("AUDITOR_FISCAL")
    me = switch(client, fiscal, "GESTOR_CADASTRO").json()
    response = client.post(
        f"/api/v1/sanitization/{proposal_id}/decide",
        json={
            "expected_version": 1,
            "review_area": "TECHNICAL",
            "decision": "APPROVE",
            "reason": "Conferido depois da troca de persona.",
            "primary_material_code": "100",
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": me["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    with factory() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == str(proposal_id)))
        assert str(audit.actor_user_id) == governance["user"]["id"] != fiscal["user"]["id"]
        assert audit.effective_role == "ROLE_GOVERNANCA_PDM"


def test_switching_back_and_forth_keeps_both_sessions(demo):
    client, login, _ = demo
    login("AUDITOR_FISCAL")
    governance = login("GESTOR_CADASTRO")
    fiscal = switch(client, governance, "AUDITOR_FISCAL").json()
    back = switch(client, fiscal, "GESTOR_CADASTRO")
    assert back.status_code == 200, back.text
    assert back.json()["user"]["id"] == governance["user"]["id"]


def test_persona_without_a_session_in_this_browser_is_not_granted(demo):
    client, login, _ = demo
    governance = login("GESTOR_CADASTRO")
    response = switch(client, governance, "AUDITOR_FISCAL")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEMO_SESSION_NOT_FOUND"
    assert client.get("/api/v1/auth/me").json()["user"]["id"] == governance["user"]["id"]


def test_switch_requires_csrf_origin_and_the_same_browser(demo):
    client, login, _ = demo
    login("AUDITOR_FISCAL")
    governance = login("GESTOR_CADASTRO")
    assert switch(client, governance, "AUDITOR_FISCAL", **{"X-CSRF-Token": "wrong"}).status_code == 403
    assert switch(client, governance, "AUDITOR_FISCAL", Origin="https://evil.test").status_code == 403
    # Outro navegador com o cookie de sessão copiado, mas outro contexto, não autentica.
    token = client.cookies[SESSION_COOKIE]
    other = TestClient(client.app, base_url=ORIGIN)
    other.cookies.set(SESSION_COOKIE, token)
    other.cookies.set(CONTEXT_COOKIE, "another-browser")
    assert switch(other, governance, "AUDITOR_FISCAL").status_code == 401


def test_sessions_from_another_browser_are_not_reachable(demo, oidc):  # noqa: F811
    client, login, factory = demo
    login("AUDITOR_FISCAL")
    governance = login("GESTOR_CADASTRO")
    with factory() as db:
        for session in db.scalars(select(AuthSession).where(AuthSession.demo_label == "AUDITOR_FISCAL")):
            session.browser_context_hash = digest("another-browser")
        db.commit()
    assert switch(client, governance, "AUDITOR_FISCAL").status_code == 404


def test_account_outside_the_demo_list_has_no_persona(demo):
    client, login, _ = demo
    me = login("GESTOR_CADASTRO", email="someone@else.test")
    assert me["demo"] == {"enabled": False, "active_persona": None}
    assert switch(client, me, "GESTOR_CADASTRO").status_code == 403


def test_demo_account_with_another_role_gets_no_persona(demo):
    """A persona vem da lista e do papel no token; e-mail sozinho não concede a persona fiscal."""
    client, login, _ = demo
    me = login("AUDITOR_FISCAL", group="ROLE_SOLICITANTE")
    assert me["demo"]["active_persona"] is None
    assert me["user"]["roles"] == ["ROLE_SOLICITANTE"]


def test_switch_is_off_without_demo_mode(demo, monkeypatch):
    client, login, _ = demo
    login("AUDITOR_FISCAL")
    governance = login("GESTOR_CADASTRO")
    monkeypatch.setenv("DEMO_MODE", "false")
    me = client.get("/api/v1/auth/me").json()
    assert me["demo"] == {"enabled": False, "active_persona": None}
    response = switch(client, governance, "AUDITOR_FISCAL")
    assert response.status_code == 403 and response.json()["error"]["code"] == "DEMO_DISABLED"


def test_expired_or_revoked_target_session_is_refused(demo):
    client, login, factory = demo
    login("AUDITOR_FISCAL")
    governance = login("GESTOR_CADASTRO")
    from datetime import UTC, datetime

    with factory() as db:
        for session in db.scalars(select(AuthSession).where(AuthSession.demo_label == "AUDITOR_FISCAL")):
            session.revoked_at = datetime.now(UTC)
        db.commit()
    assert switch(client, governance, "AUDITOR_FISCAL").status_code == 404


def test_demo_mode_requires_accounts(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("DEMO_ACCOUNTS", raising=False)
    with pytest.raises(RuntimeError, match="DEMO_ACCOUNTS"):
        create_app()
    monkeypatch.setenv("DEMO_ACCOUNTS", "ADMIN=x@y.test")
    with pytest.raises(RuntimeError, match="inválido"):
        create_app()
