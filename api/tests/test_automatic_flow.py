"""Batch real → API automática → consulta HTTP → índice consultado com mcp_reader."""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from clients.storage import LocalObjectStore
from domain.pdm_loader import load_pdm
from pipelines.full_run import run_sanitize
from repositories.automatic_index import refresh_automatic_materials
from vx_materials_api.bootstrap import TENANT_ID, bootstrap
from vx_materials_api.db.models import AuditLog, AutomaticCorrectionResult, BatchJob, SanitizationProposal, UserSso
from vx_materials_api.db.temporary_login import temporary_login
from vx_materials_api.main import create_app
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.permissions import permissions_for
from vx_materials_api.services.automatic_corrections import capture_context, process_job

KIT = Path(__file__).parents[2] / "data/desafio01"


@pytest.fixture
def flow_database(migrated_url):
    engine = create_engine(migrated_url)
    try:
        yield engine
    finally:
        # O fluxo confirma transações; apaga também a auditoria para não contaminar testes posteriores.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE audit_logs, datasets, reference_versions, materials_master, "
                    "sanitization_proposals, batch_jobs CASCADE"
                )
            )
            connection.execute(text("DELETE FROM users_sso WHERE issuer='automatic-test'"))
        engine.dispose()


def test_real_batch_applies_and_refreshes_search(migrated_url, flow_database, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("AUTOMATIC_CORRECTION_MODE", "APPLY")
    admin = flow_database
    with admin.begin() as connection:
        connection.execute(
            text("TRUNCATE datasets, reference_versions, materials_master, sanitization_proposals, batch_jobs CASCADE")
        )
    with (
        temporary_login(migrated_url, "api_user") as api_url,
        temporary_login(migrated_url, "batch_user") as batch_url,
        temporary_login(migrated_url, "mcp_reader") as mcp_url,
    ):
        api = create_engine(api_url)
        dataset_id = bootstrap(KIT, api, LocalObjectStore(tmp_path / "kit")).dataset_id
        # Mantém dois registros reais, sem alterar os valores; reduz só o volume do teste integrado.
        with admin.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM material_inventory_snapshots WHERE material_id IN "
                    "(SELECT id FROM materials_master WHERE material_code NOT IN ('24794045','16454102'))"
                )
            )
            connection.execute(text("DELETE FROM materials_master WHERE material_code NOT IN ('24794045','16454102')"))
        factory = sessionmaker(api, expire_on_commit=False)
        catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
        with factory.begin() as db:
            user = UserSso(
                id=uuid.uuid4(),
                tenant_id=TENANT_ID,
                issuer="automatic-test",
                subject=str(uuid.uuid4()),
                display_name="Governança",
                roles_snapshot=["ROLE_GOVERNANCA_PDM"],
            )
            db.add(user)
            db.flush()
            identity = Identity(
                user_id=user.id,
                tenant_id=TENANT_ID,
                roles=("ROLE_GOVERNANCA_PDM",),
                permissions=permissions_for(("ROLE_GOVERNANCA_PDM",)),
                center_codes=frozenset(
                    {"1100", "1200", "1300", "1400", "1500", "1600", "2100", "2200", "2300", "9000"}
                ),
                csrf_token="csrf",
            )
            job = BatchJob(
                id=uuid.uuid4(),
                tenant_id=TENANT_ID,
                requested_by_user_id=user.id,
                dataset_id=dataset_id,
                job_type="SANITIZE",
                pdm_version=catalog.version,
                status="QUEUED",
                automatic_corrections=capture_context(identity),
            )
            db.add(job)
        metrics = run_sanitize(
            str(KIT / "03_padrao_cadastro_PDM.xlsx"),
            str(job.id),
            database_url=batch_url,
            store=LocalObjectStore(tmp_path / "batch"),
        )
        assert metrics["inserted"] > 0

        def indexer(tenant, ids):
            return refresh_automatic_materials(batch_url, tenant, ids, catalog)

        process_job(factory, job.id, catalog, indexer=indexer)
        with factory() as db:
            results = list(db.scalars(select(AutomaticCorrectionResult)))
            applied = [row for row in results if row.status == "APPLIED"]
            assert len(applied) == 2, [(row.status, row.reasons) for row in results]
            assert all(row.status in {"APPLIED", "REVIEW", "STALE"} for row in results)
            assert all(row.index_status == "CURRENT" for row in applied), [row.index_error for row in results]
            assert len(list(db.scalars(select(AuditLog).where(AuditLog.action == "PROPOSAL_AUTO_APPLY")))) == 2
            assert all(p.technical_reviewer_id is None for p in db.scalars(select(SanitizationProposal)))
        app = create_app(session_factory=factory, identity_provider=lambda _: identity)
        app.state.pdm_catalog = catalog
        with TestClient(app) as client:
            response = client.get("/api/v1/materials", params={"q": "24794045"})
            assert response.status_code == 200, response.text
            assert response.json()["items"][0]["unit"] == "PC"
            report = client.get(f"/api/v1/batch/jobs/{job.id}/automatic-corrections")
            assert report.status_code == 200, report.text
            assert report.json()["counts"]["applied"] == 2
            detail = client.get(f"/api/v1/sanitization/{applied[0].proposal_id}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["application_mode"] == "AUTOMATIC"
            assert detail.json()["automation"]["status"] == "APPLIED"
        # A credencial de busca lê o índice reconstruído, sem acesso à tabela de decisões.
        mcp = create_engine(mcp_url)
        with mcp.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM mcp_search_index")).scalar_one() == 2
            assert connection.execute(text("SELECT count(*) FROM mcp_automatic_index_pending")).scalar_one() == 0
            row = connection.execute(
                text(
                    "SELECT extracted_attributes FROM mcp_search_index i "
                    "JOIN mcp_catalog c ON c.id=i.material_id WHERE c.material_code='16454102'"
                )
            ).one()
            assert row[0]["MATERIAL"] == "NBR"
        mcp.dispose()
        api.dispose()
