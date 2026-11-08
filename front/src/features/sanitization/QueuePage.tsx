"use client";
import { AutomaticDecision } from "./AutomaticDecision";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import {
  Button,
  Code,
  PageHeader,
  Select,
  Table,
  Tabs,
  TabPanels,
  Td,
  Th,
  EmptyState,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import type { components } from "@/types/api.generated";
import {
  ProposalOriginBadge,
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

import { mergeQueueItems, useQueueNavigation, type Area } from "./QueueNavigation";

/** Integração: GET /api/v1/sanitization/queue?review_area=…&status=PENDING&limit=20 (contrato 6.3). */
export function QueuePage() {
  const { me, backend, api } = useAuth();
  const isFiscal = can(me, "ncm:decide");
  const navigation = useQueueNavigation();
  const [area, setArea] = useState<Area>(
    navigation.current?.area ?? (isFiscal ? "FISCAL" : "TECHNICAL"),
  );
  const [type, setType] = useState<ProposalType | "ALL">(navigation.current?.type ?? "ALL");
  const [remote, setRemote] = useState<components["schemas"]["ProposalSummary"][]>(
    navigation.current?.items ?? [],
  );
  const [cursor, setCursor] = useState<string | null>(navigation.current?.cursor ?? null);
  const [nextCursor, setNextCursor] = useState<string | null>(
    navigation.current?.nextCursor ?? null,
  );
  const [loading, setLoading] = useState(backend);
  const [pageCount, setPageCount] = useState(navigation.current?.pageCount ?? 0);
  const [hasLoaded, setHasLoaded] = useState(!backend || !!navigation.current?.loaded);
  const [restoring, setRestoring] = useState(!!navigation.current?.loaded);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    setLoading(true);
    if (!cursor && !restoring) setRemote([]);
    setError(null);
    const readPage = (pageCursor?: string) =>
      api.request("get", "/api/v1/sanitization/queue", {
        query: {
          review_area: area === "HISTORY" ? undefined : area,
          status: area === "HISTORY" ? "DECIDED" : "PENDING",
          proposal_type: type === "ALL" ? undefined : type,
          cursor: pageCursor,
        },
        signal: controller.signal,
      });
    const load = async () => {
      if (restoring) {
        // Repete só as páginas já carregadas e publica o resultado completo de uma vez.
        // O cursor novo permite continuar mesmo quando surgiram propostas após a antiga última página.
        let pageCursor: string | undefined;
        let remaining: string | null = null;
        let pages = 0;
        let items: typeof remote = [];
        do {
          const page = await readPage(pageCursor);
          if (controller.signal.aborted) return;
          items = mergeQueueItems(items, page.items);
          remaining = page.next_cursor;
          pageCursor = remaining ?? undefined;
          pages += 1;
        } while (remaining && pages < (navigation.current?.pageCount ?? 1));
        setRemote(items);
        setNextCursor(remaining);
        setPageCount(pages);
        return;
      }
      const result = await readPage(cursor ?? undefined);
      if (controller.signal.aborted) return;
      setRemote((previous) => mergeQueueItems(cursor ? previous : [], result.items));
      setNextCursor(result.next_cursor);
      setHasLoaded(true);
      setPageCount((previous) => (cursor ? previous + 1 : 1));
    };
    load()
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(error instanceof ApiError ? error.message : "Não foi possível carregar a fila.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, area, type, cursor, retry, restoring, navigation]);

  useEffect(() => {
    const previous = navigation.current;
    navigation.current = {
      area,
      type,
      items: remote,
      cursor,
      nextCursor,
      loaded: hasLoaded,
      pageCount,
      anchor: previous?.anchor ?? null,
      scrollY: previous?.scrollY ?? 0,
    };
  }, [navigation, area, type, remote, cursor, nextCursor, hasLoaded, pageCount]);

  useEffect(() => {
    if (loading || !restoring) return;
    const frame = requestAnimationFrame(() => {
      const saved = navigation.current;
      const target = saved?.anchor && document.getElementById(`proposal-${saved.anchor}`);
      if (target) target.scrollIntoView({ block: "center" });
      else window.scrollTo(0, saved?.scrollY ?? 0);
    });
    return () => cancelAnimationFrame(frame);
  }, [loading, restoring, navigation]);

  const rememberPosition = (id: string) => {
    if (navigation.current) {
      navigation.current.anchor = id;
      navigation.current.scrollY = window.scrollY;
    }
  };
  const reset = () => {
    setRestoring(false);
    setHasLoaded(false);
    setPageCount(0);
    setRemote([]);
    setNextCursor(null);
    setCursor(null);
    if (navigation.current) {
      navigation.current.anchor = null;
      navigation.current.scrollY = 0;
    }
  };

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
        actions={
          backend && can(me, "merge:decide") ? (
            <Link
              href="/saneamento/lotes/"
              className="inline-flex h-11 items-center rounded-md bg-esmeralda px-5 font-bold text-on-esmeralda"
            >
              Aprovar correções em lote
            </Link>
          ) : undefined
        }
      />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs
          id="sanitization"
          label="Fila de saneamento"
          value={area}
          onChange={(value) => {
            setArea(value);
            reset();
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
            reset();
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

      <TabPanels id="sanitization" values={["TECHNICAL", "FISCAL", "HISTORY"]} active={area}>
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
                <tr key={p.id} id={`proposal-${p.id}`} className="hover:bg-ink/60">
                  <Td>
                    <Link
                      onClick={() => rememberPosition(p.id)}
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
                    <div className="flex flex-col items-start gap-1">
                      <ProposalTypeBadge value={p.proposal_type} />
                      <ProposalOriginBadge value={p.origin} />
                    </div>
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
                    <AutomaticDecision
                      status={p.status}
                      mode={"application_mode" in p ? p.application_mode : undefined}
                      automation={"automation" in p ? p.automation : undefined}
                    />
                    {p.created_at && (
                      <p className="mt-1 font-mono text-[11px] text-muted">
                        {fmtDate(p.created_at)}
                      </p>
                    )}
                  </Td>
                  <Td className="text-right">
                    <Code>{p.ranking_score?.toFixed(2) ?? "—"}</Code>
                  </Td>
                  <Td>
                    <Link
                      onClick={() => rememberPosition(p.id)}
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
          <Button
            disabled={loading}
            onClick={() => {
              setRestoring(false);
              setCursor(nextCursor);
            }}
          >
            Carregar mais propostas
          </Button>
        )}
        <p className="mt-3 text-xs text-muted">
          O score só ordena a fila. Ele não é probabilidade de equivalência e não aprova nada
          sozinho.
        </p>
      </TabPanels>
    </>
  );
}
