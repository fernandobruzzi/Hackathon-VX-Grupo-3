"""Fluxo comum: orçamento, tentativas, validação do esquema e registro de cada chamada."""

import time

from domain.contracts import LlmCall, LlmResult
from domain.llm import LlmBudget, LlmError, LlmSettings, check_schema, log_call, validate_structured


class TransientLlmError(Exception):
    """Falha que pode passar numa nova tentativa (limite de taxa, timeout, indisponibilidade)."""


class LlmBase:
    name: str
    model: str
    simulated = False

    def __init__(self, settings: LlmSettings | None = None, budget: LlmBudget | None = None) -> None:
        self.settings = settings or LlmSettings.from_env()
        self.budget = budget or LlmBudget(self.settings.max_calls)

    def complete(self, *, system: str, prompt: str, schema: dict, tool_name: str, prompt_version: str) -> LlmResult:
        if not prompt_version.strip():
            raise ValueError("prompt_version é obrigatório para rastrear a resposta")
        check_schema(schema)
        started, attempts = time.monotonic(), 0
        while True:
            self.budget.spend()
            attempts += 1
            try:
                raw, input_tokens, output_tokens = self._invoke(system, prompt, schema, tool_name)
                break
            except TransientLlmError as error:
                if attempts >= self.settings.max_attempts:
                    raise LlmError("LLM_UNAVAILABLE", str(error)) from error
        data = validate_structured(schema, raw)
        call = LlmCall(
            repository=self.name,
            model=self.model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round((time.monotonic() - started) * 1000),
            attempts=attempts,
            simulated=self.simulated,
        )
        log_call(call)
        return LlmResult(data, call)

    def _invoke(self, system: str, prompt: str, schema: dict, tool_name: str) -> tuple[object, int, int]:
        raise NotImplementedError
