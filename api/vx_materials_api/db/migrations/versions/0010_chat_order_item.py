"""Preserva o nome do item da ficha confirmada no pedido do chat."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("registration_orders", sa.Column("item_name", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("registration_orders", "item_name")
