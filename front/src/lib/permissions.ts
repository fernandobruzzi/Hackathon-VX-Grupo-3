import type { Me, Permission, PersonaLabel, Role } from "@/types/api";

/** Matriz RBAC da Arquitetura (seção 2). O backend é a autoridade; aqui só esconde o que o papel não usa. */
export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  ROLE_SOLICITANTE: [
    "chat:use",
    "materials:read",
    "inventory:read",
    "orders:create",
    "orders:read_own",
    "orders:update_own",
    "audit:own",
  ],
  ROLE_GOVERNANCA_PDM: [
    "chat:use",
    "materials:read",
    "inventory:read",
    "orders:create",
    "orders:read_own",
    "orders:update_own",
    "orders:decide",
    "queue:read",
    "merge:decide",
    "enrichment:decide",
    "batch:run",
    "metrics:quality",
    "audit:technical",
  ],
  ROLE_AUDITOR_FISCAL: [
    "chat:use",
    "materials:read",
    "inventory:read",
    "orders:create",
    "orders:read_own",
    "orders:update_own",
    "queue:read_audit",
    "ncm:decide",
    "metrics:quality",
    "metrics:financial",
    "audit:fiscal",
  ],
  ROLE_DEV_TI: [
    "chat:use",
    "materials:read",
    "inventory:read",
    "orders:create",
    "orders:read_own",
    "orders:update_own",
    "chat:diagnostics",
  ],
};

export const PERSONAS: {
  label: PersonaLabel;
  role: Role;
  name: string;
  short: string;
  description: string;
}[] = [
  {
    label: "SOLICITANTE_OPERACAO",
    role: "ROLE_SOLICITANTE",
    name: "Operação Demo",
    short: "Solicitante",
    description: "Pede itens pelo chat e acompanha os próprios pedidos.",
  },
  {
    label: "GESTOR_CADASTRO",
    role: "ROLE_GOVERNANCA_PDM",
    name: "Fernanda · Cadastro",
    short: "Governança PDM",
    description: "Revisa unificações, enriquecimento e publica cadastros.",
  },
  {
    label: "AUDITOR_FISCAL",
    role: "ROLE_AUDITOR_FISCAL",
    name: "Auditoria Fiscal",
    short: "Auditor fiscal",
    description: "Aprova alterações de NCM e vê o impacto financeiro.",
  },
  {
    label: "DEV_TI",
    role: "ROLE_DEV_TI",
    name: "Dev/TI · Diagnóstico",
    short: "Dev/TI",
    description: "Usa o chat e consulta as chamadas MCP executadas; não aprova nem publica.",
  },
];

export function meFor(label: PersonaLabel): Me {
  const p = PERSONAS.find((x) => x.label === label)!;
  return {
    user: { id: `demo-${label.toLowerCase()}`, display_name: p.name, roles: [p.role] },
    permissions: ROLE_PERMISSIONS[p.role],
    scope: { center_codes: ["1100", "1200", "1300", "2100", "2200", "9000"] },
    demo: { enabled: true, active_persona: label },
    csrf_token: "demo-csrf",
  };
}

export const can = (me: Me | null, ...perms: Permission[]) =>
  !!me && perms.some((p) => me.permissions.includes(p));
