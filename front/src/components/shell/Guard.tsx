"use client";

import { ShieldX } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { Permission } from "@/types/api";

/** Esconde a tela quando a persona não tem a permissão. O backend continua respondendo 403 (critério do MVP). */
export function Guard({ perms, children }: { perms: Permission[]; children: React.ReactNode }) {
  const { me } = useAuth();
  if (can(me, ...perms)) return <>{children}</>;
  return (
    <div className="mx-auto mt-16 flex max-w-lg flex-col items-start gap-4 rounded-lg bg-surface p-8">
      <span className="grid size-12 place-items-center rounded-full bg-profundo">
        <ShieldX className="size-6 text-esmeralda" />
      </span>
      <p className="font-mono text-xs text-muted">HTTP 403 · FORBIDDEN</p>
      <h1 className="text-2xl font-extrabold">Seu papel não tem acesso a esta tela</h1>
      <p className="text-sm leading-6 text-muted">
        A sessão ativa é válida, mas não inclui{" "}
        <span className="font-mono">{perms.join(" ou ")}</span>. Troque de persona no canto superior
        direito para ver esta área.
      </p>
    </div>
  );
}
