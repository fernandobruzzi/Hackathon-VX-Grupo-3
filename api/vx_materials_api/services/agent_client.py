"""Cliente HTTP do Agent. Cada turno leva um token interno novo, nunca o token do usuário."""

from typing import Any

import httpx
from pydantic import ValidationError

from vx_materials_api.schemas.chat import AgentRunResponse

# Um pouco acima do prazo do Agent, para receber o erro dele em vez de cortar a conexão.
TIMEOUT_SECONDS = 50.0


class AgentUnavailable(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AgentClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url
        self._transport = transport

    async def run(self, payload: dict[str, Any], token: str, request_id: str) -> AgentRunResponse:
        headers = {"Authorization": f"Bearer {token}", "X-Request-ID": request_id}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, transport=self._transport, timeout=TIMEOUT_SECONDS
            ) as client:
                response = await client.post("/internal/v1/chat/run", json=payload, headers=headers)
        except httpx.HTTPError as error:
            raise AgentUnavailable("AGENT_UNAVAILABLE", "O agente não está acessível.") from error
        if response.status_code != 200:
            code = _error_code(response) or "AGENT_ERROR"
            raise AgentUnavailable(code, f"O agente recusou o turno ({response.status_code}).")
        try:
            return AgentRunResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise AgentUnavailable("AGENT_INVALID_RESPONSE", "O agente devolveu uma resposta inválida.") from error


def _error_code(response: httpx.Response) -> str | None:
    try:
        return response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None
