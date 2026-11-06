import uuid

import pytest
from approval_fixtures import decide
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vx_materials_api.db.models import AuthSession
from vx_materials_api.main import create_app


@pytest.mark.parametrize(
    ("principal_index", "area"), [(0, "FISCAL"), (1, "TECHNICAL"), (2, "TECHNICAL"), (2, "FISCAL")]
)
def test_wrong_roles_are_refused_by_api(approval_case, principal_index, area):
    case = approval_case
    case["app"].state.test_principal = case["principals"][principal_index]
    response = decide(case, payload=case["payload"] | {"review_area": area})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("field", ["role", "actor_id", "approved_by", "new_value"])
def test_actor_and_new_values_cannot_be_sent_with_a_decision(approval_case, field):
    case = approval_case
    response = decide(case, payload=case["payload"] | {field: "untrusted"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("changes", [{"X-CSRF-Token": "bad"}, {"Origin": "https://evil.example"}])
def test_csrf_and_origin_are_checked_before_writing(approval_case, changes):
    case = approval_case
    case["headers"].update(changes)
    assert decide(case).status_code == 403


def test_missing_or_invalid_idempotency_key_is_validation_error(approval_case):
    case = approval_case
    for key in [None, "not-a-uuid"]:
        headers = {k: v for k, v in case["headers"].items() if k != "Idempotency-Key"}
        if key:
            headers["Idempotency-Key"] = key
        response = case["client"].post(
            f"/api/v1/sanitization/{case['proposal'].id}/decide", headers=headers, json=case["payload"]
        )
        assert response.status_code == 422


def test_role_header_does_not_grant_identity(approval_case):
    case = approval_case
    case["app"].state.identity_provider = None
    case["headers"]["X-Role"] = "ROLE_GOVERNANCA_PDM"
    assert decide(case).status_code == 401


def test_read_only_permission_does_not_grant_decisions_or_audit(approval_case):
    from dataclasses import replace

    case = approval_case
    case["app"].state.test_principal = replace(case["principals"][0], permissions=frozenset({"queue:read"}))
    detail = case["client"].get(f"/api/v1/sanitization/{case['proposal'].id}")
    assert detail.status_code == 200
    assert detail.json()["allowed_actions"] == []
    assert decide(case).status_code == 403
    assert case["client"].get("/api/v1/audit").status_code == 403


def test_forged_bearer_header_cannot_bypass_cookie_csrf(approval_case):
    case = approval_case
    case["headers"]["Authorization"] = "Bearer forged"
    case["headers"].pop("X-CSRF-Token")
    assert decide(case).status_code == 403


def test_trusted_bearer_provider_does_not_require_cookie_csrf(approval_case):
    from dataclasses import replace

    case = approval_case
    case["app"].state.test_principal = replace(case["principals"][0], authentication_method="bearer")
    case["headers"].pop("X-CSRF-Token")
    case["headers"].pop("Origin")
    assert decide(case).status_code == 200


def test_database_errors_have_no_sql_or_credentials_in_response():
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("private SQL", {}, Exception("private credential"))

    app = create_app(session_factory=unavailable, identity_provider=lambda db: None)
    response = TestClient(app).get("/api/v1/audit")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "private" not in response.text


@pytest.mark.parametrize("environment", [None, "production", "staging"])
def test_local_sessions_require_explicit_local_environment(monkeypatch, environment):
    monkeypatch.setenv("ENABLE_LOCAL_TEST_SESSIONS", "true")
    if environment is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", environment)
    with pytest.raises(RuntimeError, match="APP_ENV=local"):
        create_app()


@pytest.mark.parametrize(
    "marker", ["AWS_EXECUTION_ENV", "ECS_CONTAINER_METADATA_URI_V4", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"]
)
def test_local_sessions_are_impossible_with_aws_runtime_markers(monkeypatch, marker):
    monkeypatch.setenv("ENABLE_LOCAL_TEST_SESSIONS", "true")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv(marker, "present")
    with pytest.raises(RuntimeError, match="AWS"):
        create_app()


def test_local_endpoint_is_absent_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_LOCAL_TEST_SESSIONS", raising=False)
    assert (
        TestClient(create_app()).post("/api/v1/auth/local-session", json={"persona": "GESTOR_CADASTRO"}).status_code
        == 404
    )


def test_local_session_uses_opaque_cookie_expiry_csrf_and_revocation(connection, monkeypatch):
    monkeypatch.setenv("ENABLE_LOCAL_TEST_SESSIONS", "true")
    monkeypatch.setenv("APP_ENV", "local")
    app = create_app(session_factory=lambda: Session(bind=connection, join_transaction_mode="create_savepoint"))
    with TestClient(app, base_url="http://localhost:8000") as client:
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post("/api/v1/auth/local-session", json={"persona": "GESTOR_CADASTRO"}).status_code == 403
        result = client.post(
            "/api/v1/auth/local-session",
            json={"persona": "GESTOR_CADASTRO"},
            headers={"Origin": "http://localhost:8000"},
        )
        assert result.status_code == 200, result.text
        assert "HttpOnly" in result.headers["set-cookie"]
        assert "SameSite=lax" in result.headers["set-cookie"]
        me = client.get("/api/v1/auth/me").json()
        from vx_materials_api.bootstrap import TENANT_ID
        from vx_materials_api.security.approval_identity import LOCAL_TENANT

        assert LOCAL_TENANT == TENANT_ID
        assert me["user"]["roles"] == ["ROLE_GOVERNANCA_PDM"]
        assert me["csrf_token"] == result.json()["csrf_token"]
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            stored = db.scalar(select(AuthSession))
            assert client.cookies["vx_local_session"] not in stored.session_token_hash
            assert me["csrf_token"] not in stored.csrf_token_hash
        headers = {
            "Origin": "http://localhost:8000",
            "X-CSRF-Token": me["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
        }
        assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
