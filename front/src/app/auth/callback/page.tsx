"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Seta } from "@/components/ui";

/**
 * Integração: lê code e state da URL e faz POST /api/v1/auth/sso-callback { code, state }.
 * A resposta traz redirect_path (ex.: "/chat") e o cookie __Host-vx_session.
 */
export default function CallbackPage() {
  const router = useRouter();
  useEffect(() => { const t = setTimeout(() => router.replace("/chat/"), 700); return () => clearTimeout(t); }, [router]);
  return (
    <div className="grid min-h-dvh place-items-center">
      <div className="flex flex-col items-center gap-4">
        <Seta className="h-12 w-11 animate-bounce" />
        <p className="text-sm font-semibold">Validando sua sessão…</p>
        <p className="font-mono text-xs text-muted">state · nonce · PKCE</p>
      </div>
    </div>
  );
}
