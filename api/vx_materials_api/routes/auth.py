"""Login OAuth com PKCE, sessão BFF e contas de teste exclusivamente locais."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import uuid5

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vx_materials_api import settings
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import AuthSession, LoginTransaction, UserSso
from vx_materials_api.dependencies import current_identity, db_session
from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.cognito import invalid_login
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.local_session import CENTERS, LOCAL_COOKIE, csrf_for
from vx_materials_api.security.permissions import PERSONA_ROLES, permissions_for
from vx_materials_api.security.sessions import (
    CONTEXT_COOKIE,
    LOGIN_COOKIE,
    SESSION_COOKIE,
    create_session,
    demo_persona,
    digest,
    identity_from_session,
    me_response,
    seal,
    secure_cookie,
    unseal,
    verify_write,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
local_router = APIRouter(prefix="/api/v1/auth", tags=["local-auth"])
Db = Annotated[Session, Depends(db_session)]
Caller = Annotated[Identity, Depends(current_identity)]


class CallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=32, max_length=128)


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_handle: str = Field(min_length=1, max_length=64)


class LocalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona: Literal["SOLICITANTE_OPERACAO", "GESTOR_CADASTRO", "AUDITOR_FISCAL", "DEV_TI"]


def same_origin(request):
    if request.headers.get("origin") != request.app.state.application_origin:
        raise ApiProblem(403, "FORBIDDEN", "Origem não autorizada.")


@router.get("/config")
def config(request: Request):
    return {"mode": request.app.state.auth_mode}


@router.get("/sso-start")
def sso_start(request: Request, db: Db, prompt: Literal["login"] | None = None):
    config = request.app.state.cognito_config
    if config is None:
        raise ApiProblem(503, "IDENTITY_UNAVAILABLE", "Cognito ainda não configurado.")
    state, nonce, verifier, browser = (secrets.token_urlsafe(32) for _ in range(4))
    db.add(
        LoginTransaction(
            state_hash=digest(state),
            browser_context_hash=digest(browser),
            payload_ciphertext=seal(config, {"nonce": nonce, "verifier": verifier}),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    db.commit()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            # No modo demo, permite entrar com outra conta sem sair da atual no Cognito.
            **({"prompt": "login"} if prompt and settings.demo_mode_enabled() else {}),
        }
    )
    response = RedirectResponse(config.domain + "/oauth2/authorize?" + query, status_code=302)
    secure_cookie(response, LOGIN_COOKIE, browser, 600)
    return response


@router.post("/sso-callback")
def callback(payload: CallbackRequest, request: Request, response: Response, db: Db):
    same_origin(request)
    client = request.app.state.cognito_client
    if client is None:
        raise ApiProblem(503, "IDENTITY_UNAVAILABLE", "Cognito ainda não configurado.")
    transaction = db.scalar(
        select(LoginTransaction).where(LoginTransaction.state_hash == digest(payload.state)).with_for_update()
    )
    if (
        transaction is None
        or transaction.consumed_at is not None
        or transaction.expires_at <= datetime.now(UTC)
        or not hmac.compare_digest(transaction.browser_context_hash, digest(request.cookies.get(LOGIN_COOKIE, "")))
    ):
        raise invalid_login()
    login = unseal(client.config, transaction.payload_ciphertext)
    transaction.consumed_at = datetime.now(UTC)
    db.commit()
    # O código só pode ser trocado uma vez, inclusive quando o provedor falha.
    tokens = client.exchange(payload.code, login["verifier"])
    access, profile = client.validate_pair(tokens, login["nonce"])
    browser = request.cookies.get(CONTEXT_COOKIE) or secrets.token_urlsafe(32)
    token, session = create_session(db, client.config, tokens, access, profile, browser)
    db.commit()
    seconds = max(0, int((session.expires_at - datetime.now(UTC)).total_seconds()))
    secure_cookie(response, SESSION_COOKIE, token, seconds)
    secure_cookie(response, CONTEXT_COOKIE, browser, 86400)
    response.delete_cookie(LOGIN_COOKIE, secure=True, httponly=True, samesite="lax")
    return {"authenticated": True, "expires_in_seconds": seconds, "redirect_path": "/chat/"}


@router.get("/me")
def me(caller: Caller):
    return me_response(caller)


@router.post("/demo/switch")
def demo_switch(payload: DemoSwitchRequest, request: Request, response: Response, caller: Caller, db: Db):
    """Troca para outra sessão demo já autenticada neste navegador. A persona não concede papel."""
    client = request.app.state.cognito_client
    if not settings.demo_mode_enabled() or client is None or caller.authentication_method != "cookie":
        raise ApiProblem(403, "DEMO_DISABLED", "Troca de persona indisponível neste ambiente.")
    verify_write(request, caller)
    if caller.persona is None:
        raise ApiProblem(403, "FORBIDDEN", "A sessão atual não é de uma conta de demonstração.")
    # O handle é a persona; só vale uma sessão desta mesma conta de navegador, ainda válida.
    row = db.execute(
        select(AuthSession, UserSso)
        .join(UserSso, AuthSession.user_id == UserSso.id)
        .where(
            AuthSession.demo_label == payload.session_handle,
            AuthSession.browser_context_hash == digest(request.cookies.get(CONTEXT_COOKIE, "")),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
            UserSso.disabled_at.is_(None),
            UserSso.tenant_id == TENANT_ID,
            UserSso.issuer == client.config.issuer,
        )
        .order_by(AuthSession.expires_at.desc())
        .limit(1)
        .with_for_update()
    ).first()
    if row is None:
        raise ApiProblem(
            404,
            "DEMO_SESSION_NOT_FOUND",
            "Entre antes com a conta desta persona neste navegador.",
            persona=payload.session_handle,
        )
    identity = identity_from_session(client, row.AuthSession, row.UserSso)
    # A lista de contas pode ter mudado desde o login: confere de novo com os papéis atuais do token.
    if demo_persona(row.UserSso, identity.roles) != payload.session_handle:
        raise ApiProblem(403, "FORBIDDEN", "A conta não pertence à lista de demonstração.")
    # Um segredo novo para a sessão escolhida: o cookie antigo dela deixa de valer.
    token = secrets.token_urlsafe(32)
    row.AuthSession.session_token_hash = digest(token)
    db.commit()
    seconds = max(0, int((row.AuthSession.expires_at - datetime.now(UTC)).total_seconds()))
    secure_cookie(response, SESSION_COOKIE, token, seconds)
    return me_response(identity)


@router.post("/logout")
def logout(payload: EmptyRequest, request: Request, response: Response, caller: Caller, db: Db):
    verify_write(request, caller)
    cookie = LOCAL_COOKIE if request.app.state.auth_mode == "local" else SESSION_COOKIE
    session = db.scalar(
        select(AuthSession).where(AuthSession.session_token_hash == digest(request.cookies.get(cookie, "")))
    )
    if session:
        session.revoked_at = datetime.now(UTC)
        db.commit()
    response.delete_cookie(cookie, secure=cookie == SESSION_COOKIE, httponly=True, samesite="lax")
    return {"logged_out": True}


@local_router.post("/local-session")
def local_session(payload: LocalRequest, request: Request, response: Response, db: Db):
    same_origin(request)
    role = PERSONA_ROLES[payload.persona]
    user_id = uuid5(TENANT_ID, payload.persona)
    db.execute(
        insert(UserSso)
        .values(
            id=user_id,
            tenant_id=TENANT_ID,
            issuer="local-test",
            subject=payload.persona,
            display_name=f"{payload.persona} (teste local)",
            roles_snapshot=[role],
        )
        .on_conflict_do_nothing(index_elements=["issuer", "subject"])
    )
    user = db.get(UserSso, user_id)
    if user is None or user.disabled_at or user.tenant_id != TENANT_ID or user.roles_snapshot != [role]:
        raise ApiProblem(403, "FORBIDDEN", "Conta local desabilitada ou alterada.")
    old = db.scalar(
        select(AuthSession).where(AuthSession.session_token_hash == digest(request.cookies.get(LOCAL_COOKIE, "")))
    )
    if old:
        old.revoked_at = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    csrf = csrf_for(request, token)
    db.add(
        AuthSession(
            session_token_hash=digest(token),
            browser_context_hash=digest(token),
            user_id=user_id,
            tokens_ciphertext=b"",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            csrf_token_hash=digest(csrf),
            demo_label=payload.persona,
        )
    )
    db.commit()
    response.set_cookie(LOCAL_COOKIE, token, httponly=True, samesite="lax", max_age=3600)
    return me_response(
        Identity(
            user_id,
            TENANT_ID,
            (role,),
            permissions_for((role,)),
            display_name=user.display_name,
            center_codes=frozenset(CENTERS),
            csrf_token=csrf,
            persona=payload.persona,
        )
    )
