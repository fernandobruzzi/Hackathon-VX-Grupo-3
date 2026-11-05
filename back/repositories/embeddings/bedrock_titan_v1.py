"""Titan Text Embeddings V2 no Bedrock, com 512 dimensões, como a arquitetura define."""

import json

import boto3

from repositories.embeddings._base import EmbeddingBase


class BedrockTitanV1EmbeddingRepository(EmbeddingBase):
    name = "bedrock_titan_v1"
    model = "amazon.titan-embed-text-v2:0"

    def __init__(self, client=None) -> None:
        self._client = client or boto3.client("bedrock-runtime")

    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        vectors = []
        for text in texts:
            body = json.dumps({"inputText": text, "dimensions": self.dimensions, "normalize": True})
            response = self._client.invoke_model(modelId=self.model, body=body)
            vectors.append(json.loads(response["body"].read())["embedding"])
        return vectors
