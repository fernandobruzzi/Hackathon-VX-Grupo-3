"use client";

import { useState } from "react";
import { ChevronRight, Wrench } from "lucide-react";
import { Badge, Code } from "@/components/ui";
import { cn } from "@/lib/format";
import type { ToolCall } from "@/types/api";

/**
 * Painel de chamadas MCP do turno. Mostra nome, parâmetros permitidos, duração e resultado resumido.
 * Nunca mostra raciocínio interno do modelo (Arquitetura, seção 3).
 */
export function ToolCallsPanel({ calls }: { calls: { turn: number; call: ToolCall }[] }) {
  if (!calls.length)
    return <p className="rounded-md bg-surface p-4 text-sm text-muted">Nenhuma ferramenta chamada ainda. Cada chamada do agente ao servidor MCP aparece aqui.</p>;
  return (
    <ol className="flex flex-col gap-2">
      {calls.map(({ turn, call }) => <ToolRow key={call.id} turn={turn} call={call} />)}
    </ol>
  );
}

function ToolRow({ turn, call }: { turn: number; call: ToolCall }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-md bg-surface">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <Wrench className="size-4 shrink-0 text-verde" />
        <span className="flex-1">
          <Code className="block">{call.name}</Code>
          <span className="font-mono text-[11px] text-muted">turno {turn} · {call.transport} · {call.duration_ms} ms</span>
        </span>
        <Badge tone={call.status === "SUCCEEDED" ? "success" : call.status === "FAILED" ? "danger" : "warning"}>{call.status === "SUCCEEDED" ? "ok" : call.status.toLowerCase()}</Badge>
        <ChevronRight className={cn("size-4 text-muted transition", open && "rotate-90")} />
      </button>
      {open && (
        <div className="grid gap-2 border-t border-surface-2 px-4 py-3">
          <Json label="input" value={call.input} />
          <Json label="result" value={call.result} />
        </div>
      )}
    </li>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.06em] text-muted">{label}</p>
      <pre className="max-h-48 overflow-auto rounded-sm bg-ink p-3 font-mono text-[12px] leading-5">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
