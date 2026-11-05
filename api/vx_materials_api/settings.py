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
