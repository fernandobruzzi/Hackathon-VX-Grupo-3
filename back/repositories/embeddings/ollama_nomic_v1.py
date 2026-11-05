"""nomic-embed-text v1.5 em um container Ollama local, cortado para 512 dimensões.

O modelo foi treinado para aceitar corte das dimensões (Matryoshka), e pede prefixos diferentes
para documentos e consultas. Os resultados não equivalem aos do Titan usado na AWS.
"""

import json
import os
import urllib.request

from repositories.embeddings._base import EmbeddingBase, normalized

_BATCH = 64


class OllamaNomicV1EmbeddingRepository(EmbeddingBase):
    name = "ollama_nomic_v1"
    model = "nomic-embed-text:v1.5"

    def __init__(self, url: str | None = None, timeout: float = 120) -> None:
        self._url = (url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self._timeout = timeout

    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        prefix = "search_query: " if query else "search_document: "
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            batch = [prefix + text for text in texts[start : start + _BATCH]]
            body = json.dumps({"model": self.model, "input": batch}).encode()
            request = urllib.request.Request(
                f"{self._url}/api/embed", data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                result = json.loads(response.read())
            vectors.extend(normalized(vector[: self.dimensions]) for vector in result["embeddings"])
        return vectors
