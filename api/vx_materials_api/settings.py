"""Configuracao da API por variaveis de ambiente."""

import os
from pathlib import Path


def front_dist_dir() -> Path | None:
    """Pasta do build estatico do front, quando configurada."""
    value = os.environ.get("FRONT_DIST_DIR")
    return Path(value) if value else None


def api_port() -> int:
    return int(os.environ.get("API_PORT", "8000"))
