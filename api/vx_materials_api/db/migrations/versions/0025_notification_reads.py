"""Leitura das notificações do solicitante, derivadas da auditoria (#249)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0025_notification_reads"
down_revision = "0024_material_equivalences"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_reads",
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users_sso.id"), primary_key=True),
        sa.Column("audit_log_id", pg.UUID(as_uuid=True), sa.ForeignKey("audit_logs.id"), primary_key=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Só inserir: marcar como lida não se desfaz nem altera a auditoria.
    op.execute("GRANT SELECT, INSERT ON notification_reads TO api_user")


def downgrade():
    op.drop_table("notification_reads")
