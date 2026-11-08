"""Repetição do batch e das pendências no PostgreSQL com um recorte real do kit."""

import pytest
from test_sanitize import PDM, batch_database, check_manual_review_counts, scalar, total

from pipelines.full_run import run_sanitize


@pytest.fixture(scope="module")
def sanitized_twice(migrated_url, tmp_path_factory, small_sanitization_kit):
    with batch_database(migrated_url, tmp_path_factory, small_sanitization_kit) as (admin, batch_url, store):
        first = run_sanitize(PDM, database_url=batch_url, store=store)
        second = run_sanitize(PDM, database_url=batch_url, store=store)
        yield first, second, admin


def test_running_again_duplicates_nothing(sanitized_twice):
    first, second, admin = sanitized_twice
    assert first["inserted"] == total(first) > 0
    assert second["inserted"] == 0
    assert total(second) == total(first)
    assert scalar(admin, "SELECT count(*) FROM sanitization_proposals") == total(first)


def test_manual_review_rerun_reuses_the_same_observations(sanitized_twice):
    first, second, admin = sanitized_twice
    assert first["manual_review_run_id"] == second["manual_review_run_id"]
    check_manual_review_counts(first, admin)
