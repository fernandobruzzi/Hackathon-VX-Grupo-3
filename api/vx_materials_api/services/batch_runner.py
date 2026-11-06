"""Disparo da task de batch. A API passa só o manifesto: nunca o token nem a sessão do usuário.

`BATCH_RUNNER` escolhe a implementação. Localmente, `local_process` roda `vx-back sanitize` como
subprocesso da API. Na AWS, o disparo por ECS RunTask entra aqui com a mesma interface (#6).
"""

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from vx_materials_api import settings
from vx_materials_api.services.ecs_batch_runner import EcsFargateRunner

# Variáveis que o batch pode receber da API. Todo o resto do ambiente, incluindo segredos da API,
# fica de fora: o batch usa a própria credencial do banco.
INHERITED_VARIABLES = (
    "APP_ENV",
    "CANDIDATE_REPOSITORY",
    "CLASSIFICATION_REPOSITORY",
    "CORRECTION_REPOSITORY",
    "EXTRACTION_REPOSITORY",
    "HOME",
    "LANG",
    "NCM_SNAPSHOT_VERSION",
    "NORMALIZATION_REPOSITORY",
    "PATH",
    "PDM_WORKBOOK_PATH",
    "S3_BUCKET",
    "STORAGE_BACKEND",
    "STORAGE_LOCAL_DIR",
    "AWS_REGION",
)


@dataclass(frozen=True)
class LaunchRequest:
    job_id: str
    manifest_key: str
    attempt_id: str | None = None


class BatchRunner(Protocol):
    name: str

    def launch(self, request: LaunchRequest) -> str:
        """Dispara a task e devolve uma referência a ela (pid local ou ARN)."""
        ...


class LocalProcessRunner:
    """Roda o batch como subprocesso. Só para ambiente local: a API recusa usá-lo fora dele."""

    name = "local_process"

    def __init__(self, popen: Callable[..., subprocess.Popen] = subprocess.Popen) -> None:
        self._popen = popen

    def command(self, request: LaunchRequest) -> list[str]:
        return [
            sys.executable,
            "-m",
            "cli",
            "sanitize",
            "--job-id",
            request.job_id,
            "--manifest-key",
            request.manifest_key,
        ]

    def environment(self) -> dict[str, str]:
        env = {name: os.environ[name] for name in INHERITED_VARIABLES if name in os.environ}
        env["DATABASE_URL"] = settings.batch_database_url()
        env["BATCH_HEARTBEAT_TIMEOUT_SECONDS"] = str(settings.batch_heartbeat_timeout_seconds())
        return env

    def launch(self, request: LaunchRequest) -> str:
        if settings.app_env() != settings.LOCAL_ENV:
            raise RuntimeError("BATCH_RUNNER=local_process só pode ser usado com APP_ENV=local")
        process = self._popen(
            self.command(request),
            env=self.environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"local-pid:{process.pid}"


RUNNERS: dict[str, Callable[[], BatchRunner]] = {
    EcsFargateRunner.name: EcsFargateRunner,
    LocalProcessRunner.name: LocalProcessRunner,
}


def get_batch_runner(name: str | None = None) -> BatchRunner | None:
    """Sem runner configurado, devolve None e a API responde que o batch está indisponível."""
    name = name or settings.batch_runner()
    if name is None:
        return None
    if name not in RUNNERS:
        raise RuntimeError(f"BATCH_RUNNER desconhecido: {name}. Opções: {', '.join(sorted(RUNNERS))}")
    return RUNNERS[name]()
