import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from approval_fixtures import approval_case as approval_case
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from vx_materials_api.db.cli import alembic_config
from vx_materials_api.db.models import Base

TEST_URL = os.environ.get("TEST_DATABASE_URL")


def _libpq(url) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def database_url():
    """Banco descartável, recriado do zero. Sem TEST_DATABASE_URL, os testes de banco são pulados."""
    if not TEST_URL:
        pytest.skip("Defina TEST_DATABASE_URL para rodar os testes de banco")
    url = make_url(TEST_URL)
    if not url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL precisa apontar para um banco terminado em _test: ele é apagado")
    with psycopg.connect(_libpq(url.set(database="postgres")), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{url.database}"')
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def migrated_url(database_url):
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest.fixture
def connection(migrated_url):
    """Conexão como migration_user, desfeita ao final de cada teste."""
    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        transaction = conn.begin()
        yield conn
        transaction.rollback()
    engine.dispose()


@pytest.fixture(scope="session")
def small_sanitization_kit(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    kit = tmp_path_factory.mktemp("sanitization") / "kit"
    extra_codes = (
        "10109628",
        "10436289",  # Correções de unidade.
        "12352505",
        "11416625",  # Um material e a fonte de seu enriquecimento.
    )
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "ci_smoke_kit.py"),
            str(root / "data" / "desafio01"),
            str(kit),
            *(arg for code in extra_codes for arg in ("--material-code", code)),
        ],
        check=True,
    )
    return kit


@pytest.fixture(scope="module")
def order_database(migrated_url):
    """Pedidos criam seus dados; não herdam o kit carregado por outro módulo."""
    engine = create_engine(migrated_url)
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    engine.dispose()


@pytest.fixture
def tenant():
    return uuid.uuid4()


@pytest.fixture
def add_material(connection, tenant):
    def add(code, *, status="ATIVO", canonical=False, identity=None, tenant_id=None, target=None):
        return connection.execute(
            text(
                "INSERT INTO materials_master (tenant_id, source_system, material_code, status, is_canonical, "
                "identity_key, active_code_target) VALUES (:t, 'ERP', :c, :s, :k, :i, :g) RETURNING id"
            ),
            {"t": tenant_id or tenant, "c": code, "s": status, "k": canonical, "i": identity, "g": target},
        ).scalar_one()

    return add
