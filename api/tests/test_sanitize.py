"""Saneamento de ponta a ponta no banco real, com a credencial batch_user."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from clients.storage import LocalObjectStore
from pipelines.sanitize import run_sanitize
from vx_materials_api.bootstrap import bootstrap

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def sanitized(migrated_url, tmp_path_factory):
    admin = create_engine(migrated_url)
    with admin.begin() as connection:
        connection.execute(
            text("TRUNCATE datasets, reference_versions, materials_master, sanitization_proposals CASCADE")
        )
        connection.execute(text("ALTER ROLE api_user LOGIN PASSWORD 'sanitize_test'"))
        connection.execute(text("ALTER ROLE batch_user LOGIN PASSWORD 'sanitize_test'"))
    url = make_url(migrated_url)
    api = create_engine(url.set(username="api_user", password="sanitize_test"))
    bootstrap(KIT, api, LocalObjectStore(tmp_path_factory.mktemp("storage")))
    api.dispose()
    batch_url = url.set(username="batch_user", password="sanitize_test").render_as_string(hide_password=False)
    first = run_sanitize(PDM, database_url=batch_url)
    second = run_sanitize(PDM, database_url=batch_url)
    yield first, second, admin, batch_url
    admin.dispose()


def scalar(engine, query):
    with engine.connect() as connection:
        return connection.execute(text(query)).scalar_one()


def test_batch_saves_proposals_with_members_conflicts_and_versions(sanitized):
    first, _, admin, _ = sanitized
    assert first["inserted"] == first["proposals"] > 1000
    assert scalar(admin, "SELECT count(*) FROM sanitization_proposals") == first["proposals"]
    with admin.connect() as connection:
        row = connection.execute(
            text(
                "SELECT p.proposal_type, p.status, p.members, p.changeset, p.fiscal_review_status, "
                "m.material_code FROM sanitization_proposals p JOIN materials_master m ON m.id = p.primary_material_id "
                "WHERE jsonb_array_length(p.changeset->'conflicts') > 0 LIMIT 1"
            )
        ).one()
    assert (row[0], row[1]) == ("MERGE", "PENDING")
    assert row[3]["primary_material_code"] == row[5]
    assert row[3]["conflicts"]
    assert all(member["observed_version"] == 1 and member["inventory"] for member in row[2])


def test_running_again_duplicates_nothing(sanitized):
    first, second, admin, _ = sanitized
    assert second["inserted"] == 0
    assert second["proposals"] == first["proposals"]
    assert scalar(admin, "SELECT count(*) FROM sanitization_proposals") == first["proposals"]


def test_master_data_stays_untouched(sanitized):
    _, _, admin, _ = sanitized
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE version <> 1 OR is_canonical") == 0
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE status = 'ATIVO'") == 20014


def test_only_active_materials_are_proposed(sanitized):
    _, _, admin, _ = sanitized
    query = (
        "SELECT count(*) FROM sanitization_proposals p, jsonb_array_elements(p.members) member "
        "WHERE member->>'status' <> 'ATIVO'"
    )
    assert scalar(admin, query) == 0


def test_batch_credential_cannot_change_master(sanitized):
    *_, batch_url = sanitized
    engine = create_engine(batch_url)
    with engine.connect() as connection:
        with pytest.raises(DBAPIError, match="permission denied"):
            connection.execute(text("UPDATE materials_master SET status = 'OBSOLETO'"))
    engine.dispose()


def test_packaging_units_are_flagged_in_saved_proposals(sanitized):
    first, _, admin, _ = sanitized
    assert first["conflicts"]["UNIDADE_SEM_FATOR"] > 0
    query = "SELECT count(*) FROM sanitization_proposals WHERE changeset::text LIKE '%UNIDADE_SEM_FATOR%'"
    assert scalar(admin, query) == first["conflicts"]["UNIDADE_SEM_FATOR"]
