"""Transações OAuth de uso único, vinculadas ao navegador.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_transactions",
        sa.Column("state_hash", sa.Text(), primary_key=True),
        sa.Column("browser_context_hash", sa.Text(), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON login_transactions TO api_user")


def downgrade():
    op.drop_table("login_transactions")
