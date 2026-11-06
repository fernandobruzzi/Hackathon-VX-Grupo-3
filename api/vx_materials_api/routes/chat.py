"""Rotas de conversa."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from vx_materials_api import settings
from vx_materials_api.dependencies import agent_client, current_identity, db_session
from vx_materials_api.errors import ApiProblem, request_id
from vx_materials_api.routes.sanitization import catalog
from vx_materials_api.schemas.chat import ChatMessageRequest, ChatSubmitRequest, ChatSubmitResponse, ChatTurnResponse
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.rbac import effective_permissions, require_center, require_permission
from vx_materials_api.security.service_tokens import issue_agent_token
from vx_materials_api.security.sessions import verify_write
from vx_materials_api.services import chat_order_service, chat_service
from vx_materials_api.services.agent_client import AgentClient, AgentUnavailable

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/message")
async def send_message(
    payload: ChatMessageRequest,
    request: Request,
    identity: Annotated[Identity, Depends(current_identity)],
    db: Annotated[Session, Depends(db_session)],
    agent: Annotated[AgentClient, Depends(agent_client)],
) -> ChatTurnResponse:
    """Executa um turno com chamadas MCP reais. Não publica material nem cria pedido."""
    require_permission(identity, "chat:use")
    require_center(identity, payload.center_code)
    verify_write(request, identity)
    rid = request_id(request)
    reservation = chat_service.reserve_turn(db, identity, payload)
    secret = settings.agent_internal_token_secret()
    token = issue_agent_token(
        identity.user_id, effective_permissions(identity), identity.center_codes, secret, identity.tenant_id
    )
    try:
        result = await agent.run(reservation.agent_payload, token, rid)
    except AgentUnavailable as error:
        chat_service.release_turn(db, reservation)
        raise ApiProblem(503, error.code, str(error)) from error
    return chat_service.complete_turn(db, identity, payload, reservation, result, rid)


@router.post("/{session_id}/submit")
def submit_chat(
    session_id: UUID,
    payload: ChatSubmitRequest,
    request: Request,
    identity: Annotated[Identity, Depends(current_identity)],
    db: Annotated[Session, Depends(db_session)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ChatSubmitResponse:
    verify_write(request, identity)
    return chat_order_service.submit_chat_order(
        db,
        identity,
        catalog(request),
        session_id,
        payload.expected_session_version,
        idempotency_key,
        request_id(request),
    )
