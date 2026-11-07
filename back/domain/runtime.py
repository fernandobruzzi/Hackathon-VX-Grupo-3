"""Barreira de inicialização para simulações que só podem existir localmente."""

import os

AWS_RUNTIME_VARIABLES = (
    "AWS_EXECUTION_ENV",
    "ECS_CONTAINER_METADATA_URI",
    "ECS_CONTAINER_METADATA_URI_V4",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
)


# Variáveis que selecionam um cliente externo; o valor `simulated_v1` só vale localmente.
SIMULATED_SELECTORS = ("EMBEDDING_REPOSITORY", "LLM_REPOSITORY")


def check_simulated_clients() -> None:
    selected = [name for name in SIMULATED_SELECTORS if os.environ.get(name, "").strip() == "simulated_v1"]
    if not selected:
        return
    if os.environ.get("APP_ENV", "production") != "local" or any(os.environ.get(key) for key in AWS_RUNTIME_VARIABLES):
        raise RuntimeError(f"{selected[0]}=simulated_v1 exige APP_ENV=local fora de runtime AWS")
