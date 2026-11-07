"""Decisões automáticas versionadas e recuperação da indexação."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_automatic_corrections"
down_revision = "0016_search_content_version"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "batch_jobs",
        sa.Column("automatic_corrections", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "sanitization_proposals",
        sa.Column("application_mode", sa.Text(), nullable=False, server_default=sa.text("'HUMAN'")),
    )
    for name, columns in [
        (
            "automatic_correction_runs",
            [
                sa.Column("job_id", postgresql.UUID(), sa.ForeignKey("batch_jobs.id"), nullable=False),
                sa.Column("mode", sa.Text(), nullable=False),
                sa.Column("policy_version", sa.Text(), nullable=False),
                sa.Column("rules_signature", sa.Text(), nullable=False),
                sa.Column("target_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
                sa.Column("status", sa.Text(), nullable=False, server_default="RUNNING"),
                sa.UniqueConstraint("job_id"),
                sa.CheckConstraint("mode IN ('SIMULATE', 'APPLY')", name="mode"),
            ],
        ),
        (
            "automatic_correction_results",
            [
                sa.Column("run_id", postgresql.UUID(), sa.ForeignKey("automatic_correction_runs.id"), nullable=False),
                sa.Column("proposal_id", postgresql.UUID(), sa.ForeignKey("sanitization_proposals.id"), nullable=False),
                sa.Column("material_id", postgresql.UUID(), sa.ForeignKey("materials_master.id")),
                sa.Column("status", sa.Text(), nullable=False),
                sa.Column("eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
                sa.Column("reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
                sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
                sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
                sa.Column("index_status", sa.Text(), nullable=False, server_default="NOT_REQUIRED"),
                sa.Column("index_error", sa.Text()),
                sa.UniqueConstraint("run_id", "proposal_id"),
            ],
        ),
    ]:
        op.create_table(
            name,
            sa.Column("id", postgresql.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(), nullable=False),
            *columns,
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {name} TO api_user")
    op.execute("""CREATE VIEW mcp_automatic_index_pending AS
        SELECT DISTINCT tenant_id FROM automatic_correction_results
        WHERE status = 'APPLIED' AND index_status <> 'CURRENT'""")
    op.execute("GRANT SELECT ON mcp_automatic_index_pending TO mcp_reader")
    # O worker de análise não pode armar retroativamente a aplicação de jobs antigos.
    op.execute("REVOKE UPDATE ON batch_jobs FROM batch_user")
    op.execute(
        "GRANT UPDATE (status,heartbeat_at,counts,checkpoint,error_summary,updated_at) ON batch_jobs TO batch_user"
    )


def downgrade():
    op.execute("GRANT UPDATE ON batch_jobs TO batch_user")
    op.execute("DROP VIEW mcp_automatic_index_pending")
    op.drop_table("automatic_correction_results")
    op.drop_table("automatic_correction_runs")
    op.drop_column("sanitization_proposals", "application_mode")
    op.drop_column("batch_jobs", "automatic_corrections")
