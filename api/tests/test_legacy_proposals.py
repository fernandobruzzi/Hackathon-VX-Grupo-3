"""A migração preserva propostas antigas sem tratá-las como revisão validada."""

import importlib
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import insert, select

from vx_materials_api.db.models import AuditLog, SanitizationProposal


def test_legacy_proposals_become_stale_with_a_system_audit(connection):
    proposal_id = uuid.uuid4()
    connection.execute(
        insert(SanitizationProposal).values(
            id=proposal_id,
            tenant_id=uuid.uuid4(),
            proposal_type="MERGE",
            members=[],
            changeset={"legacy": True},
            changeset_hash="original",
            technical_review_status="PENDING",
            fiscal_review_status="NOT_REQUIRED",
        )
    )
    migration = importlib.import_module("vx_materials_api.db.migrations.versions.0005_inventory_consolidation")
    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        migration.upgrade()
    row = (
        connection.execute(select(SanitizationProposal).where(SanitizationProposal.id == proposal_id)).mappings().one()
    )
    assert row["status"] == "STALE"
    assert row["version"] == 2
    assert row["changeset"] == {"legacy": True}
    assert row["changeset_hash"] == "original"
    event = connection.execute(select(AuditLog).where(AuditLog.entity_id == str(proposal_id))).mappings().one()
    assert event["actor_type"] == "SYSTEM"
    assert event["before_json"]["changeset"] == {"legacy": True}
    assert event["after_json"]["status"] == "STALE"
