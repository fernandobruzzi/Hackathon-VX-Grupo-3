"""Autorização de ação e recurso, sempre a partir da identidade autenticada."""

from vx_materials_api.errors import ApiProblem
from vx_materials_api.security.permissions import ROLE_PERMISSIONS


def has_permission(identity, permission: str) -> bool:
    return permission in identity.permissions and any(
        permission in ROLE_PERMISSIONS.get(role, ()) for role in identity.roles
    )


def require_permission(identity, permission: str) -> str:
    """Devolve o papel efetivo autorizado; nunca aceita um papel indicado no payload."""
    if not has_permission(identity, permission):
        raise ApiProblem(403, "FORBIDDEN", "Seu papel não autoriza esta ação.")
    return next(role for role in identity.roles if permission in ROLE_PERMISSIONS.get(role, ()))


def effective_permissions(identity) -> frozenset[str]:
    return frozenset(permission for permission in identity.permissions if has_permission(identity, permission))


def require_any_permission(identity, *permissions: str) -> str:
    for permission in permissions:
        if has_permission(identity, permission):
            return require_permission(identity, permission)
    raise ApiProblem(403, "FORBIDDEN", "Seu papel não autoriza esta consulta.")


def require_center(identity, center: str):
    if center not in identity.center_codes:
        raise ApiProblem(403, "FORBIDDEN", "Centro fora do escopo do usuário.")


def require_resource_scope(identity, tenant_id, center_codes=()):
    if tenant_id != identity.tenant_id or set(center_codes) - set(identity.center_codes):
        raise ApiProblem(404, "NOT_FOUND", "Recurso não encontrado no seu escopo.")


def require_conversation_owner(identity, conversation):
    require_permission(identity, "chat:use")
    if conversation is None:
        raise ApiProblem(404, "NOT_FOUND", "Conversa não encontrada.")
    require_resource_scope(identity, conversation.tenant_id)
    if conversation.owner_user_id != identity.user_id:
        # Papéis de revisão não concedem acesso geral às conversas de terceiros.
        raise ApiProblem(404, "NOT_FOUND", "Conversa não encontrada.")
