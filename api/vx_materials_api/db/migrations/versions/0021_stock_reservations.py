"""Reservas de saldo e movimentos de estoque, sem alterar os snapshots importados.

Revision ID: 0021_stock_reservations
Revises: 0020_material_requests
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0021_stock_reservations"
down_revision = "0020_material_requests"
branch_labels = None
depends_on = None


def _quantity_checks():
    return [
        sa.Column("quantity", sa.Numeric(24, 6), nullable=False),
        sa.CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="positive_quantity"),
    ]


def upgrade():
    op.create_table(
        "stock_reservations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", pg.UUID(as_uuid=True), sa.ForeignKey("material_requests.id"), nullable=False),
        sa.Column("material_id", pg.UUID(as_uuid=True), sa.ForeignKey("materials_master.id"), nullable=False),
        sa.Column("center_code", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ATIVA'")),
        sa.Column("dataset_id", pg.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("created_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users_sso.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        *_quantity_checks(),
        sa.CheckConstraint("status IN ('ATIVA', 'CONSUMIDA', 'CANCELADA')", name="status"),
        sa.CheckConstraint("length(btrim(center_code)) > 0", name="center_code"),
        sa.CheckConstraint("length(btrim(unit)) > 0", name="unit"),
        sa.CheckConstraint("version > 0", name="version"),
    )
    op.create_index(
        "ix_stock_reservations_tenant_id_material_id_center_code_status",
        "stock_reservations",
        ["tenant_id", "material_id", "center_code", "status"],
    )
    op.create_index("ix_stock_reservations_request_id", "stock_reservations", ["request_id"])
    op.create_table(
        "stock_movements",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", pg.UUID(as_uuid=True), sa.ForeignKey("stock_reservations.id"), nullable=False),
        sa.Column("movement_type", sa.Text(), nullable=False),
        sa.Column("reverses_movement_id", pg.UUID(as_uuid=True), sa.ForeignKey("stock_movements.id")),
        sa.Column("dataset_id", pg.UUID(as_uuid=True), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("created_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users_sso.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        *_quantity_checks(),
        sa.CheckConstraint("movement_type IN ('ENTREGA', 'REVERSAO')", name="movement_type"),
        sa.CheckConstraint(
            "(movement_type = 'REVERSAO') = (reverses_movement_id IS NOT NULL)", name="reversal_reference"
        ),
    )
    op.create_index("ix_stock_movements_reservation_id", "stock_movements", ["reservation_id"])
    # A reserva muda de estado; o movimento é somente inserção, e nenhuma das duas toca os snapshots.
    op.execute("GRANT SELECT, INSERT, UPDATE ON stock_reservations TO api_user")
    op.execute("GRANT SELECT, INSERT ON stock_movements TO api_user")


def downgrade():
    op.drop_table("stock_movements")
    op.drop_table("stock_reservations")
