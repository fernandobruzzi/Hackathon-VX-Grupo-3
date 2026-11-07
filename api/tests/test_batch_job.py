"""Job de saneamento na base inteira: checkpoints, retomada sem duplicar, cobertura e métricas."""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from clients.storage import LocalObjectStore
from pipelines import full_run
from pipelines.full_run import AnalysisRulesChanged, run_sanitize
from repositories.batch_repository import JobNotRunnable
from vx_materials_api.batch_job_cli import create_job, main
from vx_materials_api.bootstrap import bootstrap
from vx_materials_api.db.temporary_login import temporary_login

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")
MATERIALS = 23554


class Interrupted(Exception):
    """Simula a task parando no meio (queda, timeout, deploy)."""


def stop_at(stage, step):
    def hook(current_stage, done):
        if current_stage == stage and done == step:
            raise Interrupted(f"{stage}:{step}")

    return hook


@pytest.fixture(scope="module")
def base(migrated_url, tmp_path_factory):
    admin = create_engine(migrated_url)
    with admin.begin() as connection:
        connection.execute(
            text("TRUNCATE datasets, reference_versions, materials_master, sanitization_proposals, batch_jobs CASCADE")
        )
    with temporary_login(migrated_url, "api_user") as api_url, temporary_login(migrated_url, "batch_user") as batch_url:
        api = create_engine(api_url)
        bootstrap(KIT, api, LocalObjectStore(tmp_path_factory.mktemp("kit")))
        api.dispose()
        yield admin, batch_url
    admin.dispose()


def new_job(admin):
    """Como a API faria: o job nasce QUEUED, com quem pediu e o dataset."""
    return create_job(admin)


def job_row(admin, job_id):
    with admin.connect() as connection:
        return (
            connection.execute(
                text("SELECT status, checkpoint, counts, error_summary, heartbeat_at FROM batch_jobs WHERE id = :id"),
                {"id": job_id},
            )
            .mappings()
            .one()
        )


def proposals_of(admin, job_id=None):
    query = "SELECT count(*) FROM sanitization_proposals" + (" WHERE job_id = :id" if job_id else "")
    with admin.connect() as connection:
        return connection.execute(text(query), {"id": job_id}).scalar_one()


@pytest.fixture(scope="module")
def resumed(base, tmp_path_factory):
    """Um job interrompido duas vezes, na análise e na gravação, e depois concluído."""
    admin, batch_url = base
    store = LocalObjectStore(tmp_path_factory.mktemp("runs"))
    job_id = new_job(admin)
    with pytest.raises(Interrupted):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store, on_step=stop_at("analysis", 5))
    after_analysis_stop = job_row(admin, job_id)
    with pytest.raises(Interrupted):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store, on_step=stop_at("save", 1500))
    after_save_stop = job_row(admin, job_id)
    saved_before_finish = proposals_of(admin, job_id)
    metrics = run_sanitize(PDM, job_id, database_url=batch_url, store=store)
    return admin, batch_url, store, job_id, after_analysis_stop, after_save_stop, saved_before_finish, metrics


def test_interruption_marks_job_failed_and_keeps_checkpoint(resumed):
    after_analysis_stop, after_save_stop = resumed[4], resumed[5]
    assert after_analysis_stop["status"] == "FAILED"
    assert after_analysis_stop["checkpoint"]["analysis"]["chunks_done"] == 5
    assert "Interrupted" in after_analysis_stop["error_summary"]
    assert after_save_stop["status"] == "FAILED"
    assert after_save_stop["checkpoint"]["save"]["saved"] == 1500


def test_resume_reuses_analysis_and_saved_batches(resumed):
    admin, _, _, job_id, _, _, saved_before_finish, metrics = resumed
    assert saved_before_finish == 1500
    checkpoint = job_row(admin, job_id)["checkpoint"]
    assert checkpoint["analysis"]["chunks_reused"] == checkpoint["analysis"]["chunks_total"] == 24
    # A última tentativa só gravou o que faltava.
    assert metrics["inserted"] == metrics["proposals"]
    assert len(checkpoint["attempts"]) == 3


def test_resumed_job_has_no_duplicates_and_matches_a_clean_run(resumed, tmp_path_factory):
    admin, batch_url, _, job_id, *_, metrics = resumed
    assert proposals_of(admin, job_id) == metrics["proposals"] == proposals_of(admin)
    clean = run_sanitize(
        PDM, new_job(admin), database_url=batch_url, store=LocalObjectStore(tmp_path_factory.mktemp("c"))
    )
    assert clean["by_type"] == metrics["by_type"]
    assert clean["inserted"] == 0
    assert proposals_of(admin) == metrics["proposals"]


def test_every_material_has_an_outcome(resumed):
    *_, metrics = resumed
    coverage = metrics["coverage"]
    assert coverage["materials_total"] == MATERIALS
    assert sum(coverage["outcomes"].values()) == MATERIALS
    assert set(coverage["outcomes"]) <= {"PROPOSTA", "PENDENTE", "SEM_ALTERACAO", "ERRO_ANALISE"}
    assert coverage["outcomes"].get("ERRO_ANALISE", 0) == len(coverage["errors"])


def test_finished_job_stores_counts_time_and_model_usage(resumed):
    admin, _, store, job_id, *_, metrics = resumed
    row = job_row(admin, job_id)
    assert row["status"] == "SUCCEEDED" and row["error_summary"] is None and row["heartbeat_at"]
    counts = row["counts"]
    assert {key: counts[key] for key in ("proposals", "merges", "ncm", "enrichment")} == {
        "proposals": metrics["proposals"],
        "merges": metrics["by_type"]["MERGE"],
        "ncm": metrics["by_type"].get("NCM_CORRECTION", 0),
        "enrichment": 0,
    }
    assert counts["timing_seconds"]["attempts"] == 3 and counts["timing_seconds"]["total_all_attempts"] > 0
    assert counts["model_usage"] == {
        "calls": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": "0",
        "note": "sem chamadas de modelo",
    }
    assert json.loads(store.get(f"runs/{job_id}/metrics.json"))["by_type"] == counts["by_type"]


def test_finished_job_cannot_run_again(resumed):
    _, batch_url, store, job_id, *_ = resumed
    with pytest.raises(JobNotRunnable):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store)


def test_resume_with_other_rules_fails_the_job_and_keeps_its_analysis(resumed, tmp_path, monkeypatch):
    """#83: extração revisada entre a interrupção e a retomada. O job falha com o motivo, sem reanalisar."""
    admin, batch_url, *_ = resumed
    store = LocalObjectStore(tmp_path)
    job_id = new_job(admin)
    with pytest.raises(Interrupted):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store, on_step=stop_at("analysis", 1))
    chunk = store.get(f"runs/{job_id}/analysis/chunk-0000.json")
    current = full_run.get_extraction_repository()

    class Revised(type(current)):
        revision = current.revision + "-revisada"

    monkeypatch.setattr(full_run, "get_extraction_repository", Revised)
    with pytest.raises(AnalysisRulesChanged):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store)
    row = job_row(admin, job_id)
    assert row["status"] == "FAILED"
    assert "novo job" in row["error_summary"]
    assert row["checkpoint"]["analysis"]["chunks_done"] == 1
    assert store.get(f"runs/{job_id}/analysis/chunk-0000.json") == chunk
    assert proposals_of(admin, job_id) == 0


def test_local_job_command_refuses_outside_local(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="APP_ENV=local"):
        main([])


@pytest.mark.parametrize("failure_point", ["before_storage", "after_storage", "finish"])
def test_resume_after_metrics_finalization_failure(base, tmp_path, monkeypatch, failure_point):
    """Análise, armazenamento e transações reais; só a finalização falha uma vez."""
    admin, batch_url = base
    job_id = new_job(admin)
    store = LocalObjectStore(tmp_path)
    original_read = full_run.read_materials
    monkeypatch.setattr(
        full_run, "read_materials", lambda engine, tenant, **kwargs: original_read(engine, tenant, **kwargs)[:2]
    )
    original_put = store.put_if_absent
    original_finish = full_run.finish_job
    failed = False

    def put(key, content):
        nonlocal failed
        if key.endswith("metrics.json") and not failed and failure_point != "finish":
            failed = True
            if failure_point == "after_storage":
                original_put(key, content)
            raise Interrupted(failure_point)
        return original_put(key, content)

    def finish(*args):
        nonlocal failed
        if not failed and failure_point == "finish":
            failed = True
            raise Interrupted(failure_point)
        return original_finish(*args)

    monkeypatch.setattr(store, "put_if_absent", put)
    monkeypatch.setattr(full_run, "finish_job", finish)
    with pytest.raises(Interrupted):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store)
    interrupted = job_row(admin, job_id)
    assert interrupted["status"] == "FAILED"
    assert failure_point in interrupted["error_summary"]
    count = proposals_of(admin)
    checkpoint = interrupted["checkpoint"]
    metrics = run_sanitize(PDM, job_id, database_url=batch_url, store=store)
    completed = job_row(admin, job_id)
    assert completed["status"] == "SUCCEEDED"
    assert completed["counts"] == metrics == json.loads(store.get(f"runs/{job_id}/metrics.json"))
    assert proposals_of(admin) == count
    assert completed["checkpoint"]["save"] == checkpoint["save"]
    assert completed["checkpoint"]["lease"]["worker"] != checkpoint["lease"]["worker"]
    assert len(completed["checkpoint"]["finalization_attempts"]) == 2
    assert "error" in completed["checkpoint"]["finalization_attempts"][0]


def test_frozen_final_metrics_refuse_changed_rules(base, tmp_path, monkeypatch):
    admin, batch_url = base
    job_id = new_job(admin)
    store = LocalObjectStore(tmp_path)
    original_read = full_run.read_materials
    monkeypatch.setattr(
        full_run, "read_materials", lambda engine, tenant, **kwargs: original_read(engine, tenant, **kwargs)[:2]
    )
    original_finish = full_run.finish_job

    def fail_finish(*args):
        raise Interrupted("finish")

    monkeypatch.setattr(full_run, "finish_job", fail_finish)
    with pytest.raises(Interrupted):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store)
    original = store.get(f"runs/{job_id}/metrics.json")
    attempts = job_row(admin, job_id)["checkpoint"]["attempts"]
    current = full_run.get_extraction_repository()

    class Revised(type(current)):
        revision = current.revision + "-revisada"

    monkeypatch.setattr(full_run, "finish_job", original_finish)
    monkeypatch.setattr(full_run, "get_extraction_repository", Revised)
    with pytest.raises(AnalysisRulesChanged, match="novo job"):
        run_sanitize(PDM, job_id, database_url=batch_url, store=store)
    row = job_row(admin, job_id)
    assert row["status"] == "FAILED"
    assert "novo job" in row["error_summary"]
    assert row["checkpoint"]["attempts"] == attempts
    assert len(row["checkpoint"]["finalization_attempts"]) == 2
    assert "AnalysisRulesChanged" in row["checkpoint"]["finalization_attempts"][-1]["error"]
    assert store.get(f"runs/{job_id}/metrics.json") == original
