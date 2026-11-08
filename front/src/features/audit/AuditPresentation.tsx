import type { AuditEvent } from "@/types/api";

const actions: Record<string, string> = {
  ORDER_SUBMIT: "Pedido enviado para revisão",
  ORDER_SUBMITTED: "Pedido enviado para revisão",
  ORDER_APPROVED_TECHNICAL: "Pedido aprovado pela Governança",
  ORDER_REGISTERED: "Pedido aprovado pelo Fiscal e material cadastrado",
  ORDER_REJECTED: "Pedido rejeitado",
  ORDER_FOUND_EXISTING: "Material existente identificado no pedido",
  ORDER_COMPLEMENTED: "Pedido complementado",
  ORDER_TECHNICAL_REOPENED: "Revisão técnica do pedido reaberta",
  PROPOSAL_APPROVE_TECHNICAL: "Proposta aprovada pela Governança",
  PROPOSAL_APPROVE_FISCAL: "Proposta aprovada pelo Fiscal",
  PROPOSAL_REJECT_TECHNICAL: "Proposta rejeitada pela Governança",
  PROPOSAL_REJECT_FISCAL: "Proposta rejeitada pelo Fiscal",
  PROPOSAL_AUTO_APPLY: "Correção aplicada automaticamente",
  PROPOSAL_AUTO_STALE: "Correção automática impedida por dados desatualizados",
  PROPOSAL_STALE: "Proposta desatualizada",
  PROPOSAL_SUPERSEDED: "Proposta substituída por nova revisão",
  MANUAL_REVIEW_PROPOSE: "Pendência encaminhada para proposta",
  LOT_REVIEW_OPEN: "Revisão de lote aberta",
  LOT_REVIEW_APPROVE: "Lote aprovado pela Governança",
  LOT_REVIEW_RETURNED: "Lote devolvido para revisão individual",
  QUALITY_SNAPSHOT_CREATED: "Retrato de qualidade registrado",
  NCM_REVIEW_APPROVE: "Classificação NCM aprovada pelo Fiscal",
  MERGE_APPROVE: "Unificação de materiais aprovada",
  MERGE_REJECT: "Unificação de materiais rejeitada",
  BATCH_START: "Execução de saneamento iniciada",
};

export function AuditAction({ action }: { action: string }) {
  return (
    <>
      <span>{Object.hasOwn(actions, action) ? actions[action] : "Ação ainda não traduzida"}</span>
      <details className="mt-1 text-xs text-muted">
        <summary className="cursor-pointer">Identificador técnico</summary>
        <code className="break-all">{action}</code>
      </details>
    </>
  );
}

type State = Record<string, unknown>;
const record = (value: unknown): State =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? (value as State) : {};
const fields: Record<string, string> = {
  unit: "Unidade",
  ncm: "NCM",
  pdm_description: "Descrição PDM",
  status: "Status",
  active_code_target: "Código principal (identificador)",
  primary_material_id: "Material principal (identificador)",
  technical_review_status: "Revisão técnica",
  fiscal_review_status: "Revisão fiscal",
};
const available = (value: unknown) =>
  typeof value === "string"
    ? value.trim() !== ""
    : typeof value === "number"
      ? Number.isFinite(value)
      : typeof value === "boolean";
const display = (state: State, key: string) =>
  !Object.hasOwn(state, key)
    ? "Não registrado"
    : !available(state[key])
      ? "Não informado"
      : String(state[key]);

function compare(before: State, after: State, resource: string) {
  return Object.entries(fields).flatMap(([key, label]) => {
    if (!Object.hasOwn(before, key) && !Object.hasOwn(after, key)) return [];
    if (available(before[key]) && available(after[key]) && before[key] === after[key]) return [];
    return [
      {
        key: `${resource}:${key}`,
        resource,
        label,
        before: display(before, key),
        after: display(after, key),
        confirmed: available(before[key]) && available(after[key]),
      },
    ];
  });
}

/** Compara somente observações presentes; nunca trata o changeset como alteração aplicada. */
export function AuditChanges({ event }: { event: AuditEvent }) {
  const before = record(event.before),
    after = record(event.after);
  const rows = compare(before, after, "Evento");
  const previous = Array.isArray(before.materials) ? before.materials.map(record) : [];
  const following = Array.isArray(after.materials) ? after.materials.map(record) : [];
  const ids = new Set(
    [...previous, ...following]
      .map((m) => m.id)
      .filter((id): id is string => typeof id === "string"),
  );
  for (const id of ids) {
    const old = previous.filter((m) => m.id === id),
      next = following.filter((m) => m.id === id);
    if (old.length > 1 || next.length > 1) continue;
    const left = old[0] ?? {},
      right = next[0] ?? {};
    const code =
      typeof right.material_code === "string"
        ? right.material_code
        : typeof left.material_code === "string"
          ? left.material_code
          : id;
    rows.push(...compare(left, right, `Material ${code} (${id})`));
  }
  return (
    <div className="max-w-4xl min-w-0 text-sm">
      {rows.length ? (
        <ul className="space-y-3">
          {rows.map((row) => (
            <li key={row.key} className="border-borda rounded border p-3 [overflow-wrap:anywhere]">
              <p className="text-xs text-muted">{row.resource}</p>
              <p className="font-semibold">{row.label}</p>
              <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-muted">Anterior</dt>
                  <dd className="whitespace-pre-wrap">{row.before}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Posterior</dt>
                  <dd className="whitespace-pre-wrap">{row.after}</dd>
                </div>
              </dl>
              <p className="mt-2 text-xs text-muted">
                {row.confirmed
                  ? "Alterado"
                  : "Comparação indisponível: valor ausente ou não informado."}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">
          {!event.before || !event.after
            ? "Antes e depois indisponíveis para comparação."
            : "Nenhuma alteração comparável nos campos suportados. Consulte os dados registrados para outros campos."}
        </p>
      )}
      <details className="mt-3">
        <summary className="cursor-pointer text-verde">
          Dados registrados (incluindo execução e campos não traduzidos)
        </summary>
        <p className="mt-2 text-xs text-muted">
          Somente os dados disponibilizados pela API. Ausências não comprovam alterações.
        </p>
        <pre className="mt-2 max-h-80 overflow-auto text-xs [overflow-wrap:anywhere] whitespace-pre-wrap">
          {JSON.stringify({ before: event.before ?? null, after: event.after ?? null }, null, 2)}
        </pre>
      </details>
    </div>
  );
}
