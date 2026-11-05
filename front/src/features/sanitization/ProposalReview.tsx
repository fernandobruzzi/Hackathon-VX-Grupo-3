"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, X } from "lucide-react";
import { Badge, Button, Card, Code, Eyebrow, Field, Input, Table, Td, Th } from "@/components/ui";
import {
  MaterialStatusBadge,
  ProposalStatusBadge,
  ProposalTypeBadge,
  ReviewBadge,
} from "@/components/ui/status";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { cn, fmtBRL } from "@/lib/format";
import type { Proposal, ReviewStatus } from "@/types/api";

/** Integração: POST /api/v1/sanitization/{id}/decide { expected_version, review_area, decision, primary_material_code, reason }. */
export function ProposalReview({ proposal }: { proposal: Proposal }) {
  const { me } = useAuth();
  const [p, setP] = useState(proposal);
  const [primary, setPrimary] = useState(p.suggested_primary_code);
  const [reason, setReason] = useState("");
  const [auditId, setAuditId] = useState<string | null>(null);

  const isMerge = p.members.length > 1;
  const area: "TECHNICAL" | "FISCAL" | null =
    can(me, "merge:decide", "enrichment:decide") && p.technical_review_status === "PENDING"
      ? "TECHNICAL"
      : can(me, "ncm:decide") && p.fiscal_review_status === "PENDING"
        ? "FISCAL"
        : null;
  const blockedReason =
    p.status !== "PENDING"
      ? "Proposta já decidida."
      : !area && can(me, "merge:decide")
        ? "A parte técnica já foi decidida; falta a revisão fiscal."
        : !area && can(me, "ncm:decide")
          ? p.fiscal_review_status === "NOT_REQUIRED"
            ? "Sem alteração fiscal: a decisão é da Governança PDM."
            : "A revisão fiscal já foi feita."
          : !area
            ? "Seu papel só consulta esta proposta (403 ao decidir)."
            : null;

  const consolidated = useMemo(() => {
    const byCenter = new Map<string, { qty: number; unit: string }>();
    p.members.forEach((m) =>
      m.inventory.forEach((i) => {
        const cur = byCenter.get(i.center_code);
        byCenter.set(i.center_code, { qty: (cur?.qty ?? 0) + Number(i.quantity), unit: i.unit });
      }),
    );
    const total = p.members.every((m) => m.value_brl !== undefined)
      ? p.members.reduce((s, m) => s + Number(m.value_brl), 0)
      : null;
    return { centers: [...byCenter.entries()], total };
  }, [p.members]);

  const decide = (decision: "APPROVE" | "REJECT") => {
    if (!area) return;
    const r: ReviewStatus = decision === "APPROVE" ? "APPROVED" : "REJECTED";
    setP((cur) => {
      const tech = area === "TECHNICAL" ? r : cur.technical_review_status;
      const fisc = area === "FISCAL" ? r : cur.fiscal_review_status;
      const anyRejected = tech === "REJECTED" || fisc === "REJECTED";
      const allDone = [tech, fisc].every((s) => s === "APPROVED" || s === "NOT_REQUIRED");
      return {
        ...cur,
        version: cur.version + 1,
        technical_review_status: tech,
        fiscal_review_status: fisc,
        status: anyRejected ? "REJECTED" : allDone ? "APPLIED" : "PENDING",
      };
    });
    setAuditId(`audit-${Math.random().toString(16).slice(2, 10)}`);
    setReason("");
  };

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/saneamento/"
        className="inline-flex items-center gap-2 self-start text-sm font-semibold text-verde hover:text-verde-glow"
      >
        <ArrowLeft className="size-4" /> Voltar para a fila
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Eyebrow n="02">Revisão de proposta</Eyebrow>
          <h1 className="mt-4 text-[28px] leading-tight font-extrabold">{p.title}</h1>
          <p className="mt-2 text-sm text-muted">
            Identidade por{" "}
            {p.identity.mode === "MANUFACTURER_REFERENCE"
              ? "fabricante + referência"
              : "atributos técnicos"}{" "}
            · {p.identity.summary}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ProposalTypeBadge value={p.proposal_type} />
          <ProposalStatusBadge value={p.status} />
          <Code className="text-muted">v{p.version}</Code>
        </div>
      </header>

      {p.conflicts.length > 0 && (
        <div className="flex gap-3 rounded-md bg-surface p-4 ring-1 ring-surface-2 ring-inset">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-aviso" />
          <ul className="text-sm leading-6">
            {p.conflicts.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Antes */}
      <section>
        <h2 className="mb-3 text-lg font-extrabold">
          Antes · {p.members.length} {p.members.length > 1 ? "códigos ativos" : "código"}
        </h2>
        <Table>
          <thead>
            <tr>
              {isMerge && <Th>Principal</Th>}
              <Th>Código</Th>
              <Th>Descrição atual</Th>
              <Th>Un.</Th>
              <Th>NCM</Th>
              <Th>Estoque</Th>
              <Th className="text-right">Valor</Th>
            </tr>
          </thead>
          <tbody>
            {p.members.map((m) => (
              <tr
                key={m.material_code}
                className={cn(primary === m.material_code && isMerge && "bg-ink/70")}
              >
                {isMerge && (
                  <Td>
                    <input
                      type="radio"
                      name="primary"
                      aria-label={`Manter ${m.material_code} como principal`}
                      checked={primary === m.material_code}
                      onChange={() => setPrimary(m.material_code)}
                      disabled={!area}
                      className="size-4 accent-[var(--verde)]"
                    />
                  </Td>
                )}
                <Td>
                  <Code>{m.material_code}</Code>
                  <div className="mt-1">
                    <MaterialStatusBadge value={m.status} />
                  </div>
                </Td>
                <Td className="font-mono text-[13px]">{m.description}</Td>
                <Td>
                  <Code>{m.unit}</Code>
                </Td>
                <Td>
                  <Code className={m.ncm ? "" : "font-bold text-aviso"}>{m.ncm ?? "sem NCM"}</Code>
                </Td>
                <Td>
                  {m.inventory.length ? (
                    m.inventory.map((i) => (
                      <Code key={i.center_code} className="block">
                        {i.center_code}: {i.quantity} {i.unit}
                      </Code>
                    ))
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </Td>
                <Td className="text-right">
                  <Code>{fmtBRL(m.value_brl ?? null)}</Code>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </section>

      {/* Depois */}
      <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card tone="block" className="flex flex-col gap-3">
          <span className="text-xs font-extrabold tracking-[0.04em] text-esmeralda uppercase">
            Depois · {isMerge ? "um código ativo" : "registro corrigido"}
          </span>
          {primary && <Code className="text-2xl text-esmeralda">{primary}</Code>}
          <p className="font-mono text-[13px] leading-5">{p.after.description}</p>
          <p className="font-mono text-xs text-on-profundo/80">
            NCM {p.after.ncm ?? "—"} · unidade {p.after.unit}
          </p>
          {isMerge && (
            <ul className="mt-1 flex flex-col gap-1 text-sm">
              {p.members
                .filter((m) => m.material_code !== primary)
                .map((m) => (
                  <li key={m.material_code} className="font-mono text-[13px] text-on-profundo/85">
                    {m.material_code} · BLOQUEADO · USAR {primary}
                  </li>
                ))}
            </ul>
          )}
        </Card>
        <Card className="flex flex-col gap-3">
          <span className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
            Estoque consolidado
          </span>
          {consolidated.centers.map(([c, v]) => (
            <div key={c} className="flex justify-between text-sm">
              <span>Centro {c}</span>
              <Code>
                {v.qty} {v.unit}
              </Code>
            </div>
          ))}
          <div className="mt-auto flex justify-between border-t border-surface-2 pt-3 text-sm font-bold">
            <span>Valor total conservado</span>
            <Code>{fmtBRL(consolidated.total)}</Code>
          </div>
          <p className="text-xs text-muted">
            Os saldos originais ficam imutáveis; a visão consolidada só aponta para o principal.
          </p>
        </Card>
      </section>

      {/* Mudanças com fonte */}
      <section>
        <h2 className="mb-3 text-lg font-extrabold">O que muda e de onde veio</h2>
        <Table>
          <thead>
            <tr>
              <Th>Campo</Th>
              <Th>Antes</Th>
              <Th>Depois</Th>
              <Th>Fonte</Th>
            </tr>
          </thead>
          <tbody>
            {p.changes.map((c) => (
              <tr key={c.field}>
                <Td className="font-semibold">{c.field}</Td>
                <Td>
                  <Code className={c.before ? "text-muted" : "font-bold text-aviso"}>
                    {c.before ?? "ausente"}
                  </Code>
                </Td>
                <Td>
                  <Code className="text-verde">{c.after}</Code>
                </Td>
                <Td className="text-xs text-muted">{c.source}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </section>

      {/* Decisão */}
      <section className="z-10 -mx-6 border-t border-surface-2 bg-ink/95 px-6 py-4 backdrop-blur lg:sticky lg:bottom-0 lg:-mx-10 lg:px-10">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex gap-2 text-xs">
            <span className="flex items-center gap-1.5">
              Técnica <ReviewBadge value={p.technical_review_status} />
            </span>
            <span className="flex items-center gap-1.5">
              Fiscal <ReviewBadge value={p.fiscal_review_status} />
            </span>
          </div>
          {area ? (
            <>
              <div className="min-w-72 flex-1">
                <Field
                  label={`Justificativa (${area === "TECHNICAL" ? "revisão técnica" : "revisão fiscal"})`}
                >
                  <Input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder={
                      area === "FISCAL"
                        ? "Ex.: classificação conferida na tabela NCM vigente."
                        : "Ex.: mesma identidade confirmada nas evidências."
                    }
                  />
                </Field>
              </div>
              <Button variant="danger" onClick={() => decide("REJECT")} disabled={!reason.trim()}>
                <X className="size-4" /> Rejeitar
              </Button>
              <Button
                onClick={() => decide("APPROVE")}
                disabled={!reason.trim() || (isMerge && !primary)}
              >
                <Check className="size-4" /> Aprovar
              </Button>
            </>
          ) : (
            <p className="flex-1 text-sm text-muted">{blockedReason}</p>
          )}
        </div>
        {auditId && (
          <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={p.status === "REJECTED" ? "danger" : "success"}>
              {p.status === "APPLIED"
                ? "Aplicada na base"
                : p.status === "REJECTED"
                  ? "Rejeitada"
                  : "Aprovação registrada · aguarda a outra revisão"}
            </Badge>
            <Code className="text-muted">
              evento de auditoria {auditId} · {me?.user.display_name} ({me?.user.roles[0]})
            </Code>
          </p>
        )}
      </section>
    </div>
  );
}
