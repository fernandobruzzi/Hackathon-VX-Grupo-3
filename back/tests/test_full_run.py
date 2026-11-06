"""Retomada da análise só com as mesmas regras (#83). O checkpoint no banco fica de fora destes testes."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from clients.storage import LocalObjectStore
from domain.contracts import MaterialRecord
from domain.pdm_loader import load_pdm
from pipelines import full_run, sanitize
from pipelines.full_run import AnalysisRulesChanged, RunContext, analyze_all
from repositories import extraction

PDM = Path(__file__).parents[2] / "data" / "desafio01" / "03_padrao_cadastro_PDM.xlsx"
RECORDS = [
    MaterialRecord(code="1", status="ATIVO", description="FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009"),
    MaterialRecord(code="2", status="ATIVO", description="PARAFUSO SEXTAVADO M12X50 8.8 ACO CARBONO DIN 933"),
]


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(PDM)


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    monkeypatch.setattr(full_run, "_save_checkpoint", lambda context: None)


@pytest.fixture()
def job(tmp_path):
    """Um job que analisou tudo e parou: blocos no armazenamento, checkpoint em memória."""

    def context(checkpoint):
        return RunContext(
            engine=None, tenant_id="t", job_id="job-1", store=LocalObjectStore(tmp_path), checkpoint=checkpoint
        )

    return context


def interrupted(job, catalog):
    checkpoint = {}
    analyze_all(RECORDS, catalog, job(checkpoint))
    return checkpoint


def test_same_rules_reuse_the_stored_analysis(job, catalog):
    checkpoint = interrupted(job, catalog)
    analyzed, _ = analyze_all(RECORDS, catalog, job(checkpoint))
    assert checkpoint["analysis"]["chunks_reused"] == 1
    assert [material.record.code for material in analyzed] == ["1", "2"]


def test_pdm_content_change_refuses_the_resume(job, catalog):
    checkpoint = interrupted(job, catalog)
    edited = replace(catalog, source_sha256="0" * 64)
    with pytest.raises(AnalysisRulesChanged, match="novo job"):
        analyze_all(RECORDS, edited, job(checkpoint))


def test_extractor_revision_change_refuses_the_resume(job, catalog, monkeypatch):
    checkpoint = interrupted(job, catalog)
    current = extraction.get_extraction_repository()

    class Revised(type(current)):
        revision = current.revision + "-revisada"

    monkeypatch.setattr(full_run, "get_extraction_repository", Revised)
    with pytest.raises(AnalysisRulesChanged):
        analyze_all(RECORDS, catalog, job(checkpoint))


def test_identity_rules_change_refuses_the_resume(job, catalog, monkeypatch):
    checkpoint = interrupted(job, catalog)
    monkeypatch.setattr(sanitize, "IDENTITY_RULES_VERSION", "identity-revisada")
    with pytest.raises(AnalysisRulesChanged):
        analyze_all(RECORDS, catalog, job(checkpoint))


def test_stored_chunk_from_other_rules_is_refused_and_kept(job, catalog, tmp_path):
    """Sem assinatura no checkpoint, o próprio bloco gravado acusa a diferença. Nada é sobrescrito."""
    interrupted(job, catalog)
    chunk = tmp_path / "runs" / "job-1" / "analysis" / "chunk-0000.json"
    before = chunk.read_bytes()
    edited = replace(catalog, source_sha256="0" * 64)
    with pytest.raises(AnalysisRulesChanged):
        analyze_all(RECORDS, edited, job({}))
    assert chunk.read_bytes() == before
    assert json.loads(before)["rules_signature"] == sanitize.analysis_signature(
        catalog, *_default_repositories(catalog)
    )


def test_job_without_analysis_starts_with_current_rules(job, catalog):
    checkpoint = {"attempts": [{"started_at": "x"}]}
    analyze_all(RECORDS, catalog, job(checkpoint))
    assert checkpoint["analysis_signature"] == sanitize.analysis_signature(catalog, *_default_repositories(catalog))


def _default_repositories(catalog):
    from repositories.classification import get_classification_repository

    return get_classification_repository(catalog), extraction.get_extraction_repository()


@pytest.fixture
def ncm_snapshot(tmp_path, monkeypatch):
    from datetime import date

    from clients.ncm_snapshot_store import NcmSnapshotStore
    from domain.ncm_snapshot import NcmSourceKind, load_ncm_snapshot

    raw = (Path(__file__).parent / "fixtures/ncm_simulated.json").read_bytes()
    snapshot = load_ncm_snapshot(raw, snapshot_date=date(2026, 11, 6), source_kind=NcmSourceKind.SIMULATED)
    NcmSnapshotStore(LocalObjectStore(tmp_path)).register(snapshot, raw)
    monkeypatch.setenv("NCM_SNAPSHOT_VERSION", snapshot.version)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    return snapshot


def test_resume_cannot_mix_ncm_references(job, catalog, ncm_snapshot, monkeypatch):
    checkpoint = interrupted(job, catalog)
    # Um job antigo sem snapshot não pode receber a nova referência na retomada.
    with pytest.raises(AnalysisRulesChanged, match="referencia NCM"):
        full_run.run_full(RECORDS, catalog, job(checkpoint))
    checkpoint["ncm_reference"] = {
        "version": ncm_snapshot.version,
        "sha256": ncm_snapshot.source_sha256,
        "date": ncm_snapshot.snapshot_date.isoformat(),
        "source_kind": ncm_snapshot.source_kind.value,
    }
    # Remover a configuração também muda a referência previamente vinculada.
    monkeypatch.delenv("NCM_SNAPSHOT_VERSION")
    with pytest.raises(AnalysisRulesChanged, match="referencia NCM"):
        full_run.run_full(RECORDS, catalog, job(checkpoint))


def test_full_run_binds_snapshot_to_technical_proposals(catalog, ncm_snapshot, monkeypatch):
    captured = []
    monkeypatch.setattr(
        full_run, "save_all", lambda proposals, records, context: captured.extend(proposals) or len(proposals)
    )
    # Itens de identidade por referência geram merge e correções técnicas.
    records = [replace(RECORDS[0], code=str(i), ncm="8421.23.00", unit="PC") for i in range(1, 3)]
    context = RunContext(engine=None, tenant_id="t")
    result = full_run.run_full(records, catalog, context)
    assert result["merge_summary"]["fiscal_review_required"] == sum(
        p.fiscal_review_required for p in captured if p.proposal_type == "MERGE"
    )
    assert result["merge_summary"]["fiscal_review_required"] == 1
    assert captured
    assert context.checkpoint["ncm_reference"]["sha256"] == ncm_snapshot.source_sha256
    assessed = [p for p in captured if p.proposal_type != "UNIT_CORRECTION"]
    assert assessed
    for proposal in assessed:
        assessment = proposal.changeset["ncm_assessment"]
        assert assessment["ncm_version"] == ncm_snapshot.version
        assert assessment["ncm_source_sha256"] == ncm_snapshot.source_sha256
        assert assessment["ncm_snapshot_date"] == "2026-11-06"
        assert assessment["ncm_source_kind"] == "SIMULATED"
        assert proposal.fiscal_review_required
