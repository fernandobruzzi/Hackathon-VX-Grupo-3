"""Servidor HTTP interno do Agent, chamado somente pela API."""

import asyncio
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from domain.contracts import PdmCatalog
from domain.pdm_loader import load_pdm
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.chatbot.agent import TURN_TIMEOUT_SECONDS, ToolLimitExceeded, ToolRecorder, run_turn
from vx_materials_mcp.chatbot.session_manager import build_turn_context
from vx_materials_mcp.schemas.agent import AgentRunRequest, AgentRunResponse
from vx_materials_mcp.security import (
    INTERNAL_TOKEN_SECRET_VARIABLE,
    Caller,
    InvalidInternalToken,
    caller_to_environment,
    verify_internal_token,
)
from vx_materials_mcp.server import DEFAULT_PDM_PATH, PDM_PATH_VARIABLE

# Abre o servidor MCP de um turno, já vinculado à identidade validada.
Connect = Callable[[Caller], AbstractAsyncContextManager[Any]]


class AgentError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _error(status: int, code: str, message: str, request_id: str, details: dict | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": request_id, "details": details or {}}}
    return JSONResponse(body, status_code=status)


def create_app(
    catalog: PdmCatalog,
    token_secret: str,
    connect: Connect,
    timeout_seconds: float = TURN_TIMEOUT_SECONDS,
) -> FastAPI:
    app = FastAPI(title="VX Materiais Agent", docs_url=None, redoc_url=None, openapi_url=None)
    classifier = get_classification_repository(catalog)
    extractor = get_extraction_repository()

    @app.exception_handler(AgentError)
    async def agent_error(request: Request, error: AgentError) -> JSONResponse:
        return _error(error.status, error.code, error.message, request.headers.get("X-Request-ID", ""))

    @app.exception_handler(RequestValidationError)
    async def invalid_payload(request: Request, error: RequestValidationError) -> JSONResponse:
        details = {"fields": [".".join(str(part) for part in item["loc"]) for item in error.errors()]}
        return _error(422, "VALIDATION_ERROR", "Payload inválido.", request.headers.get("X-Request-ID", ""), details)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/v1/chat/run")
    async def run_chat_turn(
        payload: AgentRunRequest,
        x_request_id: Annotated[str, Header()],
        authorization: Annotated[str | None, Header()] = None,
    ) -> AgentRunResponse:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AgentError(401, "UNAUTHENTICATED", "Token interno ausente.")
        try:
            # A identidade fica vinculada à execução; nenhum parâmetro das tools a carrega.
            caller = verify_internal_token(token, token_secret)
        except InvalidInternalToken as error:
            raise AgentError(401, "UNAUTHENTICATED", "Token interno inválido.") from error

        context = build_turn_context(payload, catalog.classes, classifier, extractor)

        async def execute() -> AgentRunResponse:
            async with connect(caller) as client:
                return await run_turn(payload, context, ToolRecorder(client))

        try:
            return await asyncio.wait_for(execute(), timeout_seconds)
        except TimeoutError as error:
            raise AgentError(503, "AGENT_TIMEOUT", "O agente não respondeu dentro do prazo.") from error
        except ToolLimitExceeded as error:
            raise AgentError(503, "AGENT_LIMIT", str(error)) from error

    return app


def main() -> None:
    secret = os.environ.get(INTERNAL_TOKEN_SECRET_VARIABLE)
    if not secret:
        raise RuntimeError(f"Variavel de ambiente ausente: {INTERNAL_TOKEN_SECRET_VARIABLE}")
    pdm_path = os.environ.get(PDM_PATH_VARIABLE, DEFAULT_PDM_PATH)
    app = create_app(
        load_pdm(pdm_path),
        secret,
        lambda caller: mcp_client.connect(pdm_path, caller=caller_to_environment(caller)),
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8001")))
