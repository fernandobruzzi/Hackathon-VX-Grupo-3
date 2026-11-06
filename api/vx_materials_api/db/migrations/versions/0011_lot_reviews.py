"""Revisão por amostra de lotes de correções de forma (#120).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _jsonb(name, default="{}"):
    return sa.Column(
        name, postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text(f"'{default}'::jsonb"), nullable=False
    )


def upgrade():
    op.create_table(
        "lot_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_key", sa.Text(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("proposal_type", sa.Text(), nullable=False),
        _jsonb("proposal_versions"),
        _jsonb("sample_ids", "[]"),
        _jsonb("marks"),
        sa.Column("status", sa.Text(), server_default=sa.text("'OPEN'"), nullable=False),
        _jsonb("result"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('OPEN', 'APPROVED', 'RETURNED')", name=op.f("ck_lot_reviews_status")),
        sa.CheckConstraint("tier IN (1, 2)", name=op.f("ck_lot_reviews_tier")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users_sso.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users_sso.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Sem DELETE: a revisão de um lote fica como registro da amostra e da decisão.
    op.execute("GRANT SELECT, INSERT, UPDATE ON lot_reviews TO api_user")


def downgrade():
    op.drop_table("lot_reviews")
