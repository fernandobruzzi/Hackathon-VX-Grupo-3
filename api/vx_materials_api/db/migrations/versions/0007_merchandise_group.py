"""Grupo de mercadorias original e revisado no cadastro mestre.

O grupo original vem da carga e nunca muda. O revisado só é gravado por uma proposta aprovada.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("materials_master", sa.Column("original_merchandise_group", sa.Text()))
    op.add_column("materials_master", sa.Column("merchandise_group", sa.Text()))
    # Bases já carregadas: o grupo original está na linha bruta do snapshot, que é imutável.
    op.execute("""UPDATE materials_master m SET original_merchandise_group = s.grupo
        FROM (
            SELECT DISTINCT ON (material_id) material_id, NULLIF(raw_record->>'GRUPO_MERCADORIA', '') AS grupo
            FROM material_inventory_snapshots ORDER BY material_id, source_line
        ) s
        WHERE s.material_id = m.id""")


def downgrade():
    op.drop_column("materials_master", "merchandise_group")
    op.drop_column("materials_master", "original_merchandise_group")
