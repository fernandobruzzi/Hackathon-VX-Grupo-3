"""Recria equivalentes autorizados e notificações do solicitante (#246, #249) depois do hackathon."""

import importlib.util
from pathlib import Path

revision = "0027_restore_requester_extensions"
down_revision = "0026_drop_requester_extensions"
branch_labels = None
depends_on = None


def _drop():
    path = Path(__file__).with_name("0026_drop_requester_extensions.py")
    spec = importlib.util.spec_from_file_location("_vx_0026_drop_requester_extensions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade():
    _drop().downgrade()


def downgrade():
    _drop().upgrade()
