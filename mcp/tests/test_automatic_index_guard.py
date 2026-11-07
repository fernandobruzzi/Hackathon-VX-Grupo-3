"""Uma instância de busca já criada recusa índice pendente, inclusive consulta vazia."""

import uuid

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import create_engine, text
from test_current_inventory import engines as engines
from test_current_inventory import kit as kit

from vx_materials_mcp.repositories.catalog_repository import CatalogRepository


def test_pending_automatic_index_blocks_cached_repository(database, kit):
    tenant = kit
    admin = database["admin"]
    reader = create_engine(database["reader"])
    repository = CatalogRepository(reader, str(tenant))
    assert repository.indexed("version-for-test") == 0
    user, job, run, result = [uuid.uuid4() for _ in range(4)]
    try:
        with admin.begin() as db:
            dataset = db.execute(text("SELECT id FROM datasets WHERE tenant_id=:t LIMIT 1"), {"t": tenant}).scalar_one()
            proposal = db.execute(
                text("SELECT id FROM sanitization_proposals WHERE tenant_id=:t LIMIT 1"), {"t": tenant}
            ).scalar_one()
            db.execute(
                text(
                    "INSERT INTO users_sso (id,tenant_id,issuer,subject,display_name) "
                    "VALUES (:id,:t,'guard-test',:s,'Governança')"
                ),
                {"id": user, "t": tenant, "s": str(user)},
            )
            db.execute(
                text(
                    "INSERT INTO batch_jobs (id,tenant_id,requested_by_user_id,dataset_id,job_type,pdm_version) "
                    "VALUES (:id,:t,:u,:d,'SANITIZE','test')"
                ),
                {"id": job, "t": tenant, "u": user, "d": dataset},
            )
            db.execute(
                text(
                    "INSERT INTO automatic_correction_runs (id,tenant_id,job_id,mode,policy_version,rules_signature) "
                    "VALUES (:id,:t,:j,'APPLY','test','rules')"
                ),
                {"id": run, "t": tenant, "j": job},
            )
            db.execute(
                text(
                    "INSERT INTO automatic_correction_results (id,tenant_id,run_id,proposal_id,status,index_status) "
                    "VALUES (:id,:t,:r,:p,'APPLIED','FAILED')"
                ),
                {"id": result, "t": tenant, "r": run, "p": proposal},
            )
        for query in (
            lambda: repository.indexed("version-for-test"),
            lambda: repository.full_text([], "version-for-test", None, 10),
            lambda: repository.by_identity("key", "version-for-test"),
        ):
            with pytest.raises(ToolError, match="Índice aguarda atualização"):
                query()
        with admin.begin() as db:
            db.execute(
                text("UPDATE automatic_correction_results SET index_status='CURRENT' WHERE id=:id"), {"id": result}
            )
        assert repository.indexed("version-for-test") == 0
        assert repository.full_text([], "version-for-test", None, 10) == []
    finally:
        with admin.begin() as db:
            for table, identifier in (
                ("automatic_correction_results", result),
                ("automatic_correction_runs", run),
                ("batch_jobs", job),
                ("users_sso", user),
            ):
                db.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": identifier})
        reader.dispose()
