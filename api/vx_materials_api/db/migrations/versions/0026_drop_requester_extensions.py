"""Remove equivalentes autorizados e notificações do solicitante (#246, #249) do escopo do hackathon.

As revisões 0024 e 0025 ficam para que bancos já migrados continuem com histórico válido; esta
revisão desfaz o que elas criaram. O código está num PR em rascunho para depois do hackathon.
"""

import importlib.util
from pathlib import Path


revision = "0026_drop_requester_extensions"
down_revision = "0025_notification_reads"
branch_labels = None
depends_on = None


def _revision(name):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_vx_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade():
    _revision("0025_notification_reads").downgrade()
    _revision("0024_material_equivalences").downgrade()


def downgrade():
    _revision("0024_material_equivalences").upgrade()
    _revision("0025_notification_reads").upgrade()
