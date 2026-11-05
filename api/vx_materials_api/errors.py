"""Erros padronizados da API, no formato `ApiError` do contrato."""

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def request_id(request: Request) -> str:
    """Um identificador por requisição, repassado ao Agent e devolvido nos erros."""
    if not hasattr(request.state, "request_id"):
        request.state.request_id = f"req-{uuid.uuid4().hex[:12]}"
    return request.state.request_id


def _body(request: Request, code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id(request), "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def problem(request: Request, error: ApiProblem) -> JSONResponse:
        return JSONResponse(_body(request, error.code, error.message, error.details), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_payload(request: Request, error: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(part) for part in item["loc"]) for item in error.errors()]
        return JSONResponse(_body(request, "VALIDATION_ERROR", "Payload inválido.", {"fields": fields}), 422)
