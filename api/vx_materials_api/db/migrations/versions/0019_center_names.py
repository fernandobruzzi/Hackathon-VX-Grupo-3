"""Preserva o nome do centro e recupera nomes dos registros originais."""

import sqlalchemy as sa
from alembic import op

revision = "0019_center_names"
down_revision = "0018_mcp_resource_scope"
branch_labels = None
depends_on = None


def _views(include_name):
    for view, financial in [("mcp_inventory", False), ("mcp_inventory_financial", True)]:
        extra = ", s.unit_price / COALESCE(c.factor, 1) AS unit_price, s.total_value" if financial else ""
        name = ", s.center_name" if include_name else ""
        op.execute(f"""CREATE OR REPLACE VIEW {view} AS
            SELECT s.tenant_id, s.dataset_id, COALESCE(c.primary_material_id, s.material_id) AS material_id,
                   s.center_code, s.quantity * COALESCE(c.factor, 1) AS quantity,
                   COALESCE(c.unit, s.unit) AS unit {extra} {name}
            FROM material_inventory_snapshots s LEFT JOIN inventory_consolidations c
            ON c.source_snapshot_id = s.id AND c.tenant_id = s.tenant_id
            WHERE s.dataset_id = (
                SELECT d.id FROM datasets d WHERE d.tenant_id = s.tenant_id
                ORDER BY d.imported_at DESC, d.id DESC LIMIT 1
            )""")


def upgrade():
    op.add_column("material_inventory_snapshots", sa.Column("center_name", sa.Text(), nullable=True))
    # Só recupera o nome quando o código original coincide com o código persistido.
    op.execute("""UPDATE material_inventory_snapshots
        SET center_name = NULLIF(btrim(regexp_replace(
            substr(raw_record->>'CENTRO', strpos(raw_record->>'CENTRO', '-') + 1),
            '[[:space:]]+', ' ', 'g')), '')
        WHERE strpos(raw_record->>'CENTRO', '-') > 0
          AND btrim(split_part(raw_record->>'CENTRO', '-', 1)) = center_code""")
    _views(True)


def downgrade():
    for view in ("mcp_inventory", "mcp_inventory_financial"):
        op.execute(f"DROP VIEW {view}")
    _views(False)
    for view in ("mcp_inventory", "mcp_inventory_financial"):
        op.execute(f"GRANT SELECT ON {view} TO mcp_reader")
    op.drop_column("material_inventory_snapshots", "center_name")
