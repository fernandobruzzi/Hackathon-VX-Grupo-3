"""Titan Text Embeddings V2 no Bedrock, com 512 dimensões, como a arquitetura define."""

import json
import math
import os
from contextlib import closing

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from repositories.embeddings._base import EmbeddingBase


class TitanEmbeddingError(RuntimeError):
    """A chamada falhou ou retornou dados incompatíveis com o índice."""


class BedrockTitanV1EmbeddingRepository(EmbeddingBase):
    name = "bedrock_titan_v1"
    model = "amazon.titan-embed-text-v2:0"

    def __init__(self, client=None) -> None:
        self._client = client
        self.input_tokens = 0

    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector, tokens = self._invoke(text)
            self.input_tokens += tokens
            vectors.append(vector)
        return vectors

    def _invoke(self, text: str) -> tuple[list[float], int]:
        try:
            if self._client is None:
                self._client = boto3.client(
                    "bedrock-runtime",
                    region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
                    config=Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1}),
                )
            body = json.dumps({"inputText": text, "dimensions": self.dimensions, "normalize": True})
            response = self._client.invoke_model(
                modelId=self.model, body=body, contentType="application/json", accept="application/json"
            )
            with closing(response["body"]) as stream:
                result = json.load(stream)
            vector, tokens = result["embedding"], result["inputTextTokenCount"]
            if (
                not isinstance(vector, list)
                or len(vector) != self.dimensions
                or not all(type(value) in (int, float) and math.isfinite(value) for value in vector)
                or not any(vector)
                or type(tokens) is not int
                or tokens < 0
            ):
                raise ValueError("Resposta de embeddings inválida")
        except (BotoCoreError, ClientError, OSError, KeyError, ValueError, TypeError, OverflowError) as error:
            raise TitanEmbeddingError("O Titan não forneceu um embedding válido.") from error
        return vector, tokens
