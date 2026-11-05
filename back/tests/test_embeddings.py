import io
import json

import pytest

from repositories.embeddings import REPOSITORIES, get_embedding_repository
from repositories.embeddings.bedrock_titan_v1 import BedrockTitanV1EmbeddingRepository
from repositories.embeddings.ollama_nomic_v1 import OllamaNomicV1EmbeddingRepository
from repositories.embeddings.simulated_v1 import SimulatedV1EmbeddingRepository


def test_without_configuration_search_uses_no_embeddings(monkeypatch):
    monkeypatch.delenv("EMBEDDING_REPOSITORY", raising=False)
    assert get_embedding_repository() is None
    assert get_embedding_repository("none") is None


def test_unknown_repository_lists_options():
    with pytest.raises(ValueError, match="simulated_v1"):
        get_embedding_repository("nao_existe")


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_signature_names_model_and_dimension(name):
    repository_class = REPOSITORIES[name]
    assert repository_class.dimensions == 512
    assert repository_class.name in f"{repository_class.name}:{repository_class.model}:512"


def test_simulated_vectors_are_stable_normalized_and_labeled():
    repository = SimulatedV1EmbeddingRepository()
    first, again, other = repository.embed(["FILTRO LF9009", "FILTRO LF9009", "PARAFUSO M12"], query=False)
    assert first == again
    assert len(first) == 512
    assert abs(sum(v * v for v in first) - 1) < 1e-9
    assert first != other
    assert repository.simulated is True


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_ollama_uses_prefixes_and_cuts_to_512(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data)
        sent.append(payload["input"])
        return _FakeResponse(json.dumps({"embeddings": [[1.0] * 768 for _ in payload["input"]]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    repository = OllamaNomicV1EmbeddingRepository("http://ollama")
    vectors = repository.embed(["a", "b"], query=True)
    assert sent == [["search_query: a", "search_query: b"]]
    assert len(vectors[0]) == 512
    repository.embed(["c"], query=False)
    assert sent[-1] == ["search_document: c"]


def test_titan_requests_512_normalized_dimensions():
    class Client:
        def invoke_model(self, modelId, body):
            self.request = (modelId, json.loads(body))
            return {"body": io.BytesIO(json.dumps({"embedding": [0.0] * 512}).encode())}

    client = Client()
    vectors = BedrockTitanV1EmbeddingRepository(client).embed(["FILTRO"], query=True)
    assert client.request == (
        "amazon.titan-embed-text-v2:0",
        {"inputText": "FILTRO", "dimensions": 512, "normalize": True},
    )
    assert len(vectors[0]) == 512
