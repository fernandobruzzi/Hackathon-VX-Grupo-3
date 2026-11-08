"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Button, Card, PageHeader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import {
  formatQuantity,
  quantityOrUnavailable,
  eventLabels,
  closureLabels,
  pendingActions,
  requestDate,
  stages,
  type MaterialRequest,
  type RequestDetail,
  type RequestStatus,
} from "./tracking";

export function RequestTracking({ id }: { id?: string | null }) {
  const { me, backend, sessionBusy, sessionRevision } = useAuth();
  if (!me || sessionBusy) return <p role="status">Carregando sessão…</p>;
  if (!backend)
    return <p>Entre com uma sessão conectada para consultar suas solicitações reais.</p>;
  return <TrackingSession key={`${me.user.id}:${sessionRevision}:${id ?? "list"}`} id={id} />;
}

function TrackingSession({ id }: { id?: string | null }) {
  const { api, me } = useAuth();
  const [status, setStatus] = useState<RequestStatus | "">("");
  const [page, setPage] = useState<{ cursor?: string; append: boolean }>({ append: false });
  const [items, setItems] = useState<MaterialRequest[]>([]);
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    async function load() {
      try {
        if (id !== undefined) {
          if (!id) throw new Error("Escolha uma solicitação na lista para abrir o detalhe.");
          const result = await api.request("get", "/api/v1/material-requests/{id}", {
            params: { id },
            query: { mine: true },
            signal: controller.signal,
          });
          if (!controller.signal.aborted) setDetail(result);
        } else {
          const result = await api.request("get", "/api/v1/material-requests", {
            query: {
              mine: true,
              limit: 20,
              ...(status ? { status } : {}),
              ...(page.cursor ? { cursor: page.cursor } : {}),
            },
            signal: controller.signal,
          });
          if (!controller.signal.aborted) {
            setItems((previous) => [
              ...new Map(
                [...(page.append ? previous : []), ...result.items].map((row) => [row.id, row]),
              ).values(),
            ]);
            setNext(result.next_cursor);
          }
        }
      } catch (err) {
        if (!controller.signal.aborted)
          setError(
            err instanceof ApiError || err instanceof Error
              ? err.message
              : "Não foi possível consultar suas solicitações.",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [api, id, page, retry, status]);

  const center = (code: string) =>
    me?.scope.center_names?.[code] ? `${me.scope.center_names[code]} (${code})` : code;
  return (
    <div className="space-y-6">
      <PageHeader
        n="01"
        eyebrow="Acompanhamento"
        title={id !== undefined ? "Detalhe da solicitação" : "Minhas solicitações"}
        description="Acompanhe suas necessidades de material pelo protocolo."
      />
      {id !== undefined ? (
        <Link href="/solicitacoes/" className="font-bold text-verde underline">
          Voltar às minhas solicitações
        </Link>
      ) : (
        <label className="block max-w-sm space-y-2 font-bold">
          Etapa
          <select
            className="block min-h-11 w-full rounded border border-surface-2 bg-surface px-3 text-text"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as RequestStatus | "");
              setPage({ append: false });
              setItems([]);
              setNext(null);
            }}
          >
            <option value="">Todas as etapas</option>
            {Object.entries(stages).map(([value, stage]) => (
              <option key={value} value={value}>
                {stage.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {loading && <p role="status">Carregando solicitações…</p>}
      {error && (
        <div role="alert" className="space-y-3">
          <p>{error}</p>
          <Button variant="ghost" onClick={() => setRetry((value) => value + 1)}>
            Tentar novamente
          </Button>
        </div>
      )}
      {id !== undefined ? (
        detail && (
          <>
            <Card className="space-y-4 break-words">
              <h2 className="font-mono text-xl font-bold">{detail.protocol}</h2>
              <Badge>{stages[detail.status].label}</Badge>
              <p className="whitespace-pre-wrap">{detail.original_text}</p>
              <p>Centro: {center(detail.center_code)}</p>
              <p>Equipe da etapa: {stages[detail.status].team}</p>
              <p>Pendências: {pendingActions(detail)}</p>
              {detail.closure_reason && (
                <p>
                  Motivo do encerramento:{" "}
                  {closureLabels[detail.closure_reason] ?? "Consulte o motivo no histórico"}
                </p>
              )}
              <p className="text-sm text-muted">Atualizada em {requestDate(detail.updated_at)}</p>
            </Card>
            <section aria-label="Quantidades" className="space-y-3">
              <h2 className="text-lg font-bold">Quantidades · {detail.unit}</h2>
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Solicitada", formatQuantity(detail.quantity)],
                  ["Reservada", quantityOrUnavailable(detail.reserved_quantity)],
                  ["Entregue", quantityOrUnavailable(detail.delivered_quantity)],
                  ["Encaminhada para compras", quantityOrUnavailable(detail.forwarded_quantity)],
                  ["Pendente", quantityOrUnavailable(detail.pending_quantity)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-surface p-4">
                    <dt className="text-sm text-muted">{label}</dt>
                    <dd className="mt-2 text-xl font-bold break-words">{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-sm text-muted">
                Encaminhar para Compras registra a demanda; não confirma compra, recebimento nem
                entrega. Uma quantidade não informada não significa saldo zero.
              </p>
            </section>
            {!!detail.reservations?.length && (
              <section className="space-y-3" aria-label="Reservas">
                <h2 className="text-lg font-bold">Parcelas do estoque</h2>
                <ul className="space-y-3">
                  {detail.reservations.map((reservation) => (
                    <li key={reservation.id} className="rounded-lg bg-surface p-4">
                      <p className="font-bold">
                        Reserva{" "}
                        {reservation.status === "ATIVA"
                          ? "ativa"
                          : reservation.status === "CONSUMIDA"
                            ? "consumida"
                            : "cancelada"}
                      </p>
                      <p>
                        Reservada originalmente: {formatQuantity(reservation.quantity)}{" "}
                        {reservation.unit}
                      </p>
                      <p>
                        Ainda reservada: {formatQuantity(reservation.open_quantity)}{" "}
                        {reservation.unit}
                      </p>
                      <p>
                        Entregue: {formatQuantity(reservation.delivered_quantity)}{" "}
                        {reservation.unit}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {!!detail.purchase_forwards?.length && (
              <section className="space-y-3" aria-label="Encaminhamentos para compras">
                <h2 className="text-lg font-bold">Parcelas de compras</h2>
                <ul className="space-y-3">
                  {detail.purchase_forwards.map((forward) => (
                    <li key={forward.id} className="rounded-lg bg-surface p-4 break-words">
                      <p className="font-bold">
                        {forward.status === "ENCAMINHADO"
                          ? "Encaminhada para Compras"
                          : forward.status === "ACEITO"
                            ? "Demanda aceita por Compras"
                            : forward.status === "DEVOLVIDO"
                              ? "Devolvida por Compras"
                              : "Encaminhamento cancelado"}
                      </p>
                      <p>
                        Material {forward.material_code}: {formatQuantity(forward.quantity)}{" "}
                        {forward.unit}
                      </p>
                      {forward.reason && <p>{forward.reason}</p>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <section className="space-y-3" aria-label="Histórico">
              <h2 className="text-lg font-bold">Histórico da solicitação</h2>
              <ol className="space-y-3">
                {detail.history.map((event) => (
                  <li key={event.id} className="rounded-lg border border-surface-2 p-4">
                    <p className="font-bold">
                      {eventLabels[event.action] ??
                        (event.before_status ? "Solicitação atualizada" : "Solicitação criada")}
                    </p>
                    <p>
                      {event.before_status && event.before_status !== event.after_status
                        ? `${stages[event.before_status].label} → `
                        : ""}
                      {stages[event.after_status].label}
                    </p>
                    <time dateTime={event.created_at} className="text-sm text-muted">
                      {requestDate(event.created_at)}
                    </time>
                    {event.reason && (
                      <p className="mt-2 break-words whitespace-pre-wrap">{event.reason}</p>
                    )}
                  </li>
                ))}
              </ol>
              {!detail.history.length && <p>Sem transições disponíveis.</p>}
            </section>
          </>
        )
      ) : (
        <>
          {!loading && !error && !items.length && (
            <p>Nenhuma solicitação encontrada nesta etapa.</p>
          )}
          <ul className="grid gap-4 md:grid-cols-2">
            {items.map((row) => (
              <li key={row.id} className="min-w-0">
                <Card className="h-full space-y-3 break-words">
                  <Link
                    href={`/solicitacoes/detalhe/?id=${encodeURIComponent(row.id)}`}
                    className="font-mono text-lg font-bold text-verde underline"
                  >
                    {row.protocol}
                  </Link>
                  <p>
                    <Badge>{stages[row.status].label}</Badge>
                  </p>
                  <p className="line-clamp-3 whitespace-pre-wrap">{row.original_text}</p>
                  <p>
                    {formatQuantity(row.quantity)} {row.unit} · {center(row.center_code)}
                  </p>
                  <p className="text-sm text-muted">Atualizada em {requestDate(row.updated_at)}</p>
                </Card>
              </li>
            ))}
          </ul>
          {next && !error && (
            <Button
              variant="ghost"
              disabled={loading}
              onClick={() => setPage({ cursor: next, append: true })}
            >
              Carregar mais solicitações
            </Button>
          )}
        </>
      )}
    </div>
  );
}
