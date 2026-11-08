"""Equivalências técnicas aprovadas e troca registrada na solicitação (#246)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0024_material_equivalences"
down_revision = "0023_chat_material_request"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "material_equivalences",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", pg.UUID(as_uuid=True), sa.ForeignKey("materials_master.id"), nullable=False),
        sa.Column(
            "equivalent_material_id", pg.UUID(as_uuid=True), sa.ForeignKey("materials_master.id"), nullable=False
        ),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("approved_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users_sso.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "material_id", "equivalent_material_id"),
        sa.CheckConstraint("material_id < equivalent_material_id", name="canonical_pair"),
        sa.CheckConstraint("length(btrim(basis)) > 0", name="basis"),
        sa.CheckConstraint("status IN ('APROVADA', 'REVOGADA')", name="status"),
        sa.CheckConstraint("version > 0", name="version"),
    )
    # Sem DELETE: revogação é estado, e o histórico fica na auditoria.
    op.execute("GRANT SELECT, INSERT, UPDATE ON material_equivalences TO api_user")
    op.add_column(
        "material_requests",
        sa.Column("substituted_from_material_id", pg.UUID(as_uuid=True), sa.ForeignKey("materials_master.id")),
    )
    op.add_column(
        "material_requests",
        sa.Column("substitution_equivalence_id", pg.UUID(as_uuid=True), sa.ForeignKey("material_equivalences.id")),
    )
    op.create_check_constraint(
        "substitution",
        "material_requests",
        "(substituted_from_material_id IS NULL) = (substitution_equivalence_id IS NULL)",
    )


def downgrade():
    op.drop_constraint("substitution", "material_requests", type_="check")
    op.drop_column("material_requests", "substitution_equivalence_id")
    op.drop_column("material_requests", "substituted_from_material_id")
    op.drop_table("material_equivalences")
