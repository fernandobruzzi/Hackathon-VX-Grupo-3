"""Sessão de teste para desenvolver sem Cognito. Só existe com APP_ENV=local e LOCAL_TEST_SESSION=true.

As três contas fixas só são acessadas após criar um cookie opaco no endpoint local.
"""

import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy import select

from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import AuthSession, UserSso
from vx_materials_api.security.cognito import invalid_login
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.security.sessions import digest

LOCAL_COOKIE = "vx_local_session"
CENTERS = ("1100", "1200", "1300", "2100", "2200", "9000")


def csrf_for(request, token):
    return hmac.new(request.app.state.local_session_secret, token.encode(), hashlib.sha256).hexdigest()


def local_identity(request, db):
    token = request.cookies.get(LOCAL_COOKIE, "")
    row = db.execute(
        select(AuthSession, UserSso)
        .join(UserSso, AuthSession.user_id == UserSso.id)
        .where(
            AuthSession.session_token_hash == digest(token),
            AuthSession.expires_at > datetime.now(UTC),
            AuthSession.revoked_at.is_(None),
            UserSso.issuer == "local-test",
            UserSso.disabled_at.is_(None),
            UserSso.tenant_id == TENANT_ID,
        )
    ).first()
    if row is None or not hmac.compare_digest(row.AuthSession.csrf_token_hash, digest(csrf_for(request, token))):
        raise invalid_login()
    roles = tuple(row.UserSso.roles_snapshot)
    return Identity(
        row.UserSso.id,
        TENANT_ID,
        roles,
        permissions_for(roles),
        center_codes=frozenset(CENTERS),
        display_name=row.UserSso.display_name or "",
        csrf_token=csrf_for(request, token),
        persona=row.AuthSession.demo_label,
    )
