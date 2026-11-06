"""Configuracao da API por variaveis de ambiente."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from domain.runtime import check_simulated_clients


def front_dist_dir() -> Path | None:
    """Pasta do build estatico do front, quando configurada."""
    value = os.environ.get("FRONT_DIST_DIR")
    return Path(value) if value else None


def api_port() -> int:
    return int(os.environ.get("API_PORT", "8000"))


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variavel de ambiente ausente: {name}")
    return value


def database_url() -> str:
    """Conexao da aplicacao, com a credencial api_user."""
    return _required("DATABASE_URL")


def migration_database_url() -> str:
    """Conexao das migracoes, com a credencial migration_user."""
    return _required("MIGRATION_DATABASE_URL")


def data_dir() -> str:
    """Pasta com os arquivos originais do kit."""
    return os.environ.get("DATA_DIR", "data/desafio01")


LOCAL_ENV = "local"


def app_env() -> str:
    """Ambiente da aplicação. Sem a variável, assume implantado: atalhos locais ficam proibidos."""
    return os.environ.get("APP_ENV", "production")


def local_test_session_enabled() -> bool:
    return any(
        os.environ.get(key, "false").lower() == "true" for key in ("LOCAL_TEST_SESSION", "ENABLE_LOCAL_TEST_SESSIONS")
    )


def check_local_shortcuts() -> None:
    """Impede que a sessão de teste suba fora do ambiente local."""
    check_simulated_clients()
    deployed = any(
        os.environ.get(key)
        for key in (
            "AWS_EXECUTION_ENV",
            "ECS_CONTAINER_METADATA_URI",
            "ECS_CONTAINER_METADATA_URI_V4",
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        )
    )
    if local_test_session_enabled() and (app_env() != LOCAL_ENV or deployed):
        raise RuntimeError("Sessões de teste exigem APP_ENV=local e não podem rodar na AWS")
    origin = urlsplit(application_origin())
    if local_test_session_enabled() and (
        origin.scheme not in {"http", "https"}
        or origin.hostname not in {"localhost", "127.0.0.1", "::1"}
        or origin.username
        or origin.password
        or origin.path
        or origin.query
        or origin.fragment
    ):
        raise RuntimeError("Sessão local exige APP_ORIGIN de loopback")


def application_origin() -> str:
    return os.environ.get("APP_ORIGIN", "http://localhost:8000").rstrip("/")


def agent_url() -> str:
    return os.environ.get("AGENT_URL", "http://localhost:8001")


def agent_internal_token_secret() -> str:
    """Segredo compartilhado com o Agent para assinar o token interno de cada turno."""
    return _required("AGENT_INTERNAL_TOKEN_SECRET")


def batch_runner() -> str | None:
    """Como a API dispara o batch: `local_process` localmente. Sem valor, iniciar job responde 503."""
    return os.environ.get("BATCH_RUNNER") or None


def batch_database_url() -> str:
    """Conexão que o batch disparado localmente recebe, com a credencial batch_user."""
    return _required("BATCH_DATABASE_URL")


def batch_heartbeat_timeout_seconds() -> int:
    """Sem heartbeat por mais que isso, o job é dado como parado."""
    return int(os.environ.get("BATCH_HEARTBEAT_TIMEOUT_SECONDS", "120"))


def demo_mode_enabled() -> bool:
    """Troca rápida de persona no pitch. Desligada por padrão; nunca concede papel por si só."""
    return os.environ.get("DEMO_MODE", "false").lower() == "true"


def demo_accounts() -> dict[str, str]:
    """Persona → e-mail da conta Cognito de demonstração, em `PERSONA=email,PERSONA=email`."""
    from vx_materials_api.security.permissions import PERSONA_ROLES

    accounts = {}
    for item in os.environ.get("DEMO_ACCOUNTS", "").split(","):
        if not item.strip():
            continue
        persona, _, email = item.partition("=")
        persona, email = persona.strip(), email.strip().lower()
        if persona not in PERSONA_ROLES or not email:
            raise RuntimeError(f"DEMO_ACCOUNTS inválido: {item.strip()!r}")
        accounts[persona] = email
    if demo_mode_enabled() and not accounts:
        raise RuntimeError("DEMO_MODE exige DEMO_ACCOUNTS com as contas de demonstração")
    return accounts
