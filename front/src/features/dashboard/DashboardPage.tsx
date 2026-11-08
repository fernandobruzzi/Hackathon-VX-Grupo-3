"use client";

import { useEffect, useState } from "react";
import { Card, Kpi, PageHeader, Badge, Button, EmptyState } from "@/components/ui";
import { SavingsPanel } from "./SavingsPanel";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { can } from "@/lib/permissions";
import { fmtBRL, fmtDate, fmtInt, fmtPct } from "@/lib/format";
import type { DashboardMetrics } from "@/types/api";
import { dashboard } from "@/mocks/data";
import { NcmSection } from "./NcmSection";

export function DashboardPage() {
  const { me, backend, api } = useAuth();
  const financial = can(me, "metrics:financial");
  const permitted = can(me, "metrics:quality");
  const canSnapshot = can(me, "batch:run");
  const [creating, setCreating] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [remote, setRemote] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(backend);
  const [error, setError] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!backend || !permitted) return;
    const controller = new AbortController();
    setRemote(null);
    setLoading(true);
    setError(null);
    setEmpty(false);
    api
      .request("get", "/api/v1/dashboard/metrics", {
        query: { view: financial ? "executive" : "quality" },
        signal: controller.signal,
      })
      .then((result) => {
        if (!controller.signal.aborted) setRemote(result);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) setEmpty(true);
        else
          setError(
            error instanceof ApiError ? error.message : "Não foi possível carregar as métricas.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, financial, permitted, retry]);

  const createSnapshot = () => {
    setCreating(true);
    setSnapshotError(null);
    api
      .request("post", "/api/v1/dashboard/snapshots", {
        body: { dataset_id: remote?.dataset_id ?? null },
      })
      .then(() => setRetry((value) => value + 1))
      .catch((error: unknown) =>
        setSnapshotError(
          error instanceof ApiError ? error.message : "Não foi possível gerar o snapshot.",
        ),
      )
      .finally(() => setCreating(false));
  };

  const d: DashboardMetrics | null = backend ? remote : dashboard;
  const b = d?.before;
  const a = d?.after ?? null;
  const snapshot = d?.after_snapshot ?? null;
  const pipe = d?.pipeline;
  const issues = b
    ? [
        { label: "Sem NCM", value: b.missing_ncm, after: a?.missing_ncm },
        {
          label: "Unidade fora do padrão",
          value: b.noncanonical_unit,
          after: a?.noncanonical_unit,
        },
        { label: "Códigos duplicados ativos", value: b.duplicate_codes, after: a?.duplicate_codes },
        { label: "Bloqueados", value: b.blocked, after: a?.blocked },
        { label: "Obsoletos", value: b.obsolete, after: a?.obsolete },
      ]
    : [];
  const max = Math.max(1, ...issues.flatMap((i) => [i.value, i.after ?? 0]));

  return (
    <>
      <PageHeader
        n="04"
        eyebrow="Qualidade da base"
        title="Como a base está, e quanto já foi corrigido"
        description="Situação original dos centros autorizados, propostas e aplicações registradas. O depois vem de um snapshot gerado só com propostas aplicadas."
      />
      {!permitted ? (
        <EmptyState title="Acesso restrito">
          Métricas de qualidade são reservadas à Governança e ao Auditor fiscal.
        </EmptyState>
      ) : (
        <>
          {!backend && (
            <p role="status" className="mb-4 text-sm text-aviso">
              Demonstração simulada: estes números são exemplos.
            </p>
          )}
          {loading && (
            <p role="status" className="mb-4 text-sm text-muted">
              Carregando métricas…
            </p>
          )}
          {error && (
            <div role="alert" className="mb-4 text-alerta">
              {error}{" "}
              <Button onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
            </div>
          )}
          {empty && (
            <EmptyState title="Nenhuma base disponível">
              Importe um dataset com estoque nos centros autorizados para consultar as métricas.
            </EmptyState>
          )}
          {d && b && pipe && (
            <>
              <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <Kpi
                  label="Materiais na base original"
                  value={fmtInt(b.materials_total)}
                  sub={`${fmtInt(b.active)} ativos no snapshot original`}
                />
                <Kpi
                  label="Propostas geradas"
                  value={fmtInt(pipe.proposals_total)}
                  sub={`${fmtInt(pipe.pending)} pendentes`}
                />
                <Kpi
                  tone="block"
                  label="Propostas aplicadas na base"
                  value={fmtInt(pipe.applied)}
                  sub={`${fmtInt(pipe.rejected)} rejeitadas · ${fmtInt(pipe.stale)} desatualizadas`}
                />
                <Kpi
                  label="Precisão das unificações"
                  value={fmtPct(d.evaluation.merge_precision)}
                  sub={
                    d.evaluation.reviewed_pairs
                      ? `${fmtInt(d.evaluation.reviewed_pairs)} pares revisados${backend ? "" : " · exemplo"}`
                      : "Avaliação independente indisponível"
                  }
                />
              </section>
              <section className="mt-6 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
                <Card>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
                      {a ? "Problemas na base · antes e depois" : "Problemas na base · antes"}
                    </p>
                    {a && snapshot ? (
                      <Badge tone="success">Snapshot de {fmtDate(snapshot.created_at)}</Badge>
                    ) : (
                      <Badge tone="neutral">Comparação indisponível</Badge>
                    )}
                  </div>
                  <ul className="mt-5 flex flex-col gap-4">
                    {issues.map((i) => (
                      <li
                        key={i.label}
                        className="grid grid-cols-[1fr_1fr_64px] items-center gap-3 text-sm"
                      >
                        <span className="font-semibold">{i.label}</span>
                        <span className="flex flex-col gap-1">
                          <span className="h-3 rounded-full bg-surface-2">
                            <span
                              className="block h-full rounded-full bg-serie-1"
                              style={{ width: `${(i.value / max) * 100}%` }}
                            />
                          </span>
                          {i.after !== undefined && (
                            <span className="h-3 rounded-full bg-surface-2">
                              <span
                                className="block h-full rounded-full bg-esmeralda"
                                style={{ width: `${(i.after / max) * 100}%` }}
                              />
                            </span>
                          )}
                        </span>
                        <span className="text-right font-mono">
                          {fmtInt(i.value)}
                          {i.after !== undefined && (
                            <span className="block text-verde">{fmtInt(i.after)}</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-5 text-xs text-muted">
                    Dataset {d.dataset_id.slice(0, 8)} · contagens dos registros originais, sem
                    alterar saldos.
                  </p>
                  {a && snapshot ? (
                    <p className="mt-2 text-xs text-muted">
                      Depois: {fmtInt(snapshot.applied_proposals)} propostas aplicadas,{" "}
                      {fmtInt(snapshot.materials_changed)} materiais alterados, cada um rastreado
                      até sua proposta em {snapshot.export_key}.{" "}
                      {snapshot.inventory_value_conserved
                        ? "Valor total do estoque conservado."
                        : "Valor do estoque não conferido: há saldo sem valor ou diferença."}
                    </p>
                  ) : (
                    <p className="mt-2 text-xs text-muted">
                      Sem snapshot posterior, a comparação antes e depois não está disponível.
                    </p>
                  )}
                  {backend && canSnapshot && (
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <Button onClick={createSnapshot} disabled={creating}>
                        {creating ? "Gerando snapshot…" : "Gerar snapshot posterior"}
                      </Button>
                      <span className="text-xs text-muted">
                        Registra só as propostas já aplicadas.
                      </span>
                    </div>
                  )}
                  {snapshotError && (
                    <p role="alert" className="mt-2 text-sm text-alerta">
                      {snapshotError}
                    </p>
                  )}
                </Card>
                <Card className="flex flex-col gap-4">
                  <p className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
                    Funil das propostas
                  </p>
                  {[
                    ["Geradas", pipe.proposals_total],
                    ["Pendentes", pipe.pending],
                    ["Aplicadas", pipe.applied],
                    ["Rejeitadas", pipe.rejected],
                    ["Desatualizadas", pipe.stale],
                  ].map(([label, value], index) => (
                    <div key={label}>
                      <div className="flex justify-between text-sm">
                        <span className="font-semibold">{label}</span>
                        <span className="font-mono">{fmtInt(value as number)}</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pipe.proposals_total ? ((value as number) / pipe.proposals_total) * 100 : 0}%`,
                            background: [
                              "var(--text-muted)",
                              "var(--aviso)",
                              "var(--esmeralda)",
                              "var(--alerta)",
                              "var(--info)",
                            ][index],
                          }}
                        />
                      </div>
                    </div>
                  ))}
                  <p className="mt-auto text-xs text-muted">
                    Uma aplicação é uma proposta efetivada, não uma contagem de materiais nem uma
                    economia financeira.
                  </p>
                </Card>
              </section>
              <NcmSection ncm={d.ncm} />
              {financial && d.financial && <SavingsPanel data={d.financial} />}
              <section className="mt-6">
                {financial && d.financial ? (
                  <Card className="grid gap-6 md:grid-cols-3">
                    <div>
                      <p className="text-xs font-extrabold text-verde uppercase">
                        Valor contábil do estoque original
                      </p>
                      <p className="mt-2 text-2xl font-extrabold">
                        {fmtBRL(d.financial.inventory_book_value)}
                      </p>
                      <p className="mt-2 text-xs text-muted">
                        Dados sintéticos do desafio · centros autorizados
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-extrabold text-verde uppercase">
                        Economia realizada
                      </p>
                      <p className="mt-2 text-2xl font-extrabold">
                        {fmtBRL(d.financial.realized_savings)}
                      </p>
                      <p className="mt-2 text-xs text-muted">
                        Indisponível: consolidar códigos conserva o valor do estoque.
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-extrabold text-verde uppercase">
                        Economia estimada
                      </p>
                      <p className="mt-2 text-2xl font-extrabold">
                        {fmtBRL(d.financial.estimated_savings)}
                      </p>
                      <p className="mt-2 text-xs text-muted">
                        Calculada apenas nos componentes com premissas registradas, detalhados
                        acima.
                      </p>
                    </div>
                  </Card>
                ) : (
                  <Card className="text-sm text-muted">
                    Métricas financeiras ficam restritas ao Auditor fiscal.
                  </Card>
                )}
              </section>
            </>
          )}
        </>
      )}
    </>
  );
}
