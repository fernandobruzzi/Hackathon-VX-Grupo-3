"""Preserva complementos de pedidos separadamente dos textos originais."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_order_supplements"
down_revision = "0013_manual_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "registration_orders",
        sa.Column("supplements", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade():
    op.drop_column("registration_orders", "supplements")
