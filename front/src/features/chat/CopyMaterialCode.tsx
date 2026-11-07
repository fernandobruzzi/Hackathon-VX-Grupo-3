"use client";

import { useState } from "react";
import { Copy } from "lucide-react";
import { Button } from "@/components/ui";

export function CopyMaterialCode({ code }: { code: string }) {
  const [state, setState] = useState<"idle" | "copying" | "copied" | "failed">("idle");

  const copy = async () => {
    setState("copying");
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
        throw new Error("Área de transferência indisponível");
      }
      await navigator.clipboard.writeText(code);
      setState("copied");
    } catch {
      setState("failed");
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="primary"
        size="sm"
        className="self-start"
        onClick={copy}
        disabled={state === "copying"}
        aria-busy={state === "copying"}
      >
        <Copy className="size-4" /> Copiar código
      </Button>
      <p role="status" aria-live="polite" className="text-sm text-on-profundo">
        {state === "copied"
          ? "Código copiado."
          : state === "failed"
            ? "Não foi possível copiar. Selecione o código acima e copie manualmente."
            : state === "copying"
              ? "Copiando código…"
              : ""}
      </p>
    </div>
  );
}
