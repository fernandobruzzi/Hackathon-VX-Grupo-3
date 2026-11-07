"""Regras comuns às chamadas de modelo: configuração, orçamento, validação e registro."""

import logging
import os
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from domain.contracts import LlmCall

logger = logging.getLogger("vx.llm")

DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-sonnet-5"


class LlmError(Exception):
    """Falha sem resultado utilizável. `code` é estável para relatórios e para manter o caso pendente."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


class LlmBudget:
    """Limite de chamadas de uma execução. Cada tentativa conta, porque cada uma é cobrada."""

    def __init__(self, max_calls: int) -> None:
        if max_calls < 0:
            raise ValueError("Orçamento de chamadas não pode ser negativo")
        self.max_calls, self.used = max_calls, 0

    def spend(self) -> None:
        if self.used >= self.max_calls:
            raise LlmError("LLM_BUDGET_EXHAUSTED", f"{self.max_calls} chamadas nesta execução")
        self.used += 1


@dataclass(frozen=True)
class LlmSettings:
    timeout_seconds: float = 30.0
    max_attempts: int = 2
    max_calls: int = 200
    max_tokens: int = 4096

    @classmethod
    def from_env(cls) -> "LlmSettings":
        settings = cls(
            timeout_seconds=_number("LLM_TIMEOUT_SECONDS", cls.timeout_seconds, float),
            max_attempts=_number("LLM_MAX_ATTEMPTS", cls.max_attempts, int),
            max_calls=_number("LLM_MAX_CALLS_PER_RUN", cls.max_calls, int),
            max_tokens=_number("LLM_MAX_TOKENS", cls.max_tokens, int),
        )
        if settings.timeout_seconds <= 0 or settings.max_attempts < 1 or settings.max_tokens < 1:
            raise ValueError("LLM_TIMEOUT_SECONDS, LLM_MAX_ATTEMPTS e LLM_MAX_TOKENS precisam ser positivos")
        return settings


def _number(name, default, kind):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return kind(raw)
    except ValueError:
        raise ValueError(f"{name} inválido: {raw!r}") from None


def check_schema(schema: dict) -> Draft202012Validator:
    """Esquema errado é erro de programação: falha antes de gastar uma chamada."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"Esquema inválido: {error.message}") from None
    if schema.get("type") != "object":
        raise ValueError("O esquema da resposta precisa ser um objeto")
    return Draft202012Validator(schema)


def validate_structured(schema: dict, data: object) -> dict:
    """Confere a resposta contra o esquema JSON pedido; qualquer divergência é erro."""
    validator = check_schema(schema)
    if not isinstance(data, dict):
        raise LlmError("LLM_INVALID_RESPONSE", "resposta não é um objeto")
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        where = "/".join(str(p) for p in errors[0].absolute_path) or "<raiz>"
        raise LlmError("LLM_INVALID_RESPONSE", f"{where}: {errors[0].message}")
    return data


def log_call(call: LlmCall) -> None:
    # Só metadados: prompt, resposta e credenciais nunca vão para o log.
    logger.info(
        "llm_call repository=%s model=%s prompt_version=%s input_tokens=%d output_tokens=%d "
        "latency_ms=%d attempts=%d simulated=%s",
        call.repository,
        call.model,
        call.prompt_version,
        call.input_tokens,
        call.output_tokens,
        call.latency_ms,
        call.attempts,
        call.simulated,
    )
