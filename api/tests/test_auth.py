"""OAuth com assinaturas RSA reais e provedor controlado; não comprova acesso à AWS."""

import base64
import hashlib
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vx_materials_api.db.models import AuthSession, LoginTransaction, UserSso
from vx_materials_api.errors import ApiProblem
from vx_materials_api.main import create_app
from vx_materials_api.security.cognito import CognitoClient, CognitoConfig
from vx_materials_api.security.permissions import PERSONA_ROLES
from vx_materials_api.security.sessions import CONTEXT_COOKIE, LOGIN_COOKIE, SESSION_COOKIE, digest


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def oidc(signing_key):
    config = CognitoConfig(
        "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test",
        "client1",
        "https://pool.auth.us-east-1.amazoncognito.com",
        "https://app.test",
        Fernet.generate_key().decode(),
        ("1100", "1200"),
    )
    keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=signing_key.public_key()))
    client = CognitoClient(config, key_provider=keys)

    def token(use="access", **changes):
        claims = {
            "iss": config.issuer,
            "sub": "user1",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "token_use": use,
        }
        claims |= (
            {"client_id": config.client_id, "scope": "openid profile", "cognito:groups": ["ROLE_SOLICITANTE"]}
            if use == "access"
            else {"aud": config.client_id, "nonce": "nonce", "name": "Pessoa"}
        )
        claims.update(changes)
        return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})

    return config, client, token


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://evil.test"},
        {"exp": 1},
        {"iat": 9999999999},
        {"token_use": "id"},
        {"client_id": "wrong"},
        {"sub": ""},
        {"scope": "profile"},
        {"scope": []},
        {"cognito:groups": "ROLE_SOLICITANTE"},
        {"exp": "9999999999"},
    ],
)
def test_access_token_rejects_invalid_claims(oidc, changes):
    _, client, token = oidc
    with pytest.raises(ApiProblem) as error:
        client.validate(token(**changes), "access")
    assert error.value.status == 401


def test_unknown_groups_do_not_grant_access(oidc):
    _, client, token = oidc
    with pytest.raises(ApiProblem) as error:
        client.validate(token(**{"cognito:groups": ["admin"]}), "access")
    assert error.value.status == 403


@pytest.mark.parametrize(
    "marker", ["AWS_EXECUTION_ENV", "ECS_CONTAINER_METADATA_URI_V4", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"]
)
def test_local_identity_cannot_start_in_aws_runtime(monkeypatch, marker):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    monkeypatch.setenv(marker, "present")
    with pytest.raises(RuntimeError):
        create_app()


def test_cognito_and_local_helpers_are_mutually_exclusive(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    monkeypatch.setenv("AUTH_BACKEND", "cognito")
    with pytest.raises(RuntimeError, match="juntos"):
        create_app()


def test_signature_algorithm_audience_nonce_and_subject_are_checked(oidc):
    config, client, token = oidc
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(token(), options={"verify_signature": False})
    invalid = [
        jwt.encode(claims, wrong_key, algorithm="RS256", headers={"kid": "test-key"}),
        jwt.encode(claims, "not-a-real-secret-just-a-test-key", algorithm="HS256", headers={"kid": "test-key"}),
    ]
    for value in invalid:
        with pytest.raises(ApiProblem):
            client.validate(value, "access")
    for profile in [token("id", aud="other"), token("id", nonce="other"), token("id", sub="other")]:
        with pytest.raises(ApiProblem):
            client.validate_pair({"access_token": token(), "id_token": profile}, "nonce")
    assert client.validate(token(), "access")["client_id"] == config.client_id


@pytest.fixture
def browser(connection, oidc):
    config, cognito, token = oidc

    def factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    app = create_app(session_factory=factory, cognito_config=config, cognito_client=cognito)
    client = TestClient(app, base_url=config.origin)
    query = parse_qs(urlsplit(client.get("/api/v1/auth/sso-start", follow_redirects=False).headers["location"]).query)
    issued = {"access_token": token(), "id_token": token("id", nonce=query["nonce"][0]), "token_type": "Bearer"}
    calls = []

    def exchange(request):
        body = parse_qs(request.content.decode())
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(body["code_verifier"][0].encode()).digest()).decode().rstrip("=")
        )
        assert challenge == query["code_challenge"][0]
        assert body["redirect_uri"] == [config.redirect_uri]
        calls.append(body)
        return httpx.Response(200, json=issued)

    cognito.transport = httpx.MockTransport(exchange)
    yield client, app, factory, query, issued, calls
    client.close()


def finish(browser, **changes):
    client, _, _, query, _, _ = browser
    return client.post(
        "/api/v1/auth/sso-callback",
        headers={"Origin": "https://app.test"},
        json={"code": "one-time-code", "state": query["state"][0], **changes},
    )


def test_pkce_login_opaque_cookie_encrypted_tokens_and_logout(browser):
    client, _, factory, query, issued, calls = browser
    assert query["code_challenge_method"] == ["S256"]
    response = finish(browser)
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    cookies = response.headers.get_list("set-cookie")
    assert all("Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie for cookie in cookies)
    assert response.headers["cache-control"] == "no-store"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["user"]["roles"] == ["ROLE_SOLICITANTE"]
    assert me.json()["demo"] == {"enabled": False, "active_persona": None}
    assert me.json()["scope"]["center_codes"] == ["1100", "1200"]
    with factory() as db:
        session = db.scalar(
            select(AuthSession).where(AuthSession.session_token_hash == digest(client.cookies[SESSION_COOKIE]))
        )
        assert issued["access_token"].encode() not in session.tokens_ciphertext
        assert client.cookies[SESSION_COOKIE] != session.session_token_hash
        assert me.json()["csrf_token"] != session.csrf_token_hash
    assert finish(browser).status_code == 401
    assert len(calls) == 1
    assert client.post("/api/v1/auth/logout", json={}).status_code == 403
    result = client.post(
        "/api/v1/auth/logout", json={}, headers={"Origin": "https://app.test", "X-CSRF-Token": me.json()["csrf_token"]}
    )
    assert result.status_code == 200
    # O provedor também encerra a própria sessão; sem isso o próximo login volta à mesma conta.
    logout_url = urlsplit(result.json()["provider_logout_url"])
    assert (logout_url.scheme, logout_url.netloc, logout_url.path) == (
        "https",
        "pool.auth.us-east-1.amazoncognito.com",
        "/logout",
    )
    assert parse_qs(logout_url.query) == {"client_id": ["client1"], "logout_uri": ["https://app.test/login/"]}
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("failure", ["state", "browser", "expired", "nonce", "origin"])
def test_oauth_transaction_is_bound_to_browser_state_expiry_and_nonce(browser, failure, signing_key):
    client, _, factory, _, issued, calls = browser
    if failure == "browser":
        client.cookies.delete(LOGIN_COOKIE)
    if failure == "expired":
        with factory() as db:
            db.scalar(select(LoginTransaction)).expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
    if failure == "nonce":
        payload = jwt.decode(issued["id_token"], options={"verify_signature": False})
        payload["nonce"] = "wrong"
        issued["id_token"] = jwt.encode(payload, signing_key, algorithm="RS256", headers={"kid": "test-key"})
    if failure == "origin":
        response = client.post(
            "/api/v1/auth/sso-callback",
            headers={"Origin": "https://evil.test"},
            json={"code": "code", "state": "x" * 43},
        )
        assert response.status_code == 403
    else:
        assert finish(browser, **({"state": "x" * 43} if failure == "state" else {})).status_code == 401
    with factory() as db:
        assert db.scalar(select(AuthSession)) is None


def test_expiry_revocation_context_and_disabled_user_are_enforced(browser):
    client, app, factory, _, _, _ = browser
    assert finish(browser).status_code == 200
    context = client.cookies[CONTEXT_COOKIE]
    session_hash = digest(client.cookies[SESSION_COOKIE])
    client.cookies.delete(CONTEXT_COOKIE)
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set(CONTEXT_COOKIE, context)
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.session_token_hash == session_hash))
        db.get(UserSso, session.user_id).disabled_at = datetime.now(UTC)
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.session_token_hash == session_hash))
        db.get(UserSso, session.user_id).disabled_at = None
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_after_expiry_still_ends_the_provider_session(browser):
    # Uma aba aberta além da validade da sessão precisa conseguir sair; senão o
    # Hosted UI continua logado e o próximo login volta à mesma conta.
    client, _, factory, _, _, _ = browser
    assert finish(browser).status_code == 200
    with factory() as db:
        session = db.scalar(
            select(AuthSession).where(AuthSession.session_token_hash == digest(client.cookies[SESSION_COOKIE]))
        )
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/v1/auth/logout", json={}, headers={"Origin": "https://evil.test"}).status_code == 403
    result = client.post("/api/v1/auth/logout", json={}, headers={"Origin": "https://app.test"})
    assert result.status_code == 200, result.text
    assert urlsplit(result.json()["provider_logout_url"]).path == "/logout"
    assert SESSION_COOKIE not in client.cookies
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("persona,role", PERSONA_ROLES.items())
def test_local_accounts_have_server_roles_and_revocable_sessions(connection, monkeypatch, persona, role):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ENABLE_LOCAL_TEST_SESSIONS", "true")

    def factory():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    client = TestClient(create_app(session_factory=factory), base_url="http://localhost:8000")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/local-session", json={"persona": persona}).status_code == 403
    response = client.post(
        "/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": "http://localhost:8000"}
    )
    assert response.status_code == 200, response.text
    me = client.get("/api/v1/auth/me").json()
    assert me["user"]["roles"] == [role]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert me["demo"]["active_persona"] == persona
    logout = client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Origin": "http://localhost:8000", "X-CSRF-Token": me["csrf_token"]},
    )
    assert logout.status_code == 200
    assert logout.json() == {"logged_out": True}
    assert client.get("/api/v1/auth/me").status_code == 401
