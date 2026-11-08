import { Card, Kpi } from "@/components/ui";
import { fmtDate, fmtInt, fmtPct } from "@/lib/format";
import type { DashboardMetrics } from "@/types/api";

export function NcmSection({ ncm }: { ncm: DashboardMetrics["ncm"] }) {
  const benchmark = ncm.benchmark;
  return (
    <section className="mt-6" aria-labelledby="ncm-heading">
      <Card>
        <h2 id="ncm-heading" className="text-lg font-extrabold">
          Tratamento de NCM
        </h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <Kpi label="NCM ausente no original" value={fmtInt(ncm.missing_before)} />
          <Kpi
            label="NCM ausente depois"
            value={ncm.missing_after === null ? "Indisponível" : fmtInt(ncm.missing_after)}
            sub={
              ncm.missing_after === null
                ? "Sem snapshot posterior"
                : "Snapshot posterior registrado"
            }
          />
          <Kpi
            label="Precisão operacional fiscal"
            value={fmtPct(ncm.operational_precision)}
            sub={
              ncm.fiscal_decided
                ? `${fmtInt(ncm.fiscal_approved_decisions)} aprovações / ${fmtInt(ncm.fiscal_decided)} decisões fiscais`
                : "Sem decisões fiscais"
            }
          />
        </div>
        <p className="mt-4 text-xs text-muted">
          Aceitação operacional = aprovadas / decididas pela revisão fiscal. Não representa acurácia
          independente. Cada proposta conta uma vez, mesmo com duas revisões ou vários centros.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">
              Funil das propostas de NCM do dataset e centros autorizados
            </caption>
            <thead>
              <tr>
                {[
                  "Propostas de NCM",
                  "Criadas",
                  "Aprovadas fiscal",
                  "Rejeitadas",
                  "Pendentes fiscais",
                  "Desatualizadas",
                ].map((label) => (
                  <th className="p-2" key={label}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["Conteúdo", ncm.content],
                  ["Somente formato", ncm.format_only],
                ] as const
              ).map(([label, counts]) => (
                <tr key={label}>
                  <th className="p-2">{label}</th>
                  {[
                    counts.created,
                    counts.fiscal_approved,
                    counts.rejected,
                    counts.pending,
                    counts.stale,
                  ].map((count, index) => (
                    <td className="p-2 font-mono" key={index}>
                      {fmtInt(count)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          O funil mostra o desfecho atual: rejeição ou desatualização prevalece sobre uma aprovação
          fiscal anterior. A precisão conserva todas as decisões fiscais registradas, mesmo quando a
          proposta foi posteriormente rejeitada na revisão técnica.
        </p>
        <details className="mt-6">
          <summary className="cursor-pointer font-bold">
            Medição de desenvolvimento · resultado por família
          </summary>
          <p className="mt-3 text-sm text-muted">
            Benchmark {benchmark.benchmark_version} · medido em {fmtDate(benchmark.measured_at)} ·
            regras {benchmark.rules_version}. Os rótulos documentais não têm revisão independente.
            Estes resultados vêm de uma base de desenvolvimento, separada do tenant e das decisões
            fiscais operacionais.
          </p>
          <p className="mt-2 text-xs text-muted">
            {Object.entries(benchmark.algorithms)
              .map(([name, version]) => `${name}: ${version}`)
              .join(" · ")}
          </p>
          <div className="mt-3 max-h-96 overflow-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">
                Benchmark documental de desenvolvimento por família
              </caption>
              <thead>
                <tr>
                  {[
                    "Família",
                    "Problemas resolvidos / elegíveis",
                    "Alterações indevidas",
                    "Abstenções",
                  ].map((label) => (
                    <th className="p-2" key={label}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {benchmark.families.map((family) => (
                  <tr key={family.family}>
                    <th className="p-2">{family.family}</th>
                    <td className="p-2 font-mono">
                      {fmtInt(family.resolved)} / {fmtInt(family.eligible_problems)}
                    </td>
                    <td className="p-2 font-mono">{fmtInt(family.improper_changes)}</td>
                    <td className="p-2 font-mono">{fmtInt(family.abstentions)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
    </section>
  );
}
