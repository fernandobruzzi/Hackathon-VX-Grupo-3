"""Estoque MCP somente na observacao vigente de cada empresa.

Revision ID: 0011_current_inventory_dataset
Revises: 0010
"""

from alembic import op

revision = "0011_current_inventory_dataset"
down_revision = "0010"
branch_labels = None
depends_on = None


def _views(current_only):
    current = (
        """
        WHERE s.dataset_id = (
            SELECT d.id FROM datasets d WHERE d.tenant_id = s.tenant_id
            ORDER BY d.imported_at DESC, d.id DESC LIMIT 1
        )
    """
        if current_only
        else ""
    )
    for view, financial in [("mcp_inventory", False), ("mcp_inventory_financial", True)]:
        extra = ", s.unit_price / COALESCE(c.factor, 1) AS unit_price, s.total_value" if financial else ""
        op.execute(f"""CREATE OR REPLACE VIEW {view} AS
            SELECT s.tenant_id, s.dataset_id, COALESCE(c.primary_material_id, s.material_id) AS material_id,
                   s.center_code, s.quantity * COALESCE(c.factor, 1) AS quantity,
                   COALESCE(c.unit, s.unit) AS unit {extra}
            FROM material_inventory_snapshots s LEFT JOIN inventory_consolidations c
            ON c.source_snapshot_id = s.id AND c.tenant_id = s.tenant_id
            {current}""")


def upgrade():
    _views(True)


def downgrade():
    _views(False)
