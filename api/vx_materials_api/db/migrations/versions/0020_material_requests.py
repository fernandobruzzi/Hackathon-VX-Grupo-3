"""Solicitações de material com protocolo, escopo e vínculos existentes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0020_material_requests"
down_revision = "0019_center_names"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "material_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("protocol_number", sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users_sso.id"), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("material_id", pg.UUID(as_uuid=True), sa.ForeignKey("materials_master.id")),
        sa.Column("quantity", sa.Numeric(24, 6), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("center_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("closure_reason", sa.Text()),
        sa.Column("chat_session_id", pg.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id")),
        sa.Column("registration_order_id", pg.UUID(as_uuid=True), sa.ForeignKey("registration_orders.id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="positive_quantity"),
        sa.CheckConstraint("length(btrim(unit)) > 0", name="unit"),
        sa.CheckConstraint("length(btrim(original_text)) > 0", name="original_text"),
        sa.CheckConstraint("length(btrim(center_code)) > 0", name="center_code"),
        sa.CheckConstraint("version > 0", name="version"),
        sa.CheckConstraint(
            "status IN ('EM_IDENTIFICACAO', 'AGUARDANDO_CADASTRO', 'EM_ATENDIMENTO', 'ENCERRADA')", name="status"
        ),
        sa.CheckConstraint("(status = 'ENCERRADA') = (closure_reason IS NOT NULL)", name="closure_reason"),
    )
    op.create_index(
        "ix_material_requests_tenant_id_requester_user_id", "material_requests", ["tenant_id", "requester_user_id"]
    )
    op.create_index(
        "ix_material_requests_tenant_id_center_code_status", "material_requests", ["tenant_id", "center_code", "status"]
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON material_requests TO api_user")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE material_requests_protocol_number_seq TO api_user")


def downgrade():
    op.drop_table("material_requests")
