"""Comando `vx-db`: aplica migrações e define as senhas das credenciais SQL."""

import argparse
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url

from vx_materials_api import settings

MIGRATIONS = Path(__file__).parent / "migrations"
PASSWORD_VARIABLES = {
    "api_user": "API_DB_PASSWORD",
    "batch_user": "BATCH_DB_PASSWORD",
    "mcp_reader": "MCP_DB_PASSWORD",
}


def alembic_config(url: str | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    if url:
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def set_passwords(url: str) -> list[str]:
    """Habilita login nas credenciais com senha definida no ambiente e devolve quais mudaram."""
    conninfo = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    changed = []
    with psycopg.connect(conninfo, autocommit=True) as connection:
        for role, variable in PASSWORD_VARIABLES.items():
            password = os.environ.get(variable)
            if password:
                statement = sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
                connection.execute(statement)
                changed.append(role)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vx-db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("upgrade", help="Aplica todas as migracoes")
    commands.add_parser("set-passwords", help="Define as senhas das credenciais a partir do ambiente")
    args = parser.parse_args(argv)

    url = settings.migration_database_url()
    if args.command == "upgrade":
        command.upgrade(alembic_config(url), "head")
    else:
        print("Credenciais atualizadas:", ", ".join(set_passwords(url)) or "nenhuma")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
