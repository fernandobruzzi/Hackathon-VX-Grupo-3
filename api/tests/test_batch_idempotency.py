"""Comandos HTTP repetidos recuperam o job e nunca disparam outra task."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from sqlalchemy import text
from test_batch_api import (
    CSRF,
    RecordingRunner,
    client_for,
    start_body,
)
from test_batch_api import (
    base as base,
)
from test_batch_api import (
    clean_jobs as clean_jobs,
)
from test_batch_api import (
    storage as storage,
)

PATH = "/api/v1/batch/jobs"


def command(client, path, body, key):
    return client.post(
        path,
        json=body,
        headers={
            "Origin": "http://localhost:8000",
            "X-CSRF-Token": CSRF,
            "Idempotency-Key": str(key),
        },
    )


def set_status(base, job_id, status):
    with base[0].begin() as connection:
        connection.execute(text("UPDATE batch_jobs SET status=:s WHERE id=:id"), {"s": status, "id": job_id})


@pytest.mark.parametrize("key", [None, "not-a-uuid"])
@pytest.mark.parametrize("resume", [False, True])
def test_commands_require_uuid_key(clean_jobs, storage, key, resume):
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)
    path = f"{PATH}/{uuid.uuid4()}/resume" if resume else PATH
    headers = {"Origin": "http://localhost:8000", "X-CSRF-Token": CSRF}
    if key is not None:
        headers["Idempotency-Key"] = key
    response = client.post(path, json={} if resume else start_body(clean_jobs[3]), headers=headers)
    assert response.status_code == 422
    assert not runner.launched


def test_start_replay_after_lost_response_and_completion(clean_jobs, storage):
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)
    key = uuid.uuid4()
    body = start_body(clean_jobs[3])
    original = command(client, PATH, body, key)
    assert original.status_code == 202
    job_id = original.json()["id"]
    # O cliente perdeu a resposta; tanto em andamento como depois da conclusão recupera o mesmo id.
    assert command(client, PATH, body, key).json()["id"] == job_id
    set_status(clean_jobs, job_id, "SUCCEEDED")
    replay = command(client, PATH, body, key)
    assert replay.status_code == 202
    assert replay.json()["id"] == job_id and replay.json()["status"] == "SUCCEEDED"
    assert len(runner.launched) == 1
    assert len(list(storage._root.rglob("manifest.json"))) == 1


@pytest.mark.parametrize("resume", [False, True])
def test_concurrent_same_key_has_one_launch(clean_jobs, storage, resume):
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)
    body, path = start_body(clean_jobs[3]), PATH
    expected_launches = 1
    if resume:
        created = command(client, PATH, body, uuid.uuid4()).json()
        set_status(clean_jobs, created["id"], "FAILED")
        path, body = f"{PATH}/{created['id']}/resume", {}
        expected_launches = 2
    key, barrier = uuid.uuid4(), threading.Barrier(2)

    def submit():
        concurrent_client = client_for(clean_jobs, runner=runner)
        barrier.wait(timeout=10)
        return command(concurrent_client, path, body, key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert len(runner.launched) == expected_launches
    assert len(list(storage._root.rglob("manifest.json"))) == 1


def test_payload_and_resource_conflicts(clean_jobs, storage):
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)
    key = uuid.uuid4()
    body = start_body(clean_jobs[3])
    first = command(client, PATH, body, key).json()
    conflict = command(client, PATH, {**body, "ncm_version": "other-reference"}, key)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    set_status(clean_jobs, first["id"], "FAILED")
    # Uma chave não identifica duas ações, mesmo que apontem para o mesmo job.
    assert command(client, f"{PATH}/{first['id']}/resume", {}, key).status_code == 409
    second = command(client, PATH, body, uuid.uuid4()).json()
    set_status(clean_jobs, second["id"], "FAILED")
    resume_key = uuid.uuid4()
    assert command(client, f"{PATH}/{first['id']}/resume", {}, resume_key).status_code == 202
    conflict = command(client, f"{PATH}/{second['id']}/resume", {}, resume_key)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    set_status(clean_jobs, first["id"], "SUCCEEDED")
    assert command(client, f"{PATH}/{first['id']}/resume", {}, resume_key).json()["status"] == "SUCCEEDED"
    assert len(runner.launched) == 3


def test_replay_checks_current_authorization_and_tenant(clean_jobs, storage):
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)
    body, key = start_body(clean_jobs[3]), uuid.uuid4()
    original = command(client, PATH, body, key).json()
    identity = client.app.state.identity_provider(None)
    client.app.state.identity_provider = lambda db: replace(identity, permissions=frozenset())
    assert command(client, PATH, body, key).status_code == 403
    client.app.state.identity_provider = lambda db: replace(identity, tenant_id=uuid.uuid4())
    assert command(client, PATH, body, key).status_code == 404
    assert command(client, f"{PATH}/{original['id']}/resume", {}, uuid.uuid4()).status_code == 404
    assert len(runner.launched) == 1


def test_ambiguous_runner_failure_never_relaunches_on_replay(clean_jobs, storage):
    class LostResponseRunner(RecordingRunner):
        def launch(self, request):
            super().launch(request)
            raise TimeoutError("Resposta do runner perdida")

    runner = LostResponseRunner()
    client = client_for(clean_jobs, runner=runner)
    body, key = start_body(clean_jobs[3]), uuid.uuid4()
    assert command(client, PATH, body, key).status_code == 503
    replay = command(client, PATH, body, key)
    assert replay.status_code == 202 and replay.json()["status"] == "FAILED"
    assert len(runner.launched) == 1
