"""Busca híbrida com embeddings: full-text e vizinhos no pgvector, unidos por fusão de posições.

Embeddings só encontram candidatos. Como o texto, podem aproximar M12 de M14 ou referências
parecidas; quem diz se é o mesmo item continua sendo a identidade do PDM.
"""

from collections import defaultdict

from vx_materials_mcp.repositories.search.hybrid_v1 import (
    _TEXT_CANDIDATES,
    _TEXT_SCORE_CEILING,
    HybridV1SearchRepository,
)

# Constante usual da fusão por posição recíproca (RRF).
_RRF_K = 60


class HybridEmbeddingsV1SearchRepository(HybridV1SearchRepository):
    name = "hybrid_embeddings_v1"

    def _similar_rows(self, query, attributes, class_id):
        if self._embedder is None:
            raise ValueError("hybrid_embeddings_v1 precisa de EMBEDDING_REPOSITORY")
        text_rows = super()._similar_rows(query, attributes, class_id)
        text = " ".join([query.query, *attributes.values()])
        vector = self._embedder.embed([text], query=True)[0]
        vector_rows = self._catalog.nearest(vector, self._version, class_id, _TEXT_CANDIDATES)
        fused: dict[str, float] = defaultdict(float)
        by_id = {}
        for ranking in (text_rows, vector_rows):
            for position, row in enumerate(ranking, start=1):
                fused[row["id"]] += 1 / (_RRF_K + position)
                by_id.setdefault(row["id"], row)
        best = max(fused.values(), default=1) or 1
        return [{**by_id[key], "rank": score / best * _TEXT_SCORE_CEILING} for key, score in fused.items()]
