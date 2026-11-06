"""Sessão BFF: o cookie contém só um segredo opaco; tokens ficam cifrados no banco."""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from vx_materials_api import settings
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import AuthSession, UserSso
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.cognito import invalid_login
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import PERSONA_ROLES, permissions_for

SESSION_COOKIE = "__Host-vx_session"
CONTEXT_COOKIE = "__Host-vx_browser"
LOGIN_COOKIE = "__Host-vx_login"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def seal(config, payload: dict) -> bytes:
    return Fernet(config.encryption_key.encode()).encrypt(json.dumps(payload).encode())


def unseal(config, payload: bytes) -> dict:
    try:
        return json.loads(Fernet(config.encryption_key.encode()).decrypt(payload))
    except (InvalidToken, ValueError, TypeError):
        raise invalid_login() from None


def secure_cookie(response, name, value, max_age):
    response.set_cookie(name, value, secure=True, httponly=True, samesite="lax", path="/", max_age=max_age)


def verify_write(request: Request, identity: Identity):
    if identity.authentication_method == "bearer":
        return
    if (
        request.headers.get("origin") != request.app.state.application_origin
        or not identity.csrf_token
        or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), identity.csrf_token)
    ):
        raise ApiProblem(403, "FORBIDDEN", "Origem ou proteção CSRF inválida.")


def upsert_user(db, access, profile=None):
    profile = profile or {}
    values = dict(
        tenant_id=TENANT_ID,
        issuer=access["iss"],
        subject=access["sub"],
        display_name=profile.get("name") or profile.get("cognito:username") or access["sub"],
        email=profile.get("email"),
        roles_snapshot=list(access["roles"]),
        last_login_at=datetime.now(UTC),
    )
    db.execute(
        insert(UserSso)
        .values(values)
        .on_conflict_do_update(
            index_elements=["issuer", "subject"],
            set_={k: v for k, v in values.items() if k not in {"tenant_id", "issuer", "subject"}},
        )
    )
    user = db.scalar(select(UserSso).where(UserSso.issuer == access["iss"], UserSso.subject == access["sub"]))
    if user.disabled_at is not None or user.tenant_id != TENANT_ID:
        raise ApiProblem(403, "FORBIDDEN", "Conta desabilitada ou fora do escopo da aplicação.")
    return user


def demo_persona(user, roles) -> str | None:
    """Persona de demonstração da conta, só com DEMO_MODE e com o papel que a persona exige."""
    if not settings.demo_mode_enabled() or not user.email:
        return None
    for persona, email in settings.demo_accounts().items():
        if user.email.lower() == email and PERSONA_ROLES[persona] in roles:
            return persona
    return None


def create_session(db, config, tokens, access, profile, browser_context):
    user = upsert_user(db, access, profile)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = datetime.fromtimestamp(min(access["exp"], profile["exp"]), UTC)
    row = AuthSession(
        user_id=user.id,
        session_token_hash=digest(token),
        browser_context_hash=digest(browser_context),
        tokens_ciphertext=seal(config, {"tokens": tokens, "csrf_token": csrf}),
        expires_at=expires,
        csrf_token_hash=digest(csrf),
        demo_label=demo_persona(user, access["roles"]),
    )
    db.add(row)
    db.flush()
    return token, row


def session_identity(request: Request, db) -> Identity:
    client = request.app.state.cognito_client
    authorization = request.headers.get("authorization")
    if authorization:
        if not authorization.startswith("Bearer "):
            raise invalid_login()
        access = client.validate(authorization[7:], "access")
        user = upsert_user(db, access)
        db.commit()
        return Identity(
            user.id,
            user.tenant_id,
            access["roles"],
            permissions_for(access["roles"]),
            display_name=user.display_name or "",
            center_codes=frozenset(client.config.center_codes),
            authentication_method="bearer",
        )
    row = db.execute(
        select(AuthSession, UserSso)
        .join(UserSso, AuthSession.user_id == UserSso.id)
        .where(
            AuthSession.session_token_hash == digest(request.cookies.get(SESSION_COOKIE, "")),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
            UserSso.disabled_at.is_(None),
            UserSso.tenant_id == TENANT_ID,
            UserSso.issuer == client.config.issuer,
        )
    ).first()
    if row is None or not hmac.compare_digest(
        row.AuthSession.browser_context_hash, digest(request.cookies.get(CONTEXT_COOKIE, ""))
    ):
        raise invalid_login()
    return identity_from_session(client, row.AuthSession, row.UserSso)


def identity_from_session(client, auth_session: AuthSession, user: UserSso) -> Identity:
    """Valida os tokens guardados da sessão e monta a identidade, sempre a partir do servidor."""
    payload = unseal(client.config, auth_session.tokens_ciphertext)
    access = client.validate(payload["tokens"]["access_token"], "access")
    if access["sub"] != user.subject or not hmac.compare_digest(
        digest(payload["csrf_token"]), auth_session.csrf_token_hash
    ):
        raise invalid_login()
    return Identity(
        user.id,
        user.tenant_id,
        access["roles"],
        permissions_for(access["roles"]),
        display_name=user.display_name or "",
        center_codes=frozenset(client.config.center_codes),
        csrf_token=payload["csrf_token"],
        persona=auth_session.demo_label if settings.demo_mode_enabled() else None,
    )


def me_response(identity: Identity):
    return {
        "user": {"id": str(identity.user_id), "display_name": identity.display_name, "roles": list(identity.roles)},
        "permissions": sorted(identity.permissions),
        "scope": {"center_codes": sorted(identity.center_codes)},
        "demo": {"enabled": identity.persona is not None, "active_persona": identity.persona},
        "csrf_token": identity.csrf_token,
    }
