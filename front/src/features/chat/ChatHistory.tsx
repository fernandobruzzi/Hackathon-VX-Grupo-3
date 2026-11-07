"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import type { components } from "@/types/api.generated";

type Summary = components["schemas"]["ChatSessionSummary"];

export function ChatHistory({
  selected,
  onSelect,
  revision,
}: {
  selected: string;
  onSelect: (id: string) => void;
  revision: number;
}) {
  const { api } = useAuth();
  const [items, setItems] = useState<Summary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [page, setPage] = useState<string | undefined>();
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setPage(undefined);
  }, [revision]);
  useEffect(() => {
    const request = new AbortController();
    setLoading(true);
    setError(false);
    api
      .request("get", "/api/v1/chat/sessions", {
        query: { limit: 20, cursor: page },
        signal: request.signal,
      })
      .then((res) => {
        if (request.signal.aborted) return;
        setItems((previous) =>
          page
            ? [
                ...previous.filter((item) => !res.items.some((next) => next.id === item.id)),
                ...res.items,
              ]
            : res.items,
        );
        setCursor(res.next_cursor);
      })
      .catch(() => {
        if (!request.signal.aborted) setError(true);
      })
      .finally(() => {
        if (!request.signal.aborted) setLoading(false);
      });
    return () => request.abort();
  }, [api, page, revision, retry]);
  return (
    <details className="min-w-0 shrink-0 border-b border-surface-2 px-6 py-3">
      <summary className="cursor-pointer text-sm font-semibold">Histórico de conversas</summary>
      <p className="mt-3 text-xs text-muted">
        Selecione uma conversa para retomar. Mais recentes primeiro.
      </p>
      {selected && !items.some((item) => item.id === selected) && (
        <p className="mt-2 text-xs text-verde">Conversa atual ainda não exibida nesta lista.</p>
      )}
      <ol
        aria-label="Conversas salvas"
        aria-busy={loading}
        className="my-3 max-h-48 space-y-2 overflow-y-auto p-1"
      >
        {[...items]
          .sort(
            (a, b) =>
              Date.parse(b.updated_at) - Date.parse(a.updated_at) || b.id.localeCompare(a.id),
          )
          .map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-label={`Retomar conversa: ${item.title}`}
                aria-current={item.id === selected ? "true" : undefined}
                title={item.title}
                onClick={() => onSelect(item.id)}
                className={cn(
                  "w-full rounded-md px-3 py-3 text-left text-sm ring-1 transition-colors ring-inset",
                  item.id === selected
                    ? "bg-surface ring-verde"
                    : "bg-ink ring-surface-2 hover:ring-verde",
                )}
              >
                <span className="block font-semibold [overflow-wrap:anywhere] whitespace-normal">
                  {item.title}
                </span>
                <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  <time dateTime={item.updated_at}>
                    {new Date(item.updated_at).toLocaleDateString("pt-BR")} ·{" "}
                    {new Date(item.updated_at).toLocaleTimeString("pt-BR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                  {item.id === selected && (
                    <span className="font-semibold text-verde">Conversa atual</span>
                  )}
                </span>
              </button>
            </li>
          ))}
      </ol>
      {!loading && !error && items.length === 0 && (
        <p className="mb-3 text-sm text-muted">Nenhuma conversa salva.</p>
      )}
      {loading && (
        <p role="status" className="mb-3 text-sm text-muted">
          Carregando histórico…
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {cursor && (
          <Button size="sm" variant="ghost" disabled={loading} onClick={() => setPage(cursor)}>
            Mais conversas
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          disabled={loading}
          onClick={() => {
            setPage(undefined);
            setRetry((value) => value + 1);
          }}
        >
          Atualizar histórico
        </Button>
      </div>
      {error && (
        <p role="alert" className="w-full text-sm text-alerta">
          Não foi possível carregar o histórico. Atualize para tentar novamente.
        </p>
      )}
    </details>
  );
}
