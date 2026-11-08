"""Encaminhamentos para compras do material já cadastrado, sem novo cadastro."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0022_purchase_forwards"
down_revision = "0021_stock_reservations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "purchase_forwards",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("material_request_id", pg.UUID(as_uuid=True), sa.ForeignKey("material_requests.id"), nullable=False),
        sa.Column("request_version", sa.Integer(), nullable=False),
        sa.Column("material_id", pg.UUID(as_uuid=True), sa.ForeignKey("materials_master.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 6), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("center_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("forwarded_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users_sso.id"), nullable=False),
        sa.Column("handled_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users_sso.id")),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("material_request_id", "request_version"),
        sa.CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="positive_quantity"),
        sa.CheckConstraint("length(btrim(unit)) > 0", name="unit"),
        sa.CheckConstraint("length(btrim(center_code)) > 0", name="center_code"),
        sa.CheckConstraint("status IN ('ENCAMINHADO', 'ACEITO', 'DEVOLVIDO', 'CANCELADO')", name="status"),
        sa.CheckConstraint("(status IN ('DEVOLVIDO', 'CANCELADO')) = (reason IS NOT NULL)", name="reason"),
        sa.CheckConstraint("(status IN ('ACEITO', 'DEVOLVIDO')) = (handled_by_user_id IS NOT NULL)", name="handled_by"),
        sa.CheckConstraint("version > 0", name="version"),
        sa.CheckConstraint("request_version > 0", name="request_version"),
    )
    op.create_index(
        "ix_purchase_forwards_tenant_id_center_code_status", "purchase_forwards", ["tenant_id", "center_code", "status"]
    )
    # Sem DELETE: devolução e cancelamento são estados, e o histórico fica na auditoria.
    op.execute("GRANT SELECT, INSERT, UPDATE ON purchase_forwards TO api_user")


def downgrade():
    op.drop_table("purchase_forwards")
