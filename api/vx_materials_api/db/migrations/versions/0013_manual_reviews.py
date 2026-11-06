"""Pendências do batch separadas das propostas aplicáveis.

Revision ID: 0013_manual_reviews
Revises: 0012_current_inventory_dataset
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0013_manual_reviews"
down_revision = "0012_current_inventory_dataset"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_reviews",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("batch_jobs.id")),
        sa.Column("dataset_id", pg.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("material_id", pg.UUID(as_uuid=True), sa.ForeignKey("materials_master.id"), nullable=False),
        sa.Column("expected_material_version", sa.Integer(), nullable=False),
        sa.Column("reasons", pg.ARRAY(sa.Text()), nullable=False),
        sa.Column("observation", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rules_signature", sa.Text(), nullable=False),
        sa.Column("pdm_version", sa.Text(), nullable=False),
        sa.Column("pdm_source_sha256", sa.Text(), nullable=False),
        sa.Column("proposal_id", pg.UUID(as_uuid=True), sa.ForeignKey("sanitization_proposals.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "material_id"),
    )
    op.create_index("ix_manual_reviews_tenant_id_run_id", "manual_reviews", ["tenant_id", "run_id"])
    op.execute("GRANT SELECT, INSERT ON manual_reviews TO batch_user")
    op.execute("GRANT SELECT ON manual_reviews TO api_user")
    op.execute("GRANT UPDATE (proposal_id) ON manual_reviews TO api_user")


def downgrade():
    op.drop_table("manual_reviews")
