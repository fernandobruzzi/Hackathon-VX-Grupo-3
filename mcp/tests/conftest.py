"""Banco de busca compartilhado: kit carregado e índice do batch, como em produção."""

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from clients.storage import LocalObjectStore
from pipelines.search_index import run_index
from vx_materials_api.bootstrap import bootstrap
from vx_materials_api.db.cli import alembic_config
from vx_materials_api.db.temporary_login import temporary_login

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="session")
def database(tmp_path_factory):
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("Defina TEST_DATABASE_URL para rodar os testes de busca")
    # Nome derivado do banco de teste informado: suítes paralelas com bancos diferentes não colidem.
    url = make_url(base)
    url = url.set(database=f"{url.database.removesuffix('_test')}_mcp_search_test")
    admin_conninfo = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin_conninfo, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{url.database}"')
    migration = url.render_as_string(hide_password=False)
    command.upgrade(alembic_config(migration), "head")
    admin = create_engine(migration)
    with (
        temporary_login(migration, "api_user") as api_url,
        temporary_login(migration, "batch_user") as batch_url,
        temporary_login(migration, "mcp_reader") as reader_url,
    ):
        api = create_engine(api_url)
        bootstrap(KIT, api, LocalObjectStore(tmp_path_factory.mktemp("mcp-storage")))
        api.dispose()
        indexed = run_index(PDM, database_url=batch_url)
        yield {"admin": admin, "reader": reader_url, "batch": batch_url, "indexed": indexed}
    admin.dispose()
