"""A aprovação usa a identidade da sessão e a política central, como o chat."""

from vx_materials_api.bootstrap import TENANT_ID as LOCAL_TENANT
from vx_materials_api.dependencies import current_identity as get_principal
from vx_materials_api.security.identity import Identity as Principal
from vx_materials_api.security.rbac import require_any_permission, require_permission
from vx_materials_api.security.sessions import verify_write as verify_write

__all__ = ["LOCAL_TENANT", "Principal", "get_principal", "require_reviewer", "verify_write"]


def require_reviewer(principal: Principal, area: str | None = None):
    if area is None:
        return require_any_permission(principal, "queue:read", "queue:read_audit")
    return require_permission(principal, "ncm:decide" if area == "FISCAL" else "merge:decide")
