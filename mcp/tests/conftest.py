"""Banco de busca compartilhado: kit carregado e índice do batch, como em produção."""

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from clients.storage import LocalObjectStore
from pipelines.search_index import run_index
from vx_materials_api.bootstrap import bootstrap
from vx_materials_api.db.cli import alembic_config

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="session")
def database():
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("Defina TEST_DATABASE_URL para rodar os testes de busca")
    url = make_url(base).set(database="vx_mcp_search_test")
    admin_conninfo = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin_conninfo, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{url.database}"')
    migration = url.render_as_string(hide_password=False)
    command.upgrade(alembic_config(migration), "head")
    admin = create_engine(migration)
    with admin.begin() as connection:
        for role in ("api_user", "batch_user", "mcp_reader"):
            connection.execute(text(f"ALTER ROLE {role} LOGIN PASSWORD 'search_test'"))

    def login(role):
        return url.set(username=role, password="search_test").render_as_string(hide_password=False)

    api = create_engine(login("api_user"))
    bootstrap(KIT, api, LocalObjectStore(Path(os.environ.get("TMPDIR", "/tmp")) / "vx-search-test-storage"))
    api.dispose()
    indexed = run_index(PDM, database_url=login("batch_user"))
    yield {"admin": admin, "reader": login("mcp_reader"), "indexed": indexed}
    admin.dispose()
