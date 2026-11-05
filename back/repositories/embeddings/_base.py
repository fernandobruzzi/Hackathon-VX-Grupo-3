import math

DIMENSIONS = 512


def normalized(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class EmbeddingBase:
    name = ""
    model = ""
    dimensions = DIMENSIONS
    simulated = False

    @property
    def signature(self) -> str:
        return f"{self.name}:{self.model}:{self.dimensions}"
