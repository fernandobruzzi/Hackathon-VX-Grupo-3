"use client";

import { useEffect, useState } from "react";
import { Button, Code, EmptyState, PageHeader, Table, Td, Th } from "@/components/ui";
import { ApiError } from "@/lib/api";
import type { AuditEvent } from "@/types/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { fmtDate } from "@/lib/format";
import { audit } from "@/mocks/data";
import { AuditIdentity } from "./AuditIdentity";
import { AuditAction, AuditChanges } from "./AuditPresentation";

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
    setRemote([]);
    setCursor(null);
    setNextCursor(null);
  }, [me]);
  useEffect(() => {
    if (!backend || !me) return;
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
  }, [api, backend, cursor, me, retry]);
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
        description="Registros só de inserção: cada alteração guarda a pessoa ou sistema responsável, papel efetivo, antes/depois, justificativa e requisição."
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
            <Th>Requisição</Th>
            {backend && <Th>Alterações</Th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <Td>
                <Code className="text-muted">{fmtDate(a.created_at)}</Code>
              </Td>
              <AuditIdentity event={a} />
              <Td>
                <AuditAction action={a.action} />
              </Td>
              <Td className="text-sm">{a.entity}</Td>
              <Td className="max-w-xs text-sm text-muted">{a.reason ?? "—"}</Td>
              <Td>
                <Code className="text-muted">{a.request_id || "Não registrada"}</Code>
              </Td>
              {backend && (
                <Td>
                  <AuditChanges event={a} />
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
