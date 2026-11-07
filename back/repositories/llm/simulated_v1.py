"""Modelo simulado, sem rede: devolve a menor resposta que o esquema aceita, ou uma resposta fixa por
ferramenta. Serve para testes e execução local; não mede qualidade e é recusado fora de APP_ENV=local."""

from repositories.llm._base import LlmBase


class SimulatedV1LlmRepository(LlmBase):
    name = "simulated_v1"
    model = "simulated-minimal-v1"
    simulated = True

    def __init__(self, responses: dict[str, object] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.responses = dict(responses or {})

    def _invoke(self, system: str, prompt: str, schema: dict, tool_name: str) -> tuple[object, int, int]:
        data = self.responses[tool_name] if tool_name in self.responses else minimal_instance(schema)
        # Estimativa grosseira de tokens, só para exercitar o registro.
        return data, (len(system) + len(prompt)) // 4, len(str(data)) // 4


def minimal_instance(schema: dict) -> object:
    """Valor mínimo: nulo quando permitido, primeiro valor de enum, campos obrigatórios só."""
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = schema[key]
            nullable = [o for o in options if o.get("type") == "null"]
            return minimal_instance((nullable or options)[0])
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = "null" if "null" in kind else kind[0]
    if kind == "null":
        return None
    if kind == "object":
        properties = schema.get("properties", {})
        return {name: minimal_instance(properties.get(name, {})) for name in schema.get("required", [])}
    if kind == "array":
        return [minimal_instance(schema.get("items", {})) for _ in range(schema.get("minItems", 0))]
    if kind == "string":
        return "x" * schema.get("minLength", 0)
    if kind in ("integer", "number"):
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    return None
