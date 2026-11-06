"""Views mínimas para escopo de recursos e elegibilidade do enriquecimento MCP.

Revision ID: 0014_mcp_resource_scope
Revises: 0013_manual_reviews
"""

from alembic import op

revision = "0014_mcp_resource_scope"
down_revision = "0013_manual_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE VIEW mcp_callers AS SELECT id, tenant_id FROM users_sso WHERE disabled_at IS NULL")
    op.execute("CREATE VIEW mcp_datasets AS SELECT id, tenant_id, imported_at, real_material_codes FROM datasets")
    op.execute("GRANT SELECT ON mcp_callers, mcp_datasets TO mcp_reader")


def downgrade():
    op.execute("DROP VIEW mcp_datasets")
    op.execute("DROP VIEW mcp_callers")
