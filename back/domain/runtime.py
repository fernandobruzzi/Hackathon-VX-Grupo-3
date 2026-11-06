"""Barreira de inicialização para simulações que só podem existir localmente."""

import os

AWS_RUNTIME_VARIABLES = (
    "AWS_EXECUTION_ENV",
    "ECS_CONTAINER_METADATA_URI",
    "ECS_CONTAINER_METADATA_URI_V4",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
)


def check_simulated_clients() -> None:
    if os.environ.get("EMBEDDING_REPOSITORY") != "simulated_v1":
        return
    if os.environ.get("APP_ENV", "production") != "local" or any(os.environ.get(key) for key in AWS_RUNTIME_VARIABLES):
        raise RuntimeError("EMBEDDING_REPOSITORY=simulated_v1 exige APP_ENV=local fora de runtime AWS")
