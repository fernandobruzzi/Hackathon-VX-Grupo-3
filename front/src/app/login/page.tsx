"use client";

import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Button, Seta } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { PERSONAS } from "@/lib/permissions";
import type { PersonaLabel } from "@/types/api";

/**
 * Integração: botão chama GET /api/v1/auth/sso-start → Cognito (Authorization Code + PKCE) → /auth/callback.
 * No wireframe, o clique já cria a sessão da persona escolhida.
 */
export default function LoginPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const go = (p?: PersonaLabel) => { signIn(p); router.push("/auth/callback/"); };

  return (
    <div className="relative grid min-h-dvh overflow-hidden lg:grid-cols-[1fr_1.1fr]">
      <section className="relative z-10 flex flex-col justify-between px-8 py-10 sm:px-14">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/01_logo_horizontal.svg" alt="Do Fundo do Poço · Hackathon" className="h-14 w-auto self-start dark:hidden" />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/02_logo_horizontal_fundo_escuro.svg" alt="Do Fundo do Poço · Hackathon" className="hidden h-14 w-auto self-start dark:block" />

        <div className="max-w-md py-12">
          <p className="text-[13px] font-extrabold uppercase"><span className="text-verde">VX</span> / Cadastro de materiais</p>
          <span className="mt-2 block h-1 w-14 bg-esmeralda" />
          <h1 className="mt-6 text-[40px] font-extrabold uppercase leading-[1.05] tracking-[-0.01em]">Uma base de materiais que dá pra confiar</h1>
          <p className="mt-4 text-[15px] leading-6 text-muted">Peça itens em linguagem natural, encontre o que já existe e saneie duplicidades, NCM e descrições com revisão humana e trilha de auditoria.</p>
          <Button size="lg" className="mt-8" onClick={() => go()}><LogIn className="size-5" /> Entrar com SSO corporativo</Button>
          <p className="mt-3 text-xs text-muted">Login gerenciado pelo Cognito. Seus tokens ficam no servidor; o navegador recebe só um cookie de sessão.</p>
        </div>

        <div className="rounded-md bg-surface p-4">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-muted">Modo demo · entrar como</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {PERSONAS.map((p) => <Button key={p.label} variant="ghost" size="sm" onClick={() => go(p.label)}>{p.short}</Button>)}
          </div>
        </div>
      </section>

      <section aria-hidden className="relative hidden bg-profundo lg:block">
        <svg viewBox="880 0 1040 1080" preserveAspectRatio="xMaxYMax slice" className="absolute inset-0 size-full">
          <path fill="var(--apoio)" d="M1130 1080C1240 520 1570 180 1920 50V1080Z" />
          <path fill="var(--esmeralda)" d="M1040 1080C1330 770 1640 740 1920 730V900C1630 870 1390 930 1220 1080Z" />
        </svg>
        <div className="absolute left-14 top-16 flex flex-col gap-3 text-on-profundo">
          <Seta className="h-10 w-9" />
          <p className="max-w-xs text-sm leading-6 text-on-profundo/85">23.554 materiais · 520 pedidos de cadastro · 44 classes PDM</p>
        </div>
      </section>
    </div>
  );
}
