"""Histórico completo, cursores por empresa/filtro e acompanhamento de retomadas antigas."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from test_batch_api import RecordingRunner, _identity, client_for, post
from test_batch_api import base as base
from test_batch_api import clean_jobs as clean_jobs
from test_batch_api import storage as storage
from test_contracts import validator

PATH = "/api/v1/batch/jobs"


def seed(base, count=125):
    admin, _, _, dataset = base
    identity = _identity(admin, "GESTOR_CADASTRO")
    rows = [
        {
            "id": uuid.UUID(int=index + 1),
            "t": identity.tenant_id,
            "u": identity.user_id,
            "d": dataset,
            "created": datetime(2020, 1, 1, tzinfo=UTC) + timedelta(seconds=index // 5),
        }
        for index in range(count)
    ]
    with admin.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO batch_jobs (id, tenant_id, requested_by_user_id, dataset_id, job_type, pdm_version, "
                "status, checkpoint, created_at) VALUES "
                "(:id, :t, :u, :d, 'SANITIZE', 'pdm-kit-v1', 'FAILED', '{}', :created)"
            ),
            rows,
        )
    return rows


def encode(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def test_more_than_100_jobs_with_ties_are_complete_and_deterministic(clean_jobs):
    rows = seed(clean_jobs)
    # Outro tenant tem um job ativo mais recente, que não pode aparecer em nenhum campo.
    other_id, other_tenant, other_dataset = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with clean_jobs[0].begin() as connection:
        connection.execute(
            text("INSERT INTO datasets (id, tenant_id, files) VALUES (:d, :t, '{}')"),
            {"d": other_dataset, "t": other_tenant},
        )
        connection.execute(
            text(
                "INSERT INTO batch_jobs (id, tenant_id, requested_by_user_id, dataset_id, "
                "job_type, pdm_version, status) "
                "VALUES (:id, :t, :u, :d, 'SANITIZE', 'pdm-kit-v1', 'RUNNING')"
            ),
            {"id": other_id, "t": other_tenant, "u": rows[0]["u"], "d": other_dataset},
        )
    try:
        client = client_for(clean_jobs)
        ids, cursor, pages = [], None, 0
        while True:
            response = client.get(PATH, params={"limit": 17, **({"cursor": cursor} if cursor else {})})
            assert response.status_code == 200
            page = response.json()
            validator({"$ref": "#/components/schemas/BatchJobList"}).validate(page)
            assert page["active_job"] is None
            ids.extend(job["id"] for job in page["items"])
            cursor = page["next_cursor"]
            pages += 1
            if cursor is None:
                break
            assert pages < 10
        expected = [str(uuid.UUID(int=group * 5 + offset)) for group in reversed(range(25)) for offset in range(1, 6)]
        assert ids == expected
        assert len(ids) == len(set(ids)) == 125
        assert pages == 8
        assert client.get(PATH, params={"limit": 100}).json()["items"][0]["id"] == expected[0]
    finally:
        with clean_jobs[0].begin() as connection:
            connection.execute(text("DELETE FROM batch_jobs WHERE id = :id"), {"id": other_id})
            connection.execute(text("DELETE FROM datasets WHERE id = :id"), {"id": other_dataset})


@pytest.mark.parametrize("cursor", ["", "invalid!", "A" * 513, encode({}), encode([1, None, None, 3, []])])
def test_invalid_cursors_are_rejected(clean_jobs, cursor):
    response = client_for(clean_jobs).get(PATH, params={"cursor": cursor})
    assert response.status_code == 422


def test_cursor_is_bound_to_tenant_and_filter_and_validates_position(clean_jobs):
    rows = seed(clean_jobs, count=2)
    client = client_for(clean_jobs)
    cursor = client.get(PATH, params={"limit": 1, "status": "FAILED"}).json()["next_cursor"]
    assert cursor
    assert client.get(PATH, params={"limit": 1, "status": "FAILED", "cursor": cursor}).json()["next_cursor"] is None
    for params in [{"cursor": cursor}, {"status": "SUCCEEDED", "cursor": cursor}]:
        response = client.get(PATH, params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_CURSOR"
    payload = json.loads(base64.urlsafe_b64decode(cursor))
    for field, value in [
        (0, True),
        (0, 2),
        (1, str(uuid.uuid4())),
        (3, "2020-01-01"),
        (3, []),
        (4, []),
        (4, "not-a-uuid"),
    ]:
        changed = [*payload]
        changed[field] = value
        assert client.get(PATH, params={"status": "FAILED", "cursor": encode(changed)}).status_code == 422
    assert client.get(PATH, params={"status": "OTHER"}).status_code == 422
    assert rows


def test_resumed_old_job_is_active_outside_the_page_and_status_filter(clean_jobs, storage):
    rows = seed(clean_jobs)
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)
    old_id = str(rows[0]["id"])
    first = client.get(PATH).json()
    assert old_id not in [job["id"] for job in first["items"]]
    assert first["active_job"] is None
    resumed = post(client, f"{PATH}/{old_id}/resume")
    assert resumed.status_code == 202
    for status in [None, "FAILED", "SUCCEEDED"]:
        page = client.get(PATH, params={"limit": 20, **({"status": status} if status else {})}).json()
        assert page["active_job"]["id"] == old_id
        assert page["active_job"]["status"] == "QUEUED"
        assert old_id not in [job["id"] for job in page["items"]]
    assert [request.job_id for request in runner.launched] == [old_id]
