"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button, Code, PageHeader, Select, Table, Tabs, Td, Th, EmptyState } from "@/components/ui";
import { ApiError } from "@/lib/api";
import type { components } from "@/types/api.generated";
import {
  ProposalStatusBadge,
  ProposalTypeBadge,
  ReviewBadge,
  proposalTypeLabel,
} from "@/components/ui/status";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { fmtDate } from "@/lib/format";
import { needsFiscal, needsTechnical, proposals } from "@/mocks/queue";
import type { ProposalType } from "@/types/api";

type Area = "TECHNICAL" | "FISCAL" | "HISTORY";

/** Integração: GET /api/v1/sanitization/queue?review_area=…&status=PENDING&limit=20 (contrato 6.3). */
export function QueuePage() {
  const { me, backend, api } = useAuth();
  const isFiscal = can(me, "ncm:decide");
  const [area, setArea] = useState<Area>(isFiscal ? "FISCAL" : "TECHNICAL");
  const [type, setType] = useState<ProposalType | "ALL">("ALL");
  const [remote, setRemote] = useState<components["schemas"]["ProposalSummary"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(backend);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    setLoading(true);
    if (!cursor) setRemote([]);
    setError(null);
    api
      .request("get", "/api/v1/sanitization/queue", {
        query: {
          review_area: area === "HISTORY" ? undefined : area,
          status: area === "HISTORY" ? "DECIDED" : "PENDING",
          proposal_type: type === "ALL" ? undefined : type,
          cursor: cursor ?? undefined,
        },
        signal: controller.signal,
      })
      .then((result) => {
        if (controller.signal.aborted) return;
        setRemote((previous) => (cursor ? [...previous, ...result.items] : result.items));
        setNextCursor(result.next_cursor);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(error instanceof ApiError ? error.message : "Não foi possível carregar a fila.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, area, type, cursor, retry]);

  const rows = useMemo(() => {
    if (backend) return remote;
    const base =
      area === "TECHNICAL"
        ? proposals.filter(needsTechnical)
        : area === "FISCAL"
          ? proposals.filter(needsFiscal)
          : proposals.filter((p) => p.status !== "PENDING");
    return type === "ALL" ? base : base.filter((p) => p.proposal_type === type);
  }, [area, type, backend, remote]);

  return (
    <>
      <PageHeader
        n="02"
        eyebrow="Saneamento"
        title={
          isFiscal
            ? "Propostas que dependem da revisão fiscal"
            : "Propostas do lote aguardando revisão técnica"
        }
        description="O lote propõe; ninguém altera a base mestre sem aprovação. Unificações e enriquecimento passam pela Governança PDM; qualquer mudança de NCM passa pelo Fiscal."
      />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={area}
          onChange={(value) => {
            setArea(value);
            setCursor(null);
          }}
          items={[
            {
              value: "TECHNICAL",
              label: "Técnica",
              count: backend ? undefined : proposals.filter(needsTechnical).length,
            },
            {
              value: "FISCAL",
              label: "Fiscal",
              count: backend ? undefined : proposals.filter(needsFiscal).length,
            },
            { value: "HISTORY", label: "Decididas" },
          ]}
        />
        <Select
          value={type}
          onChange={(e) => {
            setType(e.target.value as ProposalType | "ALL");
            setCursor(null);
          }}
          className="h-10 w-56 text-sm"
          aria-label="Tipo de proposta"
        >
          <option value="ALL">Todos os tipos</option>
          {Object.entries(proposalTypeLabel).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
      </div>

      {loading && (
        <p role="status" className="mb-4 text-sm text-muted">
          Carregando propostas…
        </p>
      )}
      {error && (
        <div role="alert" className="mb-4 text-alerta">
          {error}{" "}
          <Button variant="ghost" onClick={() => setRetry((value) => value + 1)}>
            Tentar novamente
          </Button>
        </div>
      )}
      {!loading && !error && rows.length === 0 ? (
        <EmptyState title="Fila vazia">Nada pendente nesta área com esse filtro.</EmptyState>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Proposta</Th>
              <Th>Tipo</Th>
              <Th>Códigos</Th>
              <Th>Técnica</Th>
              <Th>Fiscal</Th>
              <Th>Status</Th>
              <Th className="text-right">Score</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="hover:bg-ink/60">
                <Td>
                  <Link
                    href={
                      backend
                        ? `/saneamento/revisao/?id=${encodeURIComponent(p.id)}`
                        : `/saneamento/${p.id}/`
                    }
                    className="font-semibold hover:text-verde"
                  >
                    {p.title ?? p.material_codes.join(" / ")}
                  </Link>
                  <p className="mt-0.5 text-xs text-muted">{p.identity.summary}</p>
                  {p.conflicts.length > 0 && (
                    <p className="mt-1 text-xs font-semibold text-aviso">
                      {p.conflicts.length} conflito(s)
                    </p>
                  )}
                </Td>
                <Td>
                  <ProposalTypeBadge value={p.proposal_type} />
                </Td>
                <Td>
                  <Code>{p.material_codes.join(" · ")}</Code>
                </Td>
                <Td>
                  <ReviewBadge value={p.technical_review_status} />
                </Td>
                <Td>
                  <ReviewBadge value={p.fiscal_review_status} />
                </Td>
                <Td>
                  <ProposalStatusBadge value={p.status} />
                  {p.created_at && (
                    <p className="mt-1 font-mono text-[11px] text-muted">{fmtDate(p.created_at)}</p>
                  )}
                </Td>
                <Td className="text-right">
                  <Code>{p.ranking_score?.toFixed(2) ?? "—"}</Code>
                </Td>
                <Td>
                  <Link
                    href={
                      backend
                        ? `/saneamento/revisao/?id=${encodeURIComponent(p.id)}`
                        : `/saneamento/${p.id}/`
                    }
                    aria-label={`Revisar ${p.title}`}
                    className="grid size-9 place-items-center rounded-md hover:bg-ink"
                  >
                    <ArrowRight className="size-4" />
                  </Link>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {backend && nextCursor && (
        <Button disabled={loading} onClick={() => setCursor(nextCursor)}>
          Carregar mais propostas
        </Button>
      )}
      <p className="mt-3 text-xs text-muted">
        O score só ordena a fila. Ele não é probabilidade de equivalência e não aprova nada sozinho.
      </p>
    </>
  );
}
