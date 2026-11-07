"""Claude no Bedrock pela API Converse. O modelo vem de BEDROCK_LLM_MODEL_ID (padrão: perfil de
inferência dos EUA do Claude Sonnet 5) e a região de AWS_REGION; credenciais pela cadeia padrão do SDK."""

import json
import os

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ConnectionError, NoRegionError, ReadTimeoutError

from domain.llm import DEFAULT_BEDROCK_MODEL, LlmError
from repositories.llm._base import LlmBase, TransientLlmError

_TRANSIENT_CODES = {
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
    "ServiceUnavailableException",
    "ThrottlingException",
}
_REFUSAL_STOPS = {"guardrail_intervened", "content_filtered"}


class BedrockV1LlmRepository(LlmBase):
    name = "bedrock_v1"

    def __init__(self, client=None, model: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model = model or os.environ.get("BEDROCK_LLM_MODEL_ID", "").strip() or DEFAULT_BEDROCK_MODEL
        self._client = client

    def _bedrock(self):
        if self._client is None:
            try:
                # As tentativas são controladas aqui, para cada uma contar no orçamento.
                self._client = boto3.session.Session().client(
                    "bedrock-runtime",
                    region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
                    config=Config(
                        connect_timeout=min(5, self.settings.timeout_seconds),
                        read_timeout=self.settings.timeout_seconds,
                        retries={"total_max_attempts": 1},
                    ),
                )
            except NoRegionError as error:
                raise LlmError("LLM_NOT_CONFIGURED", "defina AWS_REGION") from error
        return self._client

    def _invoke(self, system: str, prompt: str, schema: dict, tool_name: str) -> tuple[object, int, int]:
        parameters = {
            "modelId": self.model,
            "system": [{"text": f"{system}\n\nResponda somente chamando a ferramenta {tool_name}."}],
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": self.settings.max_tokens},
            # Sem toolChoice forçado: modelos mais novos recusam `any`/`tool`; a ausência da ferramenta é erro.
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool_name,
                            "description": "Devolve a resposta estruturada pedida.",
                            "inputSchema": {"json": schema},
                        }
                    }
                ]
            },
        }
        try:
            response = self._bedrock().converse(**parameters)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in _TRANSIENT_CODES:
                raise TransientLlmError(code) from error
            raise LlmError("LLM_REQUEST_REJECTED", code) from error
        except (ReadTimeoutError, ConnectionError) as error:
            raise TransientLlmError(type(error).__name__) from error
        except BotoCoreError as error:
            raise LlmError("LLM_UNAVAILABLE", type(error).__name__) from error
        return _tool_input(response, tool_name), *_usage(response)


def _tool_input(response: dict, tool_name: str) -> object:
    try:
        stop = response["stopReason"]
        blocks = response["output"]["message"]["content"]
    except (KeyError, TypeError) as error:
        raise LlmError("LLM_INVALID_RESPONSE", "formato inesperado do Converse") from error
    if stop in _REFUSAL_STOPS:
        raise LlmError("LLM_REFUSED", stop)
    if stop == "max_tokens":
        raise LlmError("LLM_TRUNCATED", "aumente LLM_MAX_TOKENS")
    uses = [block["toolUse"] for block in blocks if isinstance(block, dict) and "toolUse" in block]
    if stop != "tool_use" or len(uses) != 1 or uses[0].get("name") != tool_name:
        raise LlmError("LLM_INVALID_RESPONSE", f"esperada uma chamada de {tool_name}, stopReason={stop}")
    value = uses[0].get("input")
    # O Converse entrega objeto; alguns modelos devolvem o JSON como texto.
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise LlmError("LLM_INVALID_RESPONSE", "entrada da ferramenta não é JSON") from error
    return value


def _usage(response: dict) -> tuple[int, int]:
    usage = response.get("usage") or {}
    return int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0))
