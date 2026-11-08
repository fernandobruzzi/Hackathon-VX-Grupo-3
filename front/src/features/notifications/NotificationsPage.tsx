"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Card, PageHeader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import type { components } from "@/types/api.generated";
import { requestDate } from "@/features/requests/tracking";
import { NOTIFICATIONS_CHANGED } from "./unread";

type NotificationList = components["schemas"]["NotificationList"];

export function NotificationsPage() {
  const { api, me, backend, sessionBusy } = useAuth();
  const [data, setData] = useState<NotificationList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    api
      .request("get", "/api/v1/notifications", { query: { limit: 50 }, signal: controller.signal })
      .then((result) => !controller.signal.aborted && setData(result))
      .catch(
        (err) =>
          !controller.signal.aborted &&
          setError(err instanceof ApiError ? err.message : "Não foi possível carregar."),
      );
    return () => controller.abort();
  }, [api, backend, retry]);

  if (!me || sessionBusy) return <p role="status">Carregando sessão…</p>;
  if (!backend) return <p>Entre com uma sessão conectada para ver suas notificações reais.</p>;

  async function mark(body: { ids?: string[]; all: boolean }) {
    setBusy(true);
    setError(null);
    try {
      setData(await api.request("post", "/api/v1/notifications/read", { body }));
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível marcar como lida.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        n="01"
        eyebrow="Acompanhamento"
        title="Notificações"
        description="Mudanças de etapa nas suas solicitações feitas pelas equipes de estoque, compras e cadastro."
      />
      {error && (
        <div role="alert" className="space-y-3">
          <p>{error}</p>
          <Button variant="ghost" onClick={() => setRetry((value) => value + 1)}>
            Tentar novamente
          </Button>
        </div>
      )}
      {!data && !error && <p role="status">Carregando notificações…</p>}
      {data && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <p>{data.unread_count} não lida(s)</p>
            {data.unread_count > 0 && (
              <Button variant="ghost" disabled={busy} onClick={() => void mark({ all: true })}>
                Marcar todas como lidas
              </Button>
            )}
          </div>
          {!data.items.length && <p>Nenhuma notificação por enquanto.</p>}
          <ul className="space-y-3">
            {data.items.map((item) => (
              <li key={item.id}>
                <Card className="space-y-2 break-words">
                  <p className="font-bold">
                    {item.read ? "" : "● "}
                    {item.title}
                  </p>
                  {item.request_id && (
                    <Link
                      href={`/solicitacoes/detalhe/?id=${encodeURIComponent(item.request_id)}`}
                      className="font-mono text-verde underline"
                    >
                      {item.protocol ?? "Abrir solicitação"}
                    </Link>
                  )}
                  {item.reason && <p className="whitespace-pre-wrap">{item.reason}</p>}
                  <time dateTime={item.created_at} className="block text-sm text-muted">
                    {requestDate(item.created_at)}
                  </time>
                  {!item.read && (
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void mark({ ids: [item.id], all: false })}
                    >
                      Marcar como lida
                    </Button>
                  )}
                </Card>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
