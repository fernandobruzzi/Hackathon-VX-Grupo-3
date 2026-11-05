"""Sessão de teste para desenvolver sem Cognito. Só existe com APP_ENV=local e LOCAL_TEST_SESSION=true.

Representa a persona Solicitante. O login real (#7) substitui este provedor de identidade.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vx_materials_api import settings
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import UserSso
from vx_materials_api.security.identity import Identity

ISSUER = "local-test-session"
SUBJECT = "SOLICITANTE_OPERACAO"
ROLES = ("ROLE_SOLICITANTE",)
PERMISSIONS = frozenset(
    {"chat:use", "materials:read", "inventory:read", "orders:create", "orders:read_own", "orders:update_own"}
)


def local_identity(db: Session) -> Identity:
    settings.check_local_shortcuts()
    values = {
        "tenant_id": TENANT_ID,
        "issuer": ISSUER,
        "subject": SUBJECT,
        "display_name": "Solicitante (sessão de teste local)",
        "roles_snapshot": list(ROLES),
    }
    db.execute(insert(UserSso).values(values).on_conflict_do_nothing(index_elements=["issuer", "subject"]))
    user_id = db.scalar(select(UserSso.id).where(UserSso.issuer == ISSUER, UserSso.subject == SUBJECT))
    db.commit()
    return Identity(user_id=user_id, tenant_id=TENANT_ID, roles=ROLES, permissions=PERMISSIONS)
