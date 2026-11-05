"""Aplicacao FastAPI: rotas em /api/v1 e build do front na mesma origem."""

from collections.abc import Callable
from functools import cache
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, sessionmaker

from vx_materials_api import settings
from vx_materials_api.db.session import make_engine, make_session_factory
from vx_materials_api.errors import register_error_handlers
from vx_materials_api.routes import chat
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.local_session import local_identity
from vx_materials_api.services.agent_client import AgentClient

IdentityProvider = Callable[[Session], Identity]


@cache
def _default_session_factory() -> sessionmaker[Session]:
    """Criada no primeiro uso: rotas sem banco, como healthz, sobem sem DATABASE_URL."""
    return make_session_factory(make_engine())


def _default_identity_provider() -> IdentityProvider | None:
    settings.check_local_shortcuts()
    return local_identity if settings.local_test_session_enabled() else None


def create_app(
    front_dist: Path | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    identity_provider: IdentityProvider | None = None,
    agent_client: AgentClient | None = None,
) -> FastAPI:
    app = FastAPI(title="VX Materiais API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.session_factory = session_factory or (lambda: _default_session_factory()())
    app.state.identity_provider = identity_provider or _default_identity_provider()
    app.state.agent_client = agent_client or AgentClient(settings.agent_url())
    register_error_handlers(app)

    @app.get("/api/v1/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(chat.router)

    # Montado por ultimo: as rotas da API tem prioridade sobre os arquivos estaticos.
    if front_dist:
        app.mount("/", StaticFiles(directory=front_dist, html=True), name="front")
    return app


app = create_app(settings.front_dist_dir())


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=settings.api_port())
