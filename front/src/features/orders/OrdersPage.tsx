"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { Button, Code, PageHeader, Table, Tabs, Td, Th } from "@/components/ui";
import { OrderStatusBadge } from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { fmtDate } from "@/lib/format";
import type { RegistrationOrder } from "@/types/api";
import { orders as sample } from "@/mocks/data";

type Tab = "mine" | "review" | "all";

/**
 * Pedidos de cadastro. O Solicitante vê os próprios. A Governança aprova a parte técnica dos
 * pedidos prontos e o Fiscal publica os que aguardam NCM; a API confere papel e duplicidade.
 */
export function OrdersPage() {
  const { me, backend, api } = useAuth();
  const governance = can(me, "orders:decide");
  const fiscal = can(me, "ncm:decide");
  const reviewer = governance || fiscal;
  const awaiting = governance ? "READY_FOR_REVIEW" : "PENDING_FISCAL";
  const [tab, setTab] = useState<Tab>(reviewer ? "review" : "mine");
  const [remote, setRemote] = useState<RegistrationOrder[] | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!reviewer) setTab("mine");
  }, [reviewer]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  const loadPage = useCallback(
    async (cursor: string | null, append: boolean, signal: AbortSignal) => {
      if (!backend || !me) return;
      setLoading(true);
      setError(null);
      try {
        const result = await api.request("get", "/api/v1/registration-orders", {
          query: {
            limit: 100,
            mine: tab === "mine",
            ...(tab === "review" ? { status: awaiting } : {}),
            ...(cursor !== null ? { cursor } : {}),
          },
          signal,
        });
        if (signal.aborted) return;
        setRemote((previous) => (append ? [...(previous ?? []), ...result.items] : result.items));
        setNextCursor(result.next_cursor);
      } catch (err: unknown) {
        if (!signal.aborted)
          setError(err instanceof ApiError ? err.message : "Não foi possível carregar os pedidos.");
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [api, awaiting, backend, me, tab],
  );

  useEffect(() => {
    const request = new AbortController();
    controller.current = request;
    setRemote(null);
    setNextCursor(null);
    void loadPage(null, false, request.signal);
    return () => request.abort();
  }, [loadPage, retry]);

  const all = backend ? (remote ?? []) : sample;
  const rows = backend
    ? all
    : tab === "mine"
      ? all.filter((o) => o.origin === "CHAT")
      : tab === "review"
        ? all.filter((o) => o.status === awaiting)
        : all;

  const decide = (order: RegistrationOrder, decision: "APPROVE" | "REJECT") => {
    const reason =
      decision === "REJECT"
        ? "Rejeitado na tela de pedidos."
        : governance
          ? "Parte técnica aprovada na tela de pedidos: classe e atributos do PDM conferidos."
          : "NCM aprovado e cadastro publicado na tela de pedidos.";
    setBusy(order.id);
    setError(null);
    api
      .request("post", "/api/v1/registration-orders/{id}/decide", {
        params: { id: order.id },
        body: { expected_version: order.version, decision, reason },
      })
      .then(() => setRetry((value) => value + 1))
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Não foi possível registrar a decisão."),
      )
      .finally(() => setBusy(null));
  };

  const tabs = [
    ...(reviewer
      ? [
          {
            value: "review" as const,
            label: governance ? "Para aprovar" : "Aguardando NCM",
            // Com mais páginas, a contagem seria só da primeira: fica sem número.
            count: tab === "review" && !nextCursor && !loading ? all.length : undefined,
          },
          { value: "all" as const, label: "Todos" },
        ]
      : []),
    { value: "mine" as const, label: "Meus pedidos" },
  ];

  return (
    <>
      <PageHeader
        n="01"
        eyebrow="Pedidos de cadastro"
        title={
          tab === "mine"
            ? "Seus pedidos"
            : governance
              ? "Pedidos para aprovar"
              : "Pedidos para publicar"
        }
        description="Todo pedido passa pela checagem de duplicidade antes de virar cadastro e de novo antes de cada aprovação. Pedidos incompletos voltam com os campos que faltam."
        actions={
          <Link href="/chat/">
            <Button>
              <Plus className="size-4" /> Novo pedido
            </Button>
          </Link>
        }
      />
      {!backend && (
        <p role="status" className="mb-4 text-sm text-aviso">
          Demonstração simulada: estes pedidos são exemplos.
        </p>
      )}
      {reviewer && (
        <div className="mb-4">
          <Tabs value={tab} onChange={setTab} items={tabs} />
        </div>
      )}
      {error && (
        <div role="alert" className="mb-4 text-alerta">
          {error}{" "}
          <Button size="sm" onClick={() => setRetry((value) => value + 1)}>
            Tentar novamente
          </Button>
        </div>
      )}
      <Table>
        <thead>
          <tr>
            <Th>Pedido</Th>
            <Th>Texto original</Th>
            <Th>Centro</Th>
            <Th>Classe</Th>
            <Th>Status</Th>
            <Th>Resultado</Th>
            <Th>Atualizado</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id} className="hover:bg-ink/60">
              <Td>
                <Code>{o.id.slice(0, 8)}</Code>
                <p className="mt-1 text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">
                  {o.origin === "IMPORT" ? "importado" : "chat"}
                </p>
              </Td>
              <Td className="max-w-md text-sm">{o.original_text}</Td>
              <Td>
                <Code>{o.center_code || "—"}</Code>
              </Td>
              <Td>
                <Code className="text-muted">{o.pdm_class_id ?? "—"}</Code>
              </Td>
              <Td>
                <OrderStatusBadge value={o.status} />
              </Td>
              <Td className="text-sm">
                {o.missing_attributes.length > 0 && (
                  <span className="font-semibold text-aviso">
                    Falta: {o.missing_attributes.join(", ")}
                  </span>
                )}
                {o.material_code && (
                  <span>
                    {o.status === "REGISTERED" ? "Cadastrado como " : "Use "}
                    <Code className="text-verde">{o.material_code}</Code>
                  </span>
                )}
                {backend && o.status === awaiting && reviewer && (
                  <span className="mt-1 flex flex-wrap gap-2">
                    <Button size="sm" disabled={busy === o.id} onClick={() => decide(o, "APPROVE")}>
                      {governance ? "Aprovar parte técnica" : "Publicar cadastro"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy === o.id}
                      onClick={() => decide(o, "REJECT")}
                    >
                      Rejeitar
                    </Button>
                  </span>
                )}
              </Td>
              <Td>
                <Code className="text-muted">{fmtDate(o.updated_at)}</Code>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {backend && loading && (
        <p role="status" className="mt-4 text-sm text-muted">
          Carregando pedidos…
        </p>
      )}
      {backend && nextCursor !== null && (
        <Button
          className="mt-4"
          disabled={loading}
          onClick={() => {
            if (controller.current) void loadPage(nextCursor, true, controller.current.signal);
          }}
        >
          Carregar mais pedidos
        </Button>
      )}
      {backend && !loading && remote && rows.length === 0 && (
        <p className="mt-4 text-sm text-muted">Nenhum pedido nesta lista.</p>
      )}
    </>
  );
}
