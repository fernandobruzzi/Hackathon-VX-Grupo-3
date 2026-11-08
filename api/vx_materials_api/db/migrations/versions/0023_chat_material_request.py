"""Uma conversa corresponde a uma solicitação de material."""

from alembic import op

revision = "0023_chat_material_request"
down_revision = "0022_purchase_forwards"
branch_labels = None
depends_on = None


def upgrade():
    # Uma base com duplicações prévias precisa de revisão, sem descartar solicitações.
    op.create_unique_constraint("uq_material_requests_chat_session_id", "material_requests", ["chat_session_id"])


def downgrade():
    op.drop_constraint("uq_material_requests_chat_session_id", "material_requests", type_="unique")
