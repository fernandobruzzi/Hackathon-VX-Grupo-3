"use client";

import { Card, Kpi, PageHeader, Badge } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { fmtBRL, fmtInt, fmtPct } from "@/lib/format";
import { dashboard as d } from "@/mocks/data";

/**
 * Dono: Pessoa 5 (features/dashboard/**). Exporta DashboardPage; a rota é registrada pela Pessoa 4.
 * Integração: GET /api/v1/dashboard/metrics?view=quality | executive (executive exige metrics:financial).
 */
export function DashboardPage() {
  const { me } = useAuth();
  const financial = can(me, "metrics:financial");
  const b = d.before;
  const issues = [
    { label: "Sem NCM", value: b.missing_ncm },
    { label: "Unidade fora do padrão", value: b.noncanonical_unit },
    { label: "Bloqueados (legado)", value: b.blocked },
    { label: "Obsoletos", value: b.obsolete },
  ];
  const max = Math.max(...issues.map((i) => i.value));
  const pipe = d.pipeline;

  return (
    <>
      <PageHeader
        n="04"
        eyebrow="Qualidade da base"
        title="Como a base está, e quanto já foi corrigido"
        description="Separa o que foi proposto, o que foi aplicado e o que é estimativa. O depois só aparece com um snapshot aprovado."
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Materiais na base"
          value={fmtInt(b.materials_total)}
          sub={`${fmtInt(b.active)} ativos`}
        />
        <Kpi
          label="Propostas geradas"
          value={fmtInt(pipe.proposals_total)}
          sub={`${fmtInt(pipe.pending)} pendentes`}
        />
        <Kpi
          tone="block"
          label="Aplicadas na base"
          value={fmtInt(pipe.applied)}
          sub={`${fmtInt(pipe.rejected)} rejeitadas · ${pipe.stale} desatualizadas`}
        />
        <Kpi
          label="Precisão das unificações"
          value={fmtPct(d.evaluation.merge_precision)}
          sub={`${d.evaluation.reviewed_pairs} pares revisados · exemplo`}
        />
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
              Problemas na base · antes
            </p>
            <Badge tone="neutral">depois: aguardando snapshot</Badge>
          </div>
          <ul className="mt-5 flex flex-col gap-4">
            {issues.map((i) => (
              <li
                key={i.label}
                className="grid grid-cols-[180px_1fr_72px] items-center gap-3 text-sm"
              >
                <span className="font-semibold">{i.label}</span>
                <span className="h-3 rounded-full bg-surface-2">
                  <span
                    className="block h-full rounded-full bg-serie-1"
                    style={{ width: `${(i.value / max) * 100}%` }}
                  />
                </span>
                <span className="text-right font-mono">{fmtInt(i.value)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs text-muted">
            Contagens do kit do desafio (dataset {d.dataset_id.slice(0, 8)}).
          </p>
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
          ].map(([l, v], idx) => (
            <div key={l as string}>
              <div className="flex justify-between text-sm">
                <span className="font-semibold">{l}</span>
                <span className="font-mono">{fmtInt(v as number)}</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${((v as number) / pipe.proposals_total) * 100}%`,
                    background: [
                      "var(--text-muted)",
                      "var(--aviso)",
                      "var(--esmeralda)",
                      "var(--alerta)",
                    ][idx],
                  }}
                />
              </div>
            </div>
          ))}
          <p className="mt-auto text-xs text-muted">
            Valores de exemplo até o lote completo rodar.
          </p>
        </Card>
      </section>

      <section className="mt-6">
        {financial ? (
          <Card tone="block" className="grid gap-6 md:grid-cols-3">
            <div>
              <p className="text-xs font-extrabold tracking-[0.04em] text-esmeralda uppercase">
                Valor contábil do estoque
              </p>
              <p className="mt-2 text-[34px] leading-none font-extrabold text-esmeralda">
                {fmtBRL(d.financial.inventory_book_value)}
              </p>
              <p className="mt-2 font-mono text-xs text-on-profundo/80">
                dados sintéticos do desafio
              </p>
            </div>
            <div>
              <p className="text-xs font-extrabold tracking-[0.04em] text-esmeralda uppercase">
                Economia realizada
              </p>
              <p className="mt-2 text-2xl font-extrabold">{fmtBRL(d.financial.realized_savings)}</p>
              <p className="mt-1 text-xs text-on-profundo/80">só após unificações aplicadas</p>
            </div>
            <div>
              <p className="text-xs font-extrabold tracking-[0.04em] text-esmeralda uppercase">
                Economia estimada
              </p>
              <p className="mt-2 text-2xl font-extrabold">
                {fmtBRL(d.financial.estimated_savings)}
              </p>
              <p className="mt-1 text-xs text-on-profundo/80">
                premissas em pitch/roi-assumptions.md
              </p>
            </div>
          </Card>
        ) : (
          <Card className="text-sm text-muted">
            Métricas financeiras ficam restritas ao Auditor fiscal (view=executive).
          </Card>
        )}
      </section>
    </>
  );
}
