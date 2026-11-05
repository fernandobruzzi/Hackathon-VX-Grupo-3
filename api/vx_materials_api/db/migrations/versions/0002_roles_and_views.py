"""Credenciais SQL com permissões mínimas e views do MCP.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ROLES = ("api_user", "batch_user", "mcp_reader")

# Sem DELETE em nenhuma credencial de aplicação, exceto o índice de busca do batch, que é reconstruível.
GRANTS = {
    "api_user": {
        "users_sso": "SELECT, INSERT, UPDATE",
        "auth_sessions": "SELECT, INSERT, UPDATE",
        "audit_logs": "SELECT, INSERT",
        "datasets": "SELECT, INSERT",
        "reference_versions": "SELECT, INSERT, UPDATE",
        "materials_master": "SELECT, INSERT, UPDATE",
        "material_inventory_snapshots": "SELECT, INSERT",
        "material_search_index": "SELECT",
        "batch_jobs": "SELECT, INSERT, UPDATE",
        "sanitization_proposals": "SELECT, INSERT, UPDATE",
        "registration_orders": "SELECT, INSERT, UPDATE",
        "chat_sessions": "SELECT, INSERT, UPDATE",
        "chat_messages": "SELECT, INSERT",
        "enrichment_sources": "SELECT, UPDATE",
        "operation_requests": "SELECT, INSERT, UPDATE",
    },
    "batch_user": {
        "datasets": "SELECT",
        "reference_versions": "SELECT",
        "materials_master": "SELECT",
        "material_inventory_snapshots": "SELECT",
        "registration_orders": "SELECT",
        "batch_jobs": "SELECT, UPDATE",
        "material_search_index": "SELECT, INSERT, UPDATE, DELETE",
        "sanitization_proposals": "SELECT, INSERT, UPDATE",
        "enrichment_sources": "SELECT, INSERT, UPDATE",
    },
}

# O MCP lê somente estas views. Preço e valor ficam em uma view própria, liberada por usuário no
# código do MCP (`inventory_view`), porque o banco só conhece a credencial. O registro bruto fica de fora.
VIEWS = {
    "mcp_catalog": """
        SELECT id, tenant_id, material_code, status, active_code_target, original_description_short,
               original_description_long, pdm_description, pdm_class_id, pdm_version, attributes, manufacturer,
               manufacturer_reference, unit, ncm, ncm_review_status, identity_key, is_canonical
        FROM materials_master
    """,
    "mcp_inventory": """
        SELECT tenant_id, dataset_id, material_id, center_code, quantity, unit
        FROM material_inventory_snapshots
    """,
    "mcp_inventory_financial": """
        SELECT tenant_id, dataset_id, material_id, center_code, quantity, unit, unit_price, total_value
        FROM material_inventory_snapshots
    """,
    "mcp_references": """
        SELECT id, kind, version, reference_date, validation_status
        FROM reference_versions
    """,
    "mcp_search_index": """
        SELECT tenant_id, material_id, job_id, proposed_class_id, extracted_attributes, search_vector, embedding,
               embedding_model, normalization_version, candidate_identity_key
        FROM material_search_index
    """,
    "mcp_evidence": """
        SELECT id, tenant_id, material_id, attribute_name, proposed_value, source_url, source_title, source_excerpt,
               source_page, retrieved_at, confidence_level, confidence_basis, status
        FROM enrichment_sources
    """,
}


def upgrade() -> None:
    for role in ROLES:
        # Roles são globais no servidor: outro banco do mesmo servidor pode já tê-las criado.
        op.execute(f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    for role, tables in GRANTS.items():
        for table, privileges in tables.items():
            op.execute(f"GRANT {privileges} ON {table} TO {role}")
    for view, query in VIEWS.items():
        op.execute(f"CREATE VIEW {view} AS {query}")
        op.execute(f"GRANT SELECT ON {view} TO mcp_reader")


def downgrade() -> None:
    for view in VIEWS:
        op.execute(f"DROP VIEW {view}")
    for role, tables in GRANTS.items():
        for table in tables:
            op.execute(f"REVOKE ALL ON {table} FROM {role}")
    for role in ROLES:
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
