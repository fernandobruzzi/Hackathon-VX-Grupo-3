"""Vincula cada interpretação de busca à revisão efetiva do material."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0011"
branch_labels = None
depends_on = None

CATALOG = """SELECT id, tenant_id, material_code, status, active_code_target, original_description_short,
original_description_long, pdm_description, pdm_class_id, pdm_version, attributes, manufacturer,
manufacturer_reference, unit, ncm, ncm_review_status, identity_key, is_canonical"""
SEARCH = """SELECT tenant_id, material_id, job_id, proposed_class_id, extracted_attributes, search_vector,
embedding, embedding_model, normalization_version, candidate_identity_key"""


def upgrade():
    # O formato search-index-v2 invalida linhas legadas; fontes novas começam na revisão 1.
    op.add_column(
        "material_search_index", sa.Column("source_version", sa.Integer(), nullable=False, server_default="1")
    )
    op.execute(f"CREATE OR REPLACE VIEW mcp_catalog AS {CATALOG}, version FROM materials_master")
    op.execute(f"CREATE OR REPLACE VIEW mcp_search_index AS {SEARCH}, source_version FROM material_search_index")


def downgrade():
    for view, query, table in [
        ("mcp_search_index", SEARCH, "material_search_index"),
        ("mcp_catalog", CATALOG, "materials_master"),
    ]:
        op.execute(f"DROP VIEW {view}")
        op.execute(f"CREATE VIEW {view} AS {query} FROM {table}")
        op.execute(f"GRANT SELECT ON {view} TO mcp_reader")
    op.drop_column("material_search_index", "source_version")
