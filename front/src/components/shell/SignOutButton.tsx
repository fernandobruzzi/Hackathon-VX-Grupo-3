"use client";

import { useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

export function SignOutButton({
  onSignedOut,
  appearance = "header",
  className,
}: {
  onSignedOut: () => void;
  appearance?: "header" | "sidebar";
  className?: string;
}) {
  const { signOut, sessionBusy } = useAuth();
  const [leaving, setLeaving] = useState(false);
  const inFlight = useRef(false);
  return (
    <button
      type="button"
      aria-label="Sair da conta"
      aria-busy={leaving}
      disabled={sessionBusy || leaving}
      onClick={async () => {
        if (inFlight.current || sessionBusy) return;
        inFlight.current = true;
        setLeaving(true);
        try {
          // No Cognito o navegador segue para o logout do provedor; não redirecionar por cima.
          if (!(await signOut())) onSignedOut();
        } catch {
          // O provedor reconcilia a identidade e apresenta o erro com a opção de tentar novamente.
        } finally {
          inFlight.current = false;
          setLeaving(false);
        }
      }}
      className={cn(
        "inline-flex h-11 shrink-0 items-center gap-2 rounded-md px-3 text-sm font-semibold whitespace-nowrap transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-45",
        appearance === "sidebar"
          ? "text-on-profundo/80 hover:bg-white/8 focus-visible:outline-esmeralda"
          : "bg-surface text-text ring-1 ring-surface-2 ring-inset hover:bg-ink focus-visible:outline-verde",
        className,
      )}
    >
      <LogOut aria-hidden className="size-4" />
      <span aria-live="polite">{leaving ? "Saindo…" : "Sair"}</span>
    </button>
  );
}
