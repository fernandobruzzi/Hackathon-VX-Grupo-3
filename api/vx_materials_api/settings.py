"""Configuracao da API por variaveis de ambiente."""

import os
from pathlib import Path


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
    return os.environ.get("LOCAL_TEST_SESSION", "false").lower() == "true"


def check_local_shortcuts() -> None:
    """Impede que a sessão de teste suba fora do ambiente local."""
    if local_test_session_enabled() and app_env() != LOCAL_ENV:
        raise RuntimeError("LOCAL_TEST_SESSION só pode ser ativada com APP_ENV=local")


def agent_url() -> str:
    return os.environ.get("AGENT_URL", "http://localhost:8001")


def agent_internal_token_secret() -> str:
    """Segredo compartilhado com o Agent para assinar o token interno de cada turno."""
    return _required("AGENT_INTERNAL_TOKEN_SECRET")
