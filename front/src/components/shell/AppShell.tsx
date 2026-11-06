"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  ClipboardList,
  FileSearch,
  GitMerge,
  History,
  LogOut,
  MessagesSquare,
  Moon,
  PackageSearch,
  PlayCircle,
  Sun,
  ChevronDown,
  Check,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { can, PERSONAS } from "@/lib/permissions";
import { cn } from "@/lib/format";
import type { Permission } from "@/types/api";
import { pendingCounts } from "@/mocks/queue";

type NavItem = {
  href: string;
  label: string;
  icon: React.ElementType;
  perms: Permission[];
  badge?: (role: string) => number | undefined;
};
const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Pedir",
    items: [
      { href: "/chat/", label: "Novo pedido (chat)", icon: MessagesSquare, perms: ["chat:use"] },
      { href: "/pedidos/", label: "Meus pedidos", icon: ClipboardList, perms: ["orders:read_own"] },
      {
        href: "/materiais/",
        label: "Materiais e estoque",
        icon: PackageSearch,
        perms: ["materials:read"],
      },
    ],
  },
  {
    section: "Sanear",
    items: [
      {
        href: "/saneamento/",
        label: "Fila de revisão",
        icon: GitMerge,
        perms: ["queue:read", "queue:read_audit"],
        badge: (r) =>
          r === "ROLE_AUDITOR_FISCAL" ? pendingCounts.fiscal : pendingCounts.technical,
      },
      {
        href: "/enriquecimento/",
        label: "Evidências",
        icon: FileSearch,
        perms: ["enrichment:decide", "queue:read_audit"],
      },
      { href: "/batch/", label: "Processamento em lote", icon: PlayCircle, perms: ["batch:run"] },
    ],
  },
  {
    section: "Acompanhar",
    items: [
      {
        href: "/dashboard/",
        label: "Qualidade da base",
        icon: BarChart3,
        perms: ["metrics:quality"],
      },
      {
        href: "/auditoria/",
        label: "Auditoria",
        icon: History,
        perms: ["audit:own", "audit:technical", "audit:fiscal"],
      },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, ready, signOut, theme, toggleTheme, authMode, error, backend } = useAuth();
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    if (ready && !me) router.replace("/login/");
  }, [ready, me, router]);
  if (!ready || !me)
    return (
      <div className="grid min-h-dvh place-items-center text-sm text-muted">Carregando sessão…</div>
    );
  const role = me.user.roles[0];

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col bg-profundo px-4 py-6 text-on-profundo lg:flex">
        <Link href="/chat/" className="px-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/02_logo_horizontal_fundo_escuro.svg"
            alt="Do Fundo do Poço"
            className="h-12 w-auto"
          />
        </Link>
        <p className="mt-2 px-2 font-mono text-[11px] text-on-profundo/70">
          Cadastro de materiais · VX
        </p>
        <nav className="mt-8 flex flex-1 flex-col gap-6 overflow-y-auto">
          {NAV.map((g) => {
            const items = g.items.filter((i) => can(me, ...i.perms));
            if (!items.length) return null;
            return (
              <div key={g.section}>
                <p className="px-2 text-[11px] font-extrabold tracking-[0.08em] text-on-profundo/60 uppercase">
                  {g.section}
                </p>
                <ul className="mt-2 flex flex-col gap-0.5">
                  {items.map((i) => {
                    const active = path?.startsWith(i.href);
                    const n = i.badge?.(role);
                    return (
                      <li key={i.href}>
                        <Link
                          href={i.href}
                          className={cn(
                            "flex items-center gap-3 rounded-[10px] px-3 py-2.5 text-sm font-semibold",
                            active
                              ? "bg-esmeralda text-on-esmeralda"
                              : "text-on-profundo hover:bg-white/8",
                          )}
                        >
                          <i.icon className="size-[18px]" aria-hidden />
                          <span className="flex-1">{i.label}</span>
                          {!!n && (
                            <span
                              className={cn(
                                "rounded-full px-2 py-0.5 font-mono text-[11px]",
                                active ? "bg-on-esmeralda text-esmeralda" : "bg-white/12",
                              )}
                            >
                              {n}
                            </span>
                          )}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>
        <button
          onClick={async () => {
            try {
              await signOut();
              router.replace("/login/");
            } catch {
              window.alert("Não foi possível confirmar a saída. Tente novamente.");
            }
          }}
          className="mt-4 flex items-center gap-2 rounded-[10px] px-3 py-2 text-sm text-on-profundo/80 hover:bg-white/8"
        >
          <LogOut className="size-4" /> Sair
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-surface-2 bg-ink/95 px-6 backdrop-blur">
          <MobileNav />
          <div className="ml-auto flex items-center gap-3">
            <button
              onClick={toggleTheme}
              aria-label="Alternar tema"
              className="grid size-10 place-items-center rounded-md ring-1 ring-surface-2 ring-inset hover:bg-surface"
            >
              {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4" />}
            </button>
            <PersonaSwitcher />
          </div>
        </header>
        <main key={me.user.id} className="mx-auto w-full max-w-[1280px] flex-1 px-6 py-8 lg:px-10">
          {backend && (
            <p className="mb-4 text-xs text-muted">
              Chat, saneamento, batch, dashboard e auditoria usam dados persistidos. Demais telas em
              demonstração.
            </p>
          )}
          {authMode === "local" && (
            <p className="mb-4 text-xs text-muted">
              Sessão local de teste · identidade e permissões verificadas pela API.
            </p>
          )}
          {error && (
            <p role="alert" className="mb-4 text-sm text-alerta">
              {error}
            </p>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}

/** Fast-Switch Demo Persona (Arquitetura, seção 2). Integração: POST /api/v1/auth/demo/switch e refetch de /auth/me. */
export function PersonaSwitcher() {
  const { me, switchPersona, authMode, backend } = useAuth();
  const [open, setOpen] = useState(false);
  if (!me) return null;
  const current = PERSONAS.find((p) => p.label === me.demo.active_persona);
  // No Cognito, só contas da lista de demonstração com DEMO_MODE têm persona e podem trocar.
  if (!current || (authMode === "cognito" && !me.demo.enabled))
    return <span className="text-sm font-semibold">{me.user.display_name}</span>;
  const displayName = backend ? me.user.display_name : current.name;
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-3 rounded-md bg-surface py-1.5 pr-3 pl-1.5 ring-1 ring-surface-2 ring-inset"
      >
        <span className="grid size-8 place-items-center rounded-full bg-profundo text-xs font-extrabold text-esmeralda">
          {displayName.slice(0, 1)}
        </span>
        <span className="hidden text-left leading-tight sm:block">
          <span className="block text-sm font-bold">{displayName}</span>
          <span className="block text-[11px] font-semibold tracking-[0.06em] text-verde uppercase">
            {current.short}
          </span>
        </span>
        <ChevronDown className="size-4 text-muted" />
      </button>
      {open && (
        <div className="absolute top-14 right-0 w-80 rounded-lg bg-surface p-2 shadow-[0_0_0_1px_var(--surface-2)]">
          <p className="px-3 pt-1 pb-2 text-[11px] font-extrabold tracking-[0.08em] text-muted uppercase">
            Trocar persona · modo demo
          </p>
          {PERSONAS.map((p) => (
            <button
              key={p.label}
              onClick={() => {
                switchPersona(p.label);
                setOpen(false);
              }}
              className="flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left hover:bg-ink"
            >
              <span className="mt-0.5 grid size-5 shrink-0 place-items-center">
                {p.label === current.label && <Check className="size-4 text-verde" />}
              </span>
              <span>
                <span className="block text-sm font-bold">{p.short}</span>
                <span className="block text-xs leading-5 text-muted">{p.description}</span>
                <span className="mt-1 block font-mono text-[11px] text-muted">{p.role}</span>
              </span>
            </button>
          ))}
          <p className="px-3 pt-2 pb-1 text-[11px] leading-4 text-muted">
            {authMode === "cognito"
              ? "Cada persona é uma sessão Cognito já autenticada neste navegador; sem ela, o login da conta é pedido. A auditoria registra o usuário real."
              : "Cada persona é uma sessão de teste local; a auditoria registra o usuário da sessão."}
          </p>
        </div>
      )}
    </div>
  );
}

function MobileNav() {
  const { me } = useAuth();
  const path = usePathname();
  if (!me) return null;
  const items = NAV.flatMap((g) => g.items).filter((i) => can(me, ...i.perms));
  return (
    <select
      aria-label="Navegação"
      value={items.find((i) => path?.startsWith(i.href))?.href ?? ""}
      onChange={(e) => (window.location.href = e.target.value)}
      className="h-10 rounded-md bg-surface px-3 text-sm font-semibold ring-1 ring-surface-2 ring-inset lg:hidden"
    >
      {items.map((i) => (
        <option key={i.href} value={i.href}>
          {i.label}
        </option>
      ))}
    </select>
  );
}
