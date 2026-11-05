"""Vinculo de consolidacao sem modificar os saldos originais.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_consolidations",
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary_material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("factor", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("conversion_source", sa.Text(), nullable=False),
        sa.CheckConstraint("factor > 0", name=op.f("ck_inventory_consolidations_positive_factor")),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["material_inventory_snapshots.id"]),
        sa.ForeignKeyConstraint(["primary_material_id"], ["materials_master.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["sanitization_proposals.id"]),
        sa.PrimaryKeyConstraint("source_snapshot_id"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON inventory_consolidations TO api_user")
    op.execute("GRANT SELECT ON inventory_consolidations TO batch_user")
    for view, financial in [("mcp_inventory", False), ("mcp_inventory_financial", True)]:
        extra = ", s.unit_price / COALESCE(c.factor, 1) AS unit_price, s.total_value" if financial else ""
        op.execute(f"""CREATE OR REPLACE VIEW {view} AS
            SELECT s.tenant_id, s.dataset_id, COALESCE(c.primary_material_id, s.material_id) AS material_id,
                   s.center_code, s.quantity * COALESCE(c.factor, 1) AS quantity,
                   COALESCE(c.unit, s.unit) AS unit {extra}
            FROM material_inventory_snapshots s LEFT JOIN inventory_consolidations c
            ON c.source_snapshot_id = s.id AND c.tenant_id = s.tenant_id""")


def downgrade():
    for view, financial in [("mcp_inventory", False), ("mcp_inventory_financial", True)]:
        extra = ", unit_price, total_value" if financial else ""
        op.execute(f"""CREATE OR REPLACE VIEW {view} AS
            SELECT tenant_id, dataset_id, material_id, center_code, quantity, unit {extra}
            FROM material_inventory_snapshots""")
    op.drop_table("inventory_consolidations")
