"""Saneamento de ponta a ponta no banco real, com a credencial batch_user."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from clients.storage import LocalObjectStore
from pipelines.full_run import run_sanitize
from vx_materials_api.bootstrap import bootstrap
from vx_materials_api.db.temporary_login import temporary_login

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def sanitized(migrated_url, tmp_path_factory):
    admin = create_engine(migrated_url)
    with admin.begin() as connection:
        connection.execute(
            text("TRUNCATE datasets, reference_versions, materials_master, sanitization_proposals CASCADE")
        )
    with temporary_login(migrated_url, "api_user") as api_url, temporary_login(migrated_url, "batch_user") as batch_url:
        api = create_engine(api_url)
        bootstrap(KIT, api, LocalObjectStore(tmp_path_factory.mktemp("storage")))
        api.dispose()
        first = run_sanitize(PDM, database_url=batch_url)
        second = run_sanitize(PDM, database_url=batch_url)
        yield first, second, admin, batch_url
    admin.dispose()


def total(result):
    """Unificações mais correções, todas gravadas na mesma tabela."""
    return result["proposals"]


def scalar(engine, query):
    with engine.connect() as connection:
        return connection.execute(text(query)).scalar_one()


def test_batch_saves_proposals_with_members_conflicts_and_versions(sanitized):
    first, _, admin, _ = sanitized
    assert first["merges"] > 1000
    assert first["proposals"] == first["merges"] + sum(first["corrections"]["proposals"].values())
    assert first["inserted"] == total(first)
    assert scalar(admin, "SELECT count(*) FROM sanitization_proposals") == total(first)
    with admin.connect() as connection:
        row = connection.execute(
            text(
                "SELECT p.proposal_type, p.status, p.members, p.changeset, p.fiscal_review_status, "
                "m.material_code FROM sanitization_proposals p JOIN materials_master m ON m.id = p.primary_material_id "
                "WHERE p.proposal_type = 'MERGE' AND jsonb_array_length(p.changeset->'conflicts') > 0 LIMIT 1"
            )
        ).one()
    assert (row[0], row[1]) == ("MERGE", "PENDING")
    assert row[3]["primary_material_code"] == row[5]
    assert row[3]["conflicts"]
    assert all(member["expected_version"] == 1 and member["material_id"] for member in row[2])


def test_running_again_duplicates_nothing(sanitized):
    first, second, admin, _ = sanitized
    assert second["inserted"] == 0
    assert total(second) == total(first)
    assert scalar(admin, "SELECT count(*) FROM sanitization_proposals") == total(first)


def test_master_data_stays_untouched(sanitized):
    _, _, admin, _ = sanitized
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE version <> 1 OR is_canonical") == 0
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE status = 'ATIVO'") == 20014


def test_only_active_materials_are_proposed(sanitized):
    _, _, admin, _ = sanitized
    query = (
        "SELECT count(*) FROM sanitization_proposals p, jsonb_array_elements(p.members) member, materials_master m "
        "WHERE m.id = (member->>'material_id')::uuid AND m.status <> 'ATIVO'"
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
    assert first["merge_summary"]["conflicts"]["UNIDADE_SEM_FATOR"] > 0
    query = (
        "SELECT count(*) FROM sanitization_proposals "
        "WHERE proposal_type = 'MERGE' AND changeset::text LIKE '%UNIDADE_SEM_FATOR%'"
    )
    assert scalar(admin, query) == first["merge_summary"]["conflicts"]["UNIDADE_SEM_FATOR"]


def test_corrections_are_saved_with_before_after_and_rule(sanitized):
    first, _, admin, _ = sanitized
    with admin.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT proposal_type, count(*) FROM sanitization_proposals "
                "WHERE proposal_type <> 'MERGE' AND fiscal_review_status = 'NOT_REQUIRED' GROUP BY 1"
            )
        )
        saved = {row[0]: row[1] for row in rows}
    assert saved == first["corrections"]["proposals"]
    assert set(saved) == {"PDM_CORRECTION", "UNIT_CORRECTION"}
    query = (
        "SELECT count(*) FROM sanitization_proposals p, jsonb_array_elements(p.changeset->'changes') change "
        "WHERE p.proposal_type <> 'MERGE' AND (change->>'after' IS NULL OR change->>'source' IS NULL "
        "OR NOT change ? 'before')"
    )
    assert scalar(admin, query) == 0
