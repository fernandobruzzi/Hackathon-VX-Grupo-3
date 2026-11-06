"use client";

import { useEffect, useState } from "react";
import { Button, Select } from "@/components/ui";
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
    <div className="flex flex-wrap items-center gap-2 border-b border-surface-2 px-6 py-3">
      <label htmlFor="chat-history" className="text-xs font-semibold text-muted">
        Retomar conversa
      </label>
      <Select
        id="chat-history"
        aria-label="Conversas salvas"
        value={selected}
        onChange={(event) => onSelect(event.target.value)}
        className="max-w-full flex-1 text-sm"
      >
        <option value="">Nova conversa</option>
        {selected && !items.some((item) => item.id === selected) && (
          <option value={selected}>Conversa atual</option>
        )}
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.title} · {new Date(item.updated_at).toLocaleString("pt-BR")}
          </option>
        ))}
      </Select>
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
      {error && (
        <p role="alert" className="w-full text-sm text-alerta">
          Não foi possível carregar o histórico. Atualize para tentar novamente.
        </p>
      )}
    </div>
  );
}
