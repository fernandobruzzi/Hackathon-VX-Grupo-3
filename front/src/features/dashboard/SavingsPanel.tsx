import { Card } from "@/components/ui";
import type { DashboardMetrics } from "@/types/api";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const money = (value: string | null) =>
  value === null ? "Indisponível" : brl.format(Number(value));
const names: Record<string, string> = {
  registration_cost: "Custo por cadastro (R$)",
  code_annual_cost: "Custo por código/ano (R$)",
  review_minutes_before: "Minutos por revisão antes",
  review_minutes_after: "Minutos por revisão depois",
  hourly_cost: "Custo da hora (R$)",
};

export function SavingsPanel({ data }: { data: NonNullable<DashboardMetrics["financial"]> }) {
  return (
    <section className="mt-6" aria-label="Economia e premissas">
      <Card>
        <h2 className="text-lg font-extrabold">Economia e premissas</h2>
        <p className="mt-2 text-sm text-muted">
          Dados sintéticos do desafio. Nenhum valor aqui comprova economia realizada em uma empresa.
        </p>
        <p className="mt-3 text-sm text-muted">
          Componentes separados: benefício por cadastro, custo anual dos códigos, capacidade de
          revisão e estoque atendido têm naturezas e períodos diferentes. O total agregado fica
          indisponível; capacidade de trabalho não é economia de caixa.
        </p>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {(data.components ?? []).map((component) => (
            <div className="rounded-md bg-surface-2 p-4" key={component.key}>
              <p className="text-xs font-semibold text-verde">
                {component.kind === "ESTIMATED" ? "Estimativa com hipótese" : "Medido no kit"}
              </p>
              <h3 className="mt-1 font-bold">{component.label}</h3>
              <p className="mt-2 text-xl font-extrabold">{money(component.amount_brl)}</p>
              <p className="mt-1 font-mono text-sm">
                {component.count ?? "Indisponível"} {component.count_unit}
              </p>
              {component.estimated_hours != null && (
                <p className="mt-2 text-sm">
                  {Number(component.estimated_hours).toLocaleString("pt-BR", {
                    maximumFractionDigits: 4,
                  })}{" "}
                  horas estimadas
                </p>
              )}
              {Object.entries(component.quantities ?? {}).map(([unit, quantity]) => (
                <p key={unit} className="text-sm">
                  Entregue: {quantity} {unit}, líquido de reversões
                </p>
              ))}
              <p className="mt-2 text-xs text-muted">{component.formula}</p>
              {component.unavailable_reason && (
                <p className="mt-2 text-xs text-aviso">{component.unavailable_reason}</p>
              )}
              {component.kind === "MEASURED_KIT_VALUE" && (
                <p className="mt-2 text-xs text-muted">
                  Atendimento registrado não comprova compra evitada e não integra a estimativa de
                  economia.
                </p>
              )}
              {!!(component.stock_evidence ?? []).length && (
                <details className="mt-3 text-xs">
                  <summary className="cursor-pointer">Evidência do preço original usado</summary>
                  <ul className="mt-2 space-y-2">
                    {(component.stock_evidence ?? []).map((evidence) => (
                      <li key={evidence.delivery_id}>
                        {evidence.quantity} {evidence.unit} × {money(evidence.unit_price)} ·{" "}
                        {evidence.source} · {evidence.recorded_on}
                        <p className="mt-1 break-all text-muted">
                          Linhas originais: {evidence.snapshot_ids.join(", ")}. Fatores:{" "}
                          {Object.entries(evidence.factors)
                            .map(([id, factor]) => `${id}: ${factor}`)
                            .join("; ")}
                          .
                        </p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {!!(component.assumptions ?? []).length && (
                <details className="mt-3 text-xs">
                  <summary className="cursor-pointer">Premissas hipotéticas usadas</summary>
                  <dl className="mt-2 space-y-2">
                    {(component.assumptions ?? []).map((a) => (
                      <div key={a.key}>
                        <dt className="font-semibold">
                          {names[a.key]}: {a.value}
                        </dt>
                        <dd className="text-muted">
                          {a.source} · {a.recorded_on}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            </div>
          ))}
        </div>
        {data.assumption_source && (
          <p className="mt-4 text-xs break-all text-muted">
            Premissas {data.assumption_source.version} · SHA-256 {data.assumption_source.sha256}
          </p>
        )}
      </Card>
    </section>
  );
}
