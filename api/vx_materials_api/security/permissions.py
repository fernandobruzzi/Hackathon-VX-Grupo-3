"""Permissões públicas por grupo Cognito; grupos desconhecidos nunca concedem acesso."""

COMMON = frozenset(
    {"chat:use", "materials:read", "inventory:read", "orders:create", "orders:read_own", "orders:update_own"}
)
ROLE_PERMISSIONS = {
    "ROLE_SOLICITANTE": COMMON | {"audit:own"},
    "ROLE_GOVERNANCA_PDM": COMMON
    | {
        "orders:decide",
        "queue:read",
        "merge:decide",
        "enrichment:decide",
        "batch:run",
        "metrics:quality",
        "audit:technical",
    },
    "ROLE_AUDITOR_FISCAL": COMMON
    | {"queue:read_audit", "ncm:decide", "metrics:quality", "metrics:financial", "audit:fiscal"},
    # Diagnóstico técnico das chamadas MCP; não aprova, não publica e não administra.
    "ROLE_DEV_TI": COMMON | {"chat:diagnostics"},
}
PERSONA_ROLES = {
    "SOLICITANTE_OPERACAO": "ROLE_SOLICITANTE",
    "GESTOR_CADASTRO": "ROLE_GOVERNANCA_PDM",
    "AUDITOR_FISCAL": "ROLE_AUDITOR_FISCAL",
    "DEV_TI": "ROLE_DEV_TI",
}


def permissions_for(roles: tuple[str, ...]) -> frozenset[str]:
    return frozenset().union(*(ROLE_PERMISSIONS.get(role, frozenset()) for role in roles))
