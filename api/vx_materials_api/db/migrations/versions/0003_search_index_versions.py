"""Índice de busca por versão, sem exigir job.

O batch reconstrói o índice de uma versão por inteiro, e a busca só lê a versão que ela própria usa.
Jobs ainda não são criados pela API (#21), então o vínculo com o job passa a ser opcional.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("material_search_index", "job_id", nullable=True)
    op.drop_constraint("uq_material_search_index_material_id_job_id", "material_search_index", type_="unique")
    op.create_unique_constraint(
        "uq_material_search_index_material_id_normalization_version",
        "material_search_index",
        ["material_id", "normalization_version"],
    )
    op.create_index(
        "ix_material_search_index_candidate_identity_key", "material_search_index", ["candidate_identity_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_material_search_index_candidate_identity_key", table_name="material_search_index")
    op.drop_constraint(
        "uq_material_search_index_material_id_normalization_version", "material_search_index", type_="unique"
    )
    op.execute("DELETE FROM material_search_index WHERE job_id IS NULL")
    op.create_unique_constraint(
        "uq_material_search_index_material_id_job_id", "material_search_index", ["material_id", "job_id"]
    )
    op.alter_column("material_search_index", "job_id", nullable=False)
