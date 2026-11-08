"""Servidor HTTP interno do Agent, chamado somente pela API."""

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from domain.contracts import PdmCatalog
from domain.pdm_loader import load_pdm
from domain.runtime import check_simulated_clients
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.chatbot import mcp_client
from vx_materials_mcp.chatbot.agent import TURN_TIMEOUT_SECONDS, ToolLimitExceeded, ToolRecorder, run_turn
from vx_materials_mcp.chatbot.bedrock import BedrockError, BedrockPlanner
from vx_materials_mcp.chatbot.session_manager import build_fallback_context, build_turn_context
from vx_materials_mcp.chatbot.turns import AgentBusy, TurnCancelled, TurnManager, configured_limit
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
logger = logging.getLogger(__name__)


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
    max_concurrent_turns: int | None = None,
    bedrock_client: Any = None,
) -> FastAPI:
    turns = TurnManager(configured_limit() if max_concurrent_turns is None else max_concurrent_turns)
    model_id = os.environ.get("BEDROCK_CHAT_MODEL_ID", "").strip()
    planner = BedrockPlanner(model_id, bedrock_client) if model_id else None

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await turns.close()

    app = FastAPI(title="VX Materiais Agent", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.turns = turns
    classifier = get_classification_repository(catalog)
    extractor = get_extraction_repository()

    @app.exception_handler(AgentError)
    async def agent_error(request: Request, error: AgentError) -> JSONResponse:
        response = _error(error.status, error.code, error.message, request.headers.get("X-Request-ID", ""))
        if error.code == "AGENT_BUSY":
            response.headers["Retry-After"] = "1"
        return response

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
        request: Request,
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

        async def execute() -> AgentRunResponse:
            context = build_turn_context(payload, catalog.classes, classifier, extractor)
            active_planner = planner
            # Reconstruir a descrição também nos botões: uma classe pode existir só na interpretação LLM.
            # A ação estruturada continua indo intacta para o ciclo determinístico abaixo.
            if active_planner:
                try:
                    context = await active_planner.interpret(payload, context, catalog)
                except BedrockError as error:
                    if error.code != "BEDROCK_UNAVAILABLE":
                        raise
                    logger.warning("Bedrock unavailable during interpretation; request_id=%s", x_request_id)
                    context = build_fallback_context(payload, catalog.classes, classifier, extractor)
                    active_planner = None
            rag_context = None
            async with connect(caller) as client:
                recorder = ToolRecorder(client)
                result = await run_turn(payload, context, recorder)
                if active_planner:
                    rag_context = await recorder.call(
                        "retrieve_material_context",
                        {
                            "query": (context.search_text or payload.message)[:2000],
                            "pdm_class_id": result.material_card.pdm_class_id,
                            "limit": 3,
                        },
                        lambda packet: {"context": packet, "used_citation_ids": []},
                    )
                    result = result.model_copy(update={"tool_calls": recorder.calls})
            if active_planner:
                try:
                    return await active_planner.respond(payload, result, rag_context=rag_context)
                except BedrockError as error:
                    if error.code != "BEDROCK_UNAVAILABLE":
                        raise
                    logger.warning("Bedrock unavailable during response; request_id=%s", x_request_id)
            return result

        try:
            turn = turns.start(execute)
        except AgentBusy as error:
            raise AgentError(503, "AGENT_BUSY", "O agente está ocupado. Tente novamente em instantes.") from error

        async def disconnected():
            while True:
                message = await request.receive()
                if message["type"] == "http.disconnect":
                    return

        disconnect = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait(
                {turn.task, disconnect}, timeout=timeout_seconds, return_when=asyncio.FIRST_COMPLETED
            )
            if disconnect in done:
                raise AgentError(499, "AGENT_CANCELLED", "A conexão do turno foi encerrada.")
            if turn.task in done:
                return turn.task.result()
            raise AgentError(503, "AGENT_TIMEOUT", "O agente não respondeu dentro do prazo.")
        except TurnCancelled as error:
            raise AgentError(503, "AGENT_STOPPING", "O agente está encerrando o atendimento.") from error
        except ToolLimitExceeded as error:
            raise AgentError(503, "AGENT_LIMIT", str(error)) from error
        except BedrockError as error:
            raise AgentError(503, error.code, str(error)) from error
        finally:
            disconnect.cancel()
            await asyncio.gather(disconnect, return_exceptions=True)
            # A vaga só é liberada depois do SDK fechar a sessão e recolher o subprocesso.
            await turn.finish()

    return app


def main() -> None:
    check_simulated_clients()
    secret = os.environ.get(INTERNAL_TOKEN_SECRET_VARIABLE)
    if not secret:
        raise RuntimeError(f"Variavel de ambiente ausente: {INTERNAL_TOKEN_SECRET_VARIABLE}")
    pdm_path = os.environ.get(PDM_PATH_VARIABLE, DEFAULT_PDM_PATH)
    app = create_app(
        load_pdm(pdm_path),
        secret,
        lambda caller: mcp_client.connect(pdm_path, caller=caller_to_environment(caller)),
    )
    uvicorn.run(
        app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8001")), workers=1, timeout_graceful_shutdown=5
    )
