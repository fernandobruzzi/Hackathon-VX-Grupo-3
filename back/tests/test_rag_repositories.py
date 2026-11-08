"""Contrato de todos os algoritmos RAG: escopo, fallback e projeção sem autoridade de identidade."""

import pytest

from domain.contracts import PdmCatalog, RagMaterial, RagScope
from domain.rag_context import build_context, serialize_context
from repositories.rag import REPOSITORIES, get_rag_repository


class Source:
    version = "index-contract-v1"

    def retrieve(self, query, class_id, scope, limit, *, vector, require_embedding):
        # Uma fonte imperfeita não pode passar por cima da projeção autorizada.
        return [
            RagMaterial(tenant, frozenset({center}), code, 1, "PARAFUSO", None, {}, None, "INDEX_PROPOSAL", False, 1.0)
            for tenant, center, code in [
                ("tenant-a", "1200", "VISIBLE"),
                ("tenant-b", "1200", "FOREIGN"),
                ("tenant-a", "9000", "HIDDEN"),
            ]
        ][:limit]


class Embedding:
    dimensions = 512
    signature = "simulated_v1:contract-test:512"

    def __init__(self, failure):
        self.failure = failure

    def embed(self, texts, *, query):
        if self.failure:
            raise OSError("Modelo indisponível")
        return [[1.0, *([0.0] * 511)]]


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
@pytest.mark.parametrize("mode", ["text", "vector", "failure"])
def test_registered_repository_preserves_scope_and_reports_how_context_was_retrieved(name, mode):
    repository = get_rag_repository(
        name, source=Source(), embedder=None if mode == "text" else Embedding(mode == "failure")
    )
    packet = build_context(
        PdmCatalog("pdm-test", "a" * 64, {}), repository, RagScope("tenant-a", frozenset({"1200"})), "parafuso"
    )
    assert packet["repository"] == name and packet["index_version"] == Source.version
    payload = serialize_context(packet)
    assert "VISIBLE" in payload and "FOREIGN" not in payload and "HIDDEN" not in payload
    assert all(item["content"].get("identity_verified") is False for item in packet["items"])
    expected = {
        "text": "FULL_TEXT_NO_EMBEDDINGS",
        "vector": Embedding.signature,
        "failure": "FULL_TEXT_EMBEDDING_UNAVAILABLE",
    }
    assert packet["retrieval"] == expected[mode]


def test_unknown_repository_is_refused_instead_of_silently_changing_algorithm():
    with pytest.raises(ValueError, match="desconhecido"):
        get_rag_repository("unknown", source=Source())
