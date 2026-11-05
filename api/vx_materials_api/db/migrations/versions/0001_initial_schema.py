"""initial schema

Revision ID: 0001
Revises:
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "datasets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "files", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "real_material_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    op.create_table(
        "materials_master",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("material_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("active_code_target", sa.UUID(), nullable=True),
        sa.Column("original_description_short", sa.Text(), nullable=True),
        sa.Column("original_description_long", sa.Text(), nullable=True),
        sa.Column("pdm_description", sa.Text(), nullable=True),
        sa.Column("pdm_class_id", sa.Text(), nullable=True),
        sa.Column("pdm_version", sa.Text(), nullable=True),
        sa.Column(
            "attributes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("manufacturer", sa.Text(), nullable=True),
        sa.Column("manufacturer_reference", sa.Text(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("ncm", sa.Text(), nullable=True),
        sa.Column("ncm_review_status", sa.Text(), nullable=True),
        sa.Column("identity_key", sa.Text(), nullable=True),
        sa.Column("is_canonical", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "status <> 'ATIVO' OR active_code_target IS NULL", name=op.f("ck_materials_master_active_has_no_target")
        ),
        sa.CheckConstraint("status IN ('ATIVO', 'BLOQUEADO', 'OBSOLETO')", name=op.f("ck_materials_master_status")),
        sa.CheckConstraint(
            "active_code_target IS NULL OR active_code_target <> id", name=op.f("ck_materials_master_no_self_target")
        ),
        sa.ForeignKeyConstraint(
            ["active_code_target"],
            ["materials_master.id"],
            name=op.f("fk_materials_master_active_code_target_materials_master"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_materials_master")),
        sa.UniqueConstraint("tenant_id", "material_code", name=op.f("uq_materials_master_tenant_id_material_code")),
    )
    op.create_index(
        "uq_materials_master_canonical_identity",
        "materials_master",
        ["tenant_id", "identity_key"],
        unique=True,
        postgresql_where=sa.text("is_canonical AND status = 'ATIVO'"),
    )
    op.create_table(
        "reference_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("s3_path", sa.Text(), nullable=True),
        sa.Column("reference_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.CheckConstraint("kind IN ('PDM', 'NCM')", name=op.f("ck_reference_versions_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_versions")),
        sa.UniqueConstraint("kind", "version", name=op.f("uq_reference_versions_kind_version")),
    )
    op.create_table(
        "users_sso",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("roles_snapshot", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users_sso")),
        sa.UniqueConstraint("issuer", "subject", name=op.f("uq_users_sso_issuer_subject")),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("roles_snapshot", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("effective_role", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users_sso.id"], name=op.f("fk_audit_logs_actor_user_id_users_sso")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("browser_context_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tokens_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("csrf_token_hash", sa.Text(), nullable=False),
        sa.Column("demo_label", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users_sso.id"], name=op.f("fk_auth_sessions_user_id_users_sso")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("session_token_hash", name=op.f("uq_auth_sessions_session_token_hash")),
    )
    op.create_table(
        "batch_jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("pdm_version", sa.Text(), nullable=False),
        sa.Column("ncm_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'QUEUED'"), nullable=False),
        sa.Column("task_arn", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "counts", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "checkpoint", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('SANITIZE', 'IMPORT_ORDERS', 'ENRICH_REAL_PRODUCTS')", name=op.f("ck_batch_jobs_job_type")
        ),
        sa.CheckConstraint("status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')", name=op.f("ck_batch_jobs_status")),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], name=op.f("fk_batch_jobs_dataset_id_datasets")),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users_sso.id"], name=op.f("fk_batch_jobs_requested_by_user_id_users_sso")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_jobs")),
    )
    op.create_table(
        "enrichment_sources",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.UUID(), nullable=False),
        sa.Column("attribute_name", sa.Text(), nullable=False),
        sa.Column("proposed_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Text(), nullable=True),
        sa.Column("s3_object_key", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence_level", sa.Text(), nullable=False),
        sa.Column(
            "confidence_basis",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("validated_by_user_id", sa.UUID(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials_master.id"], name=op.f("fk_enrichment_sources_material_id_materials_master")
        ),
        sa.ForeignKeyConstraint(
            ["validated_by_user_id"],
            ["users_sso.id"],
            name=op.f("fk_enrichment_sources_validated_by_user_id_users_sso"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrichment_sources")),
    )
    op.create_table(
        "material_inventory_snapshots",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.UUID(), nullable=False),
        sa.Column("center_code", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("unit_price", sa.Numeric(), nullable=True),
        sa.Column("total_value", sa.Numeric(), nullable=True),
        sa.Column("source_line", sa.BigInteger(), nullable=False),
        sa.Column(
            "raw_record", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_material_inventory_snapshots_dataset_id_datasets")
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials_master.id"],
            name=op.f("fk_material_inventory_snapshots_material_id_materials_master"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_inventory_snapshots")),
        sa.UniqueConstraint(
            "dataset_id", "source_line", name=op.f("uq_material_inventory_snapshots_dataset_id_source_line")
        ),
    )
    op.create_table(
        "operation_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users_sso.id"], name=op.f("fk_operation_requests_user_id_users_sso")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operation_requests")),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name=op.f("uq_operation_requests_user_id_operation_idempotency_key"),
        ),
    )
    op.create_table(
        "registration_orders",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("source_order_id", sa.Text(), nullable=True),
        sa.Column("requester_user_id", sa.UUID(), nullable=True),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("attachment_text", sa.Text(), nullable=True),
        sa.Column("center_code", sa.Text(), nullable=True),
        sa.Column("urgency", sa.Text(), nullable=True),
        sa.Column("pdm_class_id", sa.Text(), nullable=True),
        sa.Column(
            "attributes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "missing_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "candidate_material_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("material_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "origin <> 'CHAT' OR requester_user_id IS NOT NULL", name=op.f("ck_registration_orders_chat_has_requester")
        ),
        sa.CheckConstraint("origin IN ('CHAT', 'IMPORT')", name=op.f("ck_registration_orders_origin")),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'INCOMPLETE', 'READY_FOR_REVIEW', 'EXISTING', 'OUT_OF_SCOPE', 'PENDING_FISCAL', 'REGISTERED', 'REJECTED')",
            name=op.f("ck_registration_orders_status"),
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials_master.id"], name=op.f("fk_registration_orders_material_id_materials_master")
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"], ["users_sso.id"], name=op.f("fk_registration_orders_requester_user_id_users_sso")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_orders")),
        sa.UniqueConstraint(
            "tenant_id", "source_order_id", name=op.f("uq_registration_orders_tenant_id_source_order_id")
        ),
    )
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("registration_order_id", sa.UUID(), nullable=True),
        sa.Column(
            "context", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("pdm_version", sa.Text(), nullable=True),
        sa.Column("ncm_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("active_turn_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users_sso.id"], name=op.f("fk_chat_sessions_owner_user_id_users_sso")
        ),
        sa.ForeignKeyConstraint(
            ["registration_order_id"],
            ["registration_orders.id"],
            name=op.f("fk_chat_sessions_registration_order_id_registration_orders"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
    )
    op.create_table(
        "material_search_index",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("proposed_class_id", sa.Text(), nullable=True),
        sa.Column(
            "extracted_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=512), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("normalization_version", sa.Text(), nullable=True),
        sa.Column("candidate_identity_key", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["batch_jobs.id"], name=op.f("fk_material_search_index_job_id_batch_jobs")),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials_master.id"], name=op.f("fk_material_search_index_material_id_materials_master")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_search_index")),
        sa.UniqueConstraint("material_id", "job_id", name=op.f("uq_material_search_index_material_id_job_id")),
    )
    op.create_index(
        "ix_material_search_index_search_vector",
        "material_search_index",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "sanitization_proposals",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("proposal_type", sa.Text(), nullable=False),
        sa.Column(
            "members", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("primary_material_id", sa.UUID(), nullable=True),
        sa.Column(
            "changeset", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("changeset_hash", sa.Text(), nullable=False),
        sa.Column(
            "evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("technical_review_status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("technical_reviewer_id", sa.UUID(), nullable=True),
        sa.Column("fiscal_review_status", sa.Text(), server_default=sa.text("'NOT_REQUIRED'"), nullable=False),
        sa.Column("fiscal_reviewer_id", sa.UUID(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "fiscal_review_status IN ('PENDING', 'APPROVED', 'REJECTED', 'NOT_REQUIRED')",
            name=op.f("ck_sanitization_proposals_fiscal_review_status"),
        ),
        sa.CheckConstraint(
            "proposal_type IN ('MERGE', 'PDM_CORRECTION', 'UNIT_CORRECTION', 'NCM_CORRECTION', 'ENRICHMENT', 'COMPOSITE')",
            name=op.f("ck_sanitization_proposals_proposal_type"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPLIED', 'REJECTED', 'STALE')", name=op.f("ck_sanitization_proposals_status")
        ),
        sa.CheckConstraint(
            "technical_review_status IN ('PENDING', 'APPROVED', 'REJECTED', 'NOT_REQUIRED')",
            name=op.f("ck_sanitization_proposals_technical_review_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users_sso.id"],
            name=op.f("fk_sanitization_proposals_created_by_user_id_users_sso"),
        ),
        sa.ForeignKeyConstraint(
            ["fiscal_reviewer_id"],
            ["users_sso.id"],
            name=op.f("fk_sanitization_proposals_fiscal_reviewer_id_users_sso"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["batch_jobs.id"], name=op.f("fk_sanitization_proposals_job_id_batch_jobs")
        ),
        sa.ForeignKeyConstraint(
            ["primary_material_id"],
            ["materials_master.id"],
            name=op.f("fk_sanitization_proposals_primary_material_id_materials_master"),
        ),
        sa.ForeignKeyConstraint(
            ["technical_reviewer_id"],
            ["users_sso.id"],
            name=op.f("fk_sanitization_proposals_technical_reviewer_id_users_sso"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sanitization_proposals")),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("client_message_id", sa.UUID(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("author_type", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tool_calls", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("turn_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users_sso.id"], name=op.f("fk_chat_messages_actor_user_id_users_sso")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], name=op.f("fk_chat_messages_session_id_chat_sessions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
        sa.UniqueConstraint(
            "session_id", "client_message_id", name=op.f("uq_chat_messages_session_id_client_message_id")
        ),
        sa.UniqueConstraint("session_id", "sequence", name=op.f("uq_chat_messages_session_id_sequence")),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("sanitization_proposals")
    op.drop_index("ix_material_search_index_search_vector", table_name="material_search_index", postgresql_using="gin")
    op.drop_table("material_search_index")
    op.drop_table("chat_sessions")
    op.drop_table("registration_orders")
    op.drop_table("operation_requests")
    op.drop_table("material_inventory_snapshots")
    op.drop_table("enrichment_sources")
    op.drop_table("batch_jobs")
    op.drop_table("auth_sessions")
    op.drop_table("audit_logs")
    op.drop_table("users_sso")
    op.drop_table("reference_versions")
    op.drop_index(
        "uq_materials_master_canonical_identity",
        table_name="materials_master",
        postgresql_where=sa.text("is_canonical AND status = 'ATIVO'"),
    )
    op.drop_table("materials_master")
    op.drop_table("datasets")
