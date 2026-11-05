"""Jobs de batch pela API: permissão, manifesto sem token, job parado e reprocessamento."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from test_contracts import validator

from clients.storage import LocalObjectStore
from pipelines.full_run import run_sanitize
from repositories.batch_repository import JobNotRunnable, LeaseLost, claim_job, update_job
from vx_materials_api.bootstrap import TENANT_ID, bootstrap
from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import PERSONA_ROLES, permissions_for
from vx_materials_api.services import batch_runner
from vx_materials_api.services.batch_runner import LaunchRequest, LocalProcessRunner

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")
MATERIALS = 23554
CSRF = "test-csrf"


@pytest.fixture(scope="module")
def base(migrated_url, tmp_path_factory):
    admin = create_engine(migrated_url)
    with admin.begin() as connection:
        connection.execute(
            text("TRUNCATE datasets, reference_versions, materials_master, sanitization_proposals, batch_jobs CASCADE")
        )
    with temporary_login(migrated_url, "api_user") as api_url, temporary_login(migrated_url, "batch_user") as batch_url:
        api = create_engine(api_url)
        result = bootstrap(KIT, api, LocalObjectStore(tmp_path_factory.mktemp("kit")))
        yield admin, api, batch_url, result.dataset_id
        api.dispose()
    admin.dispose()


@pytest.fixture
def clean_jobs(base):
    admin = base[0]
    with admin.begin() as connection:
        connection.execute(text("DELETE FROM sanitization_proposals"))
        connection.execute(text("DELETE FROM batch_jobs"))
    return base


def _identity(admin, persona: str) -> Identity:
    role = PERSONA_ROLES[persona]
    name = persona
    with admin.begin() as connection:
        user_id = connection.execute(
            text(
                "INSERT INTO users_sso (tenant_id, issuer, subject, display_name) VALUES (:t, 'test', :s, :n) "
                "ON CONFLICT (issuer, subject) DO UPDATE SET display_name = EXCLUDED.display_name RETURNING id"
            ),
            {"t": TENANT_ID, "s": persona, "n": name},
        ).scalar_one()
    return Identity(
        user_id=user_id, tenant_id=TENANT_ID, roles=(role,), permissions=permissions_for((role,)), csrf_token=CSRF
    )


class RecordingRunner:
    """Guarda o que seria disparado. `run` executa o batch de verdade, no mesmo processo."""

    name = "recording"

    def __init__(self):
        self.launched: list[LaunchRequest] = []

    def launch(self, request: LaunchRequest) -> str:
        self.launched.append(request)
        return f"test:{len(self.launched)}"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    return LocalObjectStore(tmp_path)


def client_for(base, persona="GESTOR_CADASTRO", runner=None):
    admin, api, *_ = base
    identity = _identity(admin, persona)
    app = create_app(
        session_factory=sessionmaker(api, expire_on_commit=False),
        identity_provider=lambda db: identity,
        batch_runner=runner,
    )
    return TestClient(app)


def start_body(dataset_id, **overrides):
    body = {
        "dataset_id": str(dataset_id),
        "job_type": "SANITIZE",
        "pdm_version": "pdm-kit-v1",
        "ncm_version": "ncm-demo-v1",
        "scope": {"pdm_class_ids": [], "include_statuses": ["ATIVO", "BLOQUEADO", "OBSOLETO"]},
    }
    return {**body, **overrides}


def post(client, path, body=None):
    body = {} if body is None else body
    headers = {"Idempotency-Key": str(uuid.uuid4()), "Origin": "http://localhost:8000", "X-CSRF-Token": CSRF}
    return client.post(path, json=body, headers=headers)


def age(admin, job_id, *, heartbeat_seconds=None, updated_seconds=None):
    """Envelhece o job, como se o worker tivesse parado há esse tempo."""
    with admin.begin() as connection:
        if heartbeat_seconds is not None:
            connection.execute(
                text("UPDATE batch_jobs SET heartbeat_at = now() - make_interval(secs => :s) WHERE id = :id"),
                {"s": heartbeat_seconds, "id": job_id},
            )
        if updated_seconds is not None:
            connection.execute(
                text("UPDATE batch_jobs SET updated_at = now() - make_interval(secs => :s) WHERE id = :id"),
                {"s": updated_seconds, "id": job_id},
            )


def test_requester_cannot_start_or_read_jobs(clean_jobs, storage):
    runner = RecordingRunner()
    client = client_for(clean_jobs, "SOLICITANTE_OPERACAO", runner)

    assert post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3])).status_code == 403
    assert client.get("/api/v1/batch/jobs").status_code == 403
    assert runner.launched == []


def test_governance_starts_job_with_manifest_and_no_user_token(clean_jobs, storage):
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)

    response = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3]))

    assert response.status_code == 202
    job = response.json()
    validator({"$ref": "#/components/schemas/BatchJob"}).validate(job)
    assert job["status"] == "QUEUED" and job["progress"] == {"processed": 0, "total": MATERIALS}
    assert [r.job_id for r in runner.launched] == [job["id"]]
    manifest = json.loads(storage.get(runner.launched[0].manifest_key))
    validator({"$ref": "#/components/schemas/BatchManifest"}).validate(manifest)
    assert manifest["job_id"] == job["id"]
    assert not {"token", "access_token", "session", "user_id", "role"} & set(manifest)


def test_only_one_active_job(clean_jobs, storage):
    client = client_for(clean_jobs, runner=RecordingRunner())
    first = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3])).json()

    second = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3]))

    assert second.status_code == 409
    assert second.json()["error"]["details"]["job_id"] == first["id"]


def test_job_without_heartbeat_becomes_failed(clean_jobs, storage):
    admin = clean_jobs[0]
    client = client_for(clean_jobs, runner=RecordingRunner())
    job = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3])).json()
    with admin.begin() as connection:
        connection.execute(text("UPDATE batch_jobs SET status = 'RUNNING' WHERE id = :id"), {"id": job["id"]})
    age(admin, job["id"], heartbeat_seconds=600)

    current = client.get(f"/api/v1/batch/jobs/{job['id']}").json()

    assert current["status"] == "FAILED"
    assert current["error"]["code"] == "WORKER_TIMEOUT"
    validator({"$ref": "#/components/schemas/BatchJob"}).validate(current)


def test_task_that_never_starts_becomes_failed(clean_jobs, storage):
    client = client_for(clean_jobs, runner=RecordingRunner())
    job = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3])).json()
    age(clean_jobs[0], job["id"], updated_seconds=600)

    listed = client.get("/api/v1/batch/jobs").json()

    assert listed["items"][0]["status"] == "FAILED"
    assert listed["items"][0]["error"]["code"] == "WORKER_NOT_STARTED"
    assert listed["latest_dataset_id"] == str(clean_jobs[3])
    validator({"$ref": "#/components/schemas/BatchJobList"}).validate(listed)


def test_resume_continues_from_checkpoint_without_duplicates(clean_jobs, storage):
    admin, _, batch_url, dataset_id = clean_jobs
    runner = RecordingRunner()
    client = client_for(clean_jobs, runner=runner)
    job = post(client, "/api/v1/batch/jobs", start_body(dataset_id)).json()
    manifest_key = runner.launched[0].manifest_key

    class Stop(Exception):
        pass

    def stop_at_save(stage, done):
        if stage == "save" and done == 1500:
            raise Stop()

    with pytest.raises(Stop):
        run_sanitize(
            PDM, job["id"], database_url=batch_url, store=storage, on_step=stop_at_save, manifest_key=manifest_key
        )
    assert client.get(f"/api/v1/batch/jobs/{job['id']}").json()["status"] == "FAILED"

    resumed = post(client, f"/api/v1/batch/jobs/{job['id']}/resume")
    assert resumed.status_code == 202 and resumed.json()["status"] == "QUEUED"
    assert [r.job_id for r in runner.launched] == [job["id"], job["id"]]
    metrics = run_sanitize(PDM, job["id"], database_url=batch_url, store=storage, manifest_key=manifest_key)

    done = client.get(f"/api/v1/batch/jobs/{job['id']}").json()
    assert done["status"] == "SUCCEEDED" and done["error"] is None
    assert done["progress"] == {"processed": MATERIALS, "total": MATERIALS}
    assert done["counts"]["proposals"] == metrics["proposals"]
    with admin.connect() as connection:
        saved = connection.execute(text("SELECT count(*) FROM sanitization_proposals")).scalar_one()
    assert saved == metrics["proposals"]
    assert post(client, f"/api/v1/batch/jobs/{job['id']}/resume").status_code == 409


def test_stale_worker_loses_lease_and_cannot_write(clean_jobs, storage):
    admin, _, batch_url, _ = clean_jobs
    client = client_for(clean_jobs, runner=RecordingRunner())
    job = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3])).json()
    engine = create_engine(batch_url)
    try:
        claimed = claim_job(engine, job["id"], "worker-a")
        with pytest.raises(JobNotRunnable, match="outro worker"):
            claim_job(engine, job["id"], "worker-b")
        age(admin, job["id"], heartbeat_seconds=600)
        assert client.get(f"/api/v1/batch/jobs/{job['id']}").json()["status"] == "FAILED"

        with pytest.raises(LeaseLost), engine.begin() as connection:
            update_job(connection, job["id"], claimed["checkpoint"])
        with admin.connect() as connection:
            status = connection.execute(text("SELECT status FROM batch_jobs WHERE id = :id"), {"id": job["id"]})
            assert status.scalar_one() == "FAILED"
    finally:
        engine.dispose()


def test_without_runner_start_is_unavailable(clean_jobs, storage, monkeypatch):
    monkeypatch.delenv("BATCH_RUNNER", raising=False)
    client = client_for(clean_jobs, runner=None)

    response = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3]))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BATCH_RUNNER_UNAVAILABLE"


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"job_type": "IMPORT_ORDERS"}, "JOB_TYPE_NOT_SUPPORTED"),
        ({"scope": {"pdm_class_ids": ["PDM001"], "include_statuses": ["ATIVO"]}}, "SCOPE_NOT_SUPPORTED"),
    ],
)
def test_unsupported_requests_are_rejected(clean_jobs, storage, override, code):
    client = client_for(clean_jobs, runner=RecordingRunner())

    response = post(client, "/api/v1/batch/jobs", start_body(clean_jobs[3], **override))

    assert response.status_code == 422 and response.json()["error"]["code"] == code


def test_local_runner_passes_only_batch_credentials(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("BATCH_DATABASE_URL", "postgresql+psycopg://batch_user:x@db/vx")
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", "secret-that-must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://api_user:y@db/vx")
    calls = []

    class FakeProcess:
        pid = 42

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs["env"]))
        return FakeProcess()

    reference = LocalProcessRunner(popen=fake_popen).launch(LaunchRequest("job-1", "runs/job-1/manifest.json"))

    command, env = calls[0]
    assert reference == "local-pid:42"
    assert command[-4:] == ["--job-id", "job-1", "--manifest-key", "runs/job-1/manifest.json"]
    assert env["DATABASE_URL"] == "postgresql+psycopg://batch_user:x@db/vx"
    assert "AGENT_INTERNAL_TOKEN_SECRET" not in env
    assert not any("token" in value.lower() or "api_user" in value for value in env.values())


def test_local_runner_refuses_outside_local(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="APP_ENV=local"):
        LocalProcessRunner(popen=lambda *a, **k: None).launch(LaunchRequest("j", "k"))


def test_unknown_runner_fails_fast():
    with pytest.raises(RuntimeError, match="BATCH_RUNNER desconhecido"):
        batch_runner.get_batch_runner("ecs-fake")
