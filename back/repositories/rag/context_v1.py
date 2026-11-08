"""Recuperação por embedding com fallback textual explícito e uma chamada de modelo por consulta."""

import math

from domain.contracts import EmbeddingRepository, RagCandidateSource, RagMaterial, RagScope


class ContextV1RagRepository:
    name = "context_v1"

    def __init__(self, source: RagCandidateSource, embedder: EmbeddingRepository | None = None):
        self.source, self.embedder, self.version = source, embedder, source.version
        self.retrieval = "FULL_TEXT_NO_EMBEDDINGS"

    def retrieve(self, query: str, class_id: str | None, scope: RagScope, limit: int) -> list[RagMaterial]:
        vector = None
        if self.embedder is not None:
            try:
                vector = self.embedder.embed([query], query=True)[0]
                if len(vector) != self.embedder.dimensions or not all(math.isfinite(value) for value in vector):
                    raise ValueError("Vetor inválido")
                self.retrieval = self.embedder.signature
            except Exception:  # noqa: BLE001 - falha do modelo não comprova ausência de materiais
                vector = None
                self.retrieval = "FULL_TEXT_EMBEDDING_UNAVAILABLE"
        return self.source.retrieve(
            query, class_id, scope, limit, vector=vector, require_embedding=self.embedder is not None
        )
