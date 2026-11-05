"use client";

import { useEffect, useState } from "react";
import { Button, Code, EmptyState, PageHeader, Table, Td, Th } from "@/components/ui";
import { ApiError } from "@/lib/api";
import type { AuditEvent } from "@/types/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { fmtDate } from "@/lib/format";
import { audit } from "@/mocks/data";

/** Escopo por papel: próprias ações (solicitante), técnico (governança), fiscal e financeiro (auditor). */
export function AuditPage() {
  const { me, backend, api } = useAuth();
  const [remote, setRemote] = useState<AuditEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(backend);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .request("get", "/api/v1/audit", {
        query: { cursor: cursor ?? undefined },
        signal: controller.signal,
      })
      .then((result) => {
        if (!controller.signal.aborted) {
          setRemote((previous) => (cursor ? [...previous, ...result.items] : result.items));
          setNextCursor(result.next_cursor);
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(
            error instanceof ApiError ? error.message : "Não foi possível carregar a auditoria.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, cursor, retry]);
  const rows = backend
    ? remote
    : audit.filter((a) =>
        can(me, "audit:technical")
          ? a.effective_role !== "ROLE_AUDITOR_FISCAL"
          : can(me, "audit:fiscal")
            ? a.action.startsWith("NCM") || a.action.startsWith("MERGE")
            : a.effective_role === "ROLE_SOLICITANTE",
      );
  return (
    <>
      <PageHeader
        n="05"
        eyebrow="Auditoria"
        title="Quem mudou o quê, quando e por quê"
        description="Registros só de inserção: cada alteração guarda usuário real, papel efetivo, antes/depois, justificativa e request_id."
      />
      {loading && (
        <p role="status" className="mb-4 text-sm text-muted">
          Carregando auditoria…
        </p>
      )}
      {error && (
        <div role="alert" className="mb-4 text-alerta">
          {error} <Button onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
        </div>
      )}
      {!loading && !error && rows.length === 0 && (
        <EmptyState title="Nenhum evento">Não há eventos de auditoria no seu escopo.</EmptyState>
      )}
      <Table>
        <thead>
          <tr>
            <Th>Quando</Th>
            <Th>Quem</Th>
            <Th>Papel efetivo</Th>
            <Th>Ação</Th>
            <Th>Recurso</Th>
            <Th>Justificativa</Th>
            <Th>request_id</Th>
            {backend && <Th>Alterações</Th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <Td>
                <Code className="text-muted">{fmtDate(a.created_at)}</Code>
              </Td>
              <Td className="font-semibold">{a.actor}</Td>
              <Td>
                <Code>{a.effective_role}</Code>
              </Td>
              <Td>
                <Code className="text-verde">{a.action}</Code>
              </Td>
              <Td className="text-sm">{a.entity}</Td>
              <Td className="max-w-xs text-sm text-muted">{a.reason ?? "—"}</Td>
              <Td>
                <Code className="text-muted">{a.request_id}</Code>
              </Td>
              {backend && (
                <Td>
                  <details>
                    <summary className="cursor-pointer text-verde">Antes e depois</summary>
                    <pre className="mt-2 max-w-lg overflow-auto text-xs">
                      {JSON.stringify({ before: a.before, after: a.after }, null, 2)}
                    </pre>
                  </details>
                </Td>
              )}
            </tr>
          ))}
        </tbody>
      </Table>
      {backend && nextCursor && (
        <Button disabled={loading} onClick={() => setCursor(nextCursor)}>
          Carregar mais eventos
        </Button>
      )}
    </>
  );
}
