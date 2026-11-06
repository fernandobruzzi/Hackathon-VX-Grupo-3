"""Vincula revisões técnica e fiscal à ficha de cadastro aprovada."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_order_fiscal_review"
down_revision = "0014_order_supplements"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "registration_orders",
        sa.Column("review_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade():
    op.drop_column("registration_orders", "review_data")
