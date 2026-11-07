"""Aplicacao FastAPI: rotas em /api/v1 e build do front na mesma origem."""

import os
import secrets
from collections.abc import Callable
from functools import cache
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, sessionmaker

from vx_materials_api import settings
from vx_materials_api.db.session import make_engine, make_session_factory
from vx_materials_api.errors import register_error_handlers, request_id
from vx_materials_api.routes import (
    auth,
    batch,
    chat,
    dashboard,
    enrichment,
    manual_reviews,
    materials,
    registration_orders,
    sanitization,
)
from vx_materials_api.security.cognito import CognitoClient, CognitoConfig
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.local_session import local_identity
from vx_materials_api.security.sessions import session_identity
from vx_materials_api.services.agent_client import AgentClient
from vx_materials_api.services.batch_runner import BatchRunner, get_batch_runner

IdentityProvider = Callable[[Session], Identity]


@cache
def _default_session_factory() -> sessionmaker[Session]:
    """Criada no primeiro uso: rotas sem banco, como healthz, sobem sem DATABASE_URL."""
    return make_session_factory(make_engine())


def _default_identity_provider() -> IdentityProvider | None:
    settings.check_local_shortcuts()
    return None


def create_app(
    front_dist: Path | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    identity_provider: IdentityProvider | None = None,
    agent_client: AgentClient | None = None,
    cognito_config: CognitoConfig | None = None,
    cognito_client: CognitoClient | None = None,
    batch_runner: BatchRunner | None = None,
) -> FastAPI:
    app = FastAPI(title="VX Materiais API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.session_factory = session_factory or (lambda: _default_session_factory()())
    app.state.identity_provider = identity_provider or _default_identity_provider()
    settings.check_local_shortcuts()
    # Falha cedo se a troca de persona estiver ligada sem a lista de contas.
    settings.demo_accounts()
    backend = os.environ.get("AUTH_BACKEND", "disabled")
    if backend not in {"disabled", "cognito"}:
        raise RuntimeError("AUTH_BACKEND deve ser disabled ou cognito")
    if settings.local_test_session_enabled() and (backend == "cognito" or cognito_config):
        raise RuntimeError("Sessões locais e Cognito não podem ser habilitados juntos")
    config = cognito_config or (CognitoConfig.from_environment() if backend == "cognito" else None)
    app.state.cognito_config = config
    app.state.cognito_client = cognito_client or (CognitoClient(config) if config else None)
    app.state.application_origin = config.origin if config else settings.application_origin()
    app.state.auth_mode = "cognito" if config else "disabled"
    app.state.request_identity_provider = session_identity if config else None
    if settings.local_test_session_enabled():
        app.state.auth_mode = "local"
        app.state.local_session_secret = secrets.token_bytes(32)
        app.state.request_identity_provider = local_identity
        app.include_router(auth.local_router)
    app.state.agent_client = agent_client or AgentClient(settings.agent_url())
    app.state.pdm_catalog = None
    app.state.batch_runner = batch_runner or get_batch_runner()
    register_error_handlers(app)

    @app.middleware("http")
    async def private_auth_responses(request, call_next):
        rid = request_id(request)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if request.url.path.startswith("/api/v1/auth/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/v1/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(dashboard.router)
    app.include_router(batch.router)
    app.include_router(manual_reviews.router)
    app.include_router(chat.router)
    app.include_router(materials.router)
    app.include_router(auth.router)
    app.include_router(sanitization.router)
    app.include_router(enrichment.router)
    app.include_router(registration_orders.router)

    # Montado por ultimo: as rotas da API tem prioridade sobre os arquivos estaticos.
    if front_dist:
        app.mount("/", StaticFiles(directory=front_dist, html=True), name="front")
    return app


app = create_app(settings.front_dist_dir())


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=settings.api_port(), access_log=False)
