"use client";

import { Code, PageHeader, Table, Td, Th } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { fmtDate } from "@/lib/format";
import { audit } from "@/mocks/data";

/** Escopo por papel: próprias ações (solicitante), técnico (governança), fiscal e financeiro (auditor). */
export function AuditPage() {
  const { me } = useAuth();
  const rows = audit.filter((a) =>
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
            </tr>
          ))}
        </tbody>
      </Table>
    </>
  );
}
