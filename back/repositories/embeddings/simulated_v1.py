"""Embeddings simulados por hashing de trigramas, sem rede. Servem para testes, não medem qualidade."""

import hashlib

from repositories.embeddings._base import EmbeddingBase, normalized


class SimulatedV1EmbeddingRepository(EmbeddingBase):
    name = "simulated_v1"
    model = "hashing-trigrams-v1"
    simulated = True

    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        padded = f"  {text.upper()}  "
        for index in range(len(padded) - 2):
            digest = hashlib.blake2b(padded[index : index + 3].encode(), digest_size=8).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[slot] += 1.0 if digest[4] % 2 else -1.0
        return normalized(vector)
