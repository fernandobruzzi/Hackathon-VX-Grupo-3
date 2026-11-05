"""Dependências das rotas: banco, identidade e Agent, guardados em `app.state` por `create_app`."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.identity import Identity
from vx_materials_api.services.agent_client import AgentClient


def db_session(request: Request) -> Iterator[Session]:
    if request.app.state.request_identity_provider is None and request.app.state.identity_provider is None:
        raise ApiProblem(401, "UNAUTHENTICATED", "Sessão inválida ou expirada.")
    with request.app.state.session_factory() as session:
        yield session


def current_identity(request: Request, db: Annotated[Session, Depends(db_session)]) -> Identity:
    """Identidade da sessão. Sem provedor configurado (login real ainda ausente), responde 401."""
    provider = request.app.state.request_identity_provider
    if provider is not None:
        return provider(request, db)
    provider = request.app.state.identity_provider
    if provider is None:
        raise ApiProblem(401, "UNAUTHENTICATED", "Sessão inválida ou expirada.")
    return provider(db)


def agent_client(request: Request) -> AgentClient:
    return request.app.state.agent_client


# Aprovações e chat compartilham a mesma sessão e a mesma transação por requisição.
get_db = db_session
