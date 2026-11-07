"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Badge,
  Button,
  Card,
  Code,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import type { components } from "@/types/api.generated";

type Review = components["schemas"]["ManualReview"];
type ReviewList = components["schemas"]["ManualReviewList"];
type Catalog = components["schemas"]["ManualReviewCatalog"];
type Completeness = components["schemas"]["MaterialCompletenessReview"];
export const REASON_LABELS: Record<string, string> = {
  ENRICHMENT_REQUIRED: "Dados técnicos a complementar",
  DESCRICAO_FORA_DO_PADRAO: "Descrição incompleta ou fora do padrão",
  SEM_CLASSE_CONFIAVEL: "Sem classe confiável",
  CLASSE_NAO_CONFIRMADA: "Classe não confirmada",
  UNIDADE_SEM_FATOR: "Embalagem sem fator de conversão",
  UNIDADE_AUSENTE: "Unidade ausente",
  UNIDADE_DIFERENTE_DA_CLASSE: "Unidade diferente da classe",
  MATERIAL_NAO_ATIVO: "Material bloqueado ou obsoleto",
};

const GAP_LABELS: Record<string, string> = {
  CLASS_UNRESOLVED: "Classe a confirmar",
  CLASS_OUT_OF_SCOPE: "Classe não reconhecida no PDM",
  CONTRADICTORY_OBSERVATIONS: "Conflito no registro",
  CONFLICTING_SOURCES: "Conflito entre fontes",
  IDENTITY_NOT_CONFIRMED: "Identidade do material a confirmar",
  TEXT_NOT_RECOGNIZED: "Trecho ainda não interpretado",
  NO_SUPPORTED_EVIDENCE: "Sem evidência suficiente",
  CONDITION_UNRESOLVED: "Aplicabilidade a confirmar",
  INVALID_VALUE: "Valor incompatível com o PDM",
};

export function CompletenessDiagnostics({ completeness }: { completeness?: Completeness | null }) {
  if (!completeness) return null;
  const classification = completeness.classification;
  return (
    <div className="mt-2 max-w-md space-y-2 text-sm">
      {!!completeness.before.missing_required.length && (
        <p>Faltam: {completeness.before.missing_required.join(", ")}.</p>
      )}
      {!!completeness.before.conditional_pending.length && (
        <p>Aplicabilidade a confirmar: {completeness.before.conditional_pending.join(", ")}.</p>
      )}
      {classification && classification.status !== "CLASSIFIED" && (
        <p>
          {classification.status === "UNRESOLVED"
            ? "Classe a confirmar"
            : "Classe não reconhecida no PDM"}
          {classification.candidate_class_ids.length
            ? `: ${classification.candidate_class_ids.join(", ")}.`
            : "."}
        </p>
      )}
      {!!completeness.gaps?.length && (
        <ul className="list-disc space-y-1 pl-4">
          {completeness.gaps.map((gap, index) => (
            <li key={`${gap.attribute ?? "classe"}-${gap.reason}-${index}`}>
              <span className="font-semibold">{GAP_LABELS[gap.reason] ?? gap.reason}: </span>
              {gap.question}
            </li>
          ))}
        </ul>
      )}
      {Object.entries(completeness.record_conflicts ?? {}).map(([name, values]) => (
        <p key={`record-${name}`} className="text-aviso">
          Conflito no registro · {name}: {values.join(", ")}.
        </p>
      ))}
      {Object.entries(completeness.conflicts).map(([name, values]) => (
        <p key={`sources-${name}`} className="text-aviso">
          Conflito entre fontes · {name}: {values.join(", ")}.
        </p>
      ))}
      {!!completeness.assisted_candidates?.length && (
        <details>
          <summary className="cursor-pointer font-semibold">Leituras a conferir</summary>
          <p className="mt-1 text-muted">
            Confirmação manual necessária. Confira o trecho e registre a fonte ao complementar.
          </p>
          {completeness.assisted_candidates.map((candidate, index) => (
            <div key={`${candidate.attribute}-${index}`} className="mt-2">
              <p>
                {candidate.attribute}: <strong>{candidate.value}</strong>
              </p>
              <p className="text-xs text-muted">Campo de origem: {candidate.source_field}</p>
              <blockquote className="mt-1 whitespace-pre-wrap">“{candidate.excerpt}”</blockquote>
            </div>
          ))}
        </details>
      )}
      {!!Object.keys(completeness.suggestions).length && (
        <Link className="inline-block text-verde underline" href="/enriquecimento/">
          Revisar sugestões com fontes
        </Link>
      )}
    </div>
  );
}

function message(error: unknown) {
  if (error instanceof ApiError) {
    const fields = [error.error.details.missing, error.error.details.invalid].flatMap((v) =>
      Array.isArray(v) ? v.map(String) : [],
    );
    return error.message + (fields.length ? ` Confira: ${fields.join(", ")}.` : "");
  }
  return "Não foi possível concluir a consulta. Tente novamente.";
}

export function ManualReviewsPage() {
  const { api, backend } = useAuth();
  const requestedRun = useSearchParams().get("run_id");
  const [data, setData] = useState<ReviewList | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [runId, setRunId] = useState<string | undefined>(requestedRun ?? undefined);
  const [reason, setReason] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [code, setCode] = useState("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [selected, setSelected] = useState<Review | null>(null);
  const [createdProposal, setCreatedProposal] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setSelected(null);
    Promise.all([
      api.request("get", "/api/v1/manual-reviews", {
        query: {
          run_id: runId,
          reason: reason || undefined,
          material_code: code || undefined,
          cursor,
          limit: 20,
        },
        signal: controller.signal,
      }),
      api.request("get", "/api/v1/manual-reviews/catalog", { signal: controller.signal }),
    ])
      .then(([list, pdm]) => {
        if (controller.signal.aborted) return;
        setData(list);
        setCatalog(pdm);
        // Mantém a paginação na mesma execução se outro batch terminar durante a revisão.
        if (list.run_id) setRunId(list.run_id);
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(message(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, runId, reason, code, cursor, retry]);

  return (
    <>
      <PageHeader
        n="03"
        eyebrow="Revisão manual"
        title="Pendências do saneamento"
        description="Investigue os motivos e complete os dados com uma fonte. Encaminhar cria uma proposta para aprovação da Governança; a base só muda depois da aprovação."
        actions={
          <Link href="/saneamento/" className="font-bold text-verde">
            Ver propostas
          </Link>
        }
      />
      {createdProposal && (
        <p role="status" className="mb-4 text-verde">
          Proposta criada para revisão.{" "}
          <Link className="underline" href={`/saneamento/revisao/?id=${createdProposal}`}>
            Abrir proposta
          </Link>
        </p>
      )}
      {!backend ? (
        <EmptyState title="Conecte à API">
          As pendências usam dados persistidos do batch.
        </EmptyState>
      ) : (
        <>
          <Card className="mb-6">
            <div className="flex flex-wrap items-end gap-4">
              <Field label="Motivo">
                <Select
                  value={reason}
                  disabled={loading}
                  onChange={(e) => {
                    setReason(e.target.value);
                    setCursor(undefined);
                  }}
                >
                  <option value="">Todos os motivos</option>
                  {Object.entries(data?.counts_by_reason ?? {}).map(([key, count]) => (
                    <option key={key} value={key}>
                      {REASON_LABELS[key] ?? key} ({fmtInt(count)})
                    </option>
                  ))}
                </Select>
              </Field>
              <form
                className="flex items-end gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  setCode(codeInput.trim());
                  setCursor(undefined);
                }}
              >
                <Field label="Código do material">
                  <Input
                    value={codeInput}
                    onChange={(e) => setCodeInput(e.target.value)}
                    placeholder="Código exato"
                  />
                </Field>
                <Button type="submit" variant="ghost" disabled={loading}>
                  Buscar
                </Button>
              </form>
              <Button
                variant="ghost"
                disabled={loading}
                onClick={() => {
                  setRunId(requestedRun ?? undefined);
                  setCursor(undefined);
                  setRetry((v) => v + 1);
                }}
              >
                Atualizar
              </Button>
            </div>
            {data?.run_id && (
              <p className="mt-4 text-sm text-muted">
                Execução <Code>{data.run_id.slice(0, 8)}</Code> · {fmtInt(data.materials_total)}{" "}
                materiais com pendência. As contagens preservam todos os motivos observados nessa
                execução, inclusive os já encaminhados.
              </p>
            )}
          </Card>
          {error && (
            <p role="alert" className="mb-4 text-alerta">
              {error}{" "}
              <Button variant="ghost" onClick={() => setRetry((v) => v + 1)}>
                Tentar novamente
              </Button>
            </p>
          )}
          {loading ? (
            <p role="status">Carregando pendências…</p>
          ) : (
            !error && (
              <>
                {!data?.items.length ? (
                  <EmptyState title="Nenhuma pendência encontrada">
                    Execute um novo batch ou ajuste os filtros. Execuções antigas precisam ser
                    refeitas para registrar as pendências por material.
                  </EmptyState>
                ) : (
                  <Table>
                    <thead>
                      <tr>
                        <Th>Material</Th>
                        <Th>Motivos observados</Th>
                        <Th>Encaminhamento</Th>
                        <Th>Ação</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((row) => (
                        <tr key={row.id}>
                          <Td>
                            <Code>{row.observation.material_code}</Code>
                            <p className="mt-1 max-w-md">{row.observation.description}</p>
                            <p className="mt-1 text-xs text-muted">
                              {row.observation.status} · {row.observation.unit}
                            </p>
                          </Td>
                          <Td>
                            {row.reasons.map((r) => (
                              <p key={r} className="mb-1">
                                {REASON_LABELS[r] ?? r}
                              </p>
                            ))}
                            <CompletenessDiagnostics completeness={row.observation.completeness} />
                          </Td>
                          <Td>
                            {row.proposal_id ? (
                              <Link
                                className="text-verde underline"
                                href={`/saneamento/revisao/?id=${row.proposal_id}`}
                              >
                                {row.proposal_status === "APPLIED"
                                  ? "Proposta aplicada"
                                  : row.proposal_status === "REJECTED"
                                    ? "Proposta rejeitada"
                                    : row.proposal_status === "STALE"
                                      ? "Proposta desatualizada"
                                      : "Aguardando aprovação"}
                              </Link>
                            ) : (
                              <Badge tone="warning">A investigar</Badge>
                            )}
                          </Td>
                          <Td>
                            {row.observation.status === "ATIVO" &&
                              !["PENDING", "APPLIED"].includes(row.proposal_status ?? "") && (
                                <Button size="sm" variant="ghost" onClick={() => setSelected(row)}>
                                  Revisar
                                </Button>
                              )}
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )}
                <div className="my-4 flex gap-3">
                  {cursor && (
                    <Button variant="ghost" onClick={() => setCursor(undefined)}>
                      Primeira página
                    </Button>
                  )}
                  {data?.next_cursor && (
                    <Button
                      variant="ghost"
                      onClick={() => setCursor(data.next_cursor ?? undefined)}
                    >
                      Próxima página
                    </Button>
                  )}
                </div>
              </>
            )
          )}
          {selected && catalog && (
            <ResolutionForm
              key={selected.id}
              row={selected}
              catalog={catalog}
              onClose={() => setSelected(null)}
              onSaved={(proposalId) => {
                setCreatedProposal(proposalId);
                setSelected(null);
                setRetry((v) => v + 1);
              }}
            />
          )}
        </>
      )}
    </>
  );
}

function ResolutionForm({
  row,
  catalog,
  onClose,
  onSaved,
}: {
  row: Review;
  catalog: Catalog;
  onClose: () => void;
  onSaved: (proposalId: string) => void;
}) {
  const { api } = useAuth();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
    heading.current?.scrollIntoView({ block: "start" });
  }, []);
  const [classId, setClassId] = useState(row.observation.pdm_class_id ?? "");
  const cls = catalog.classes.find((c) => c.id === classId);
  const [item, setItem] = useState(row.observation.item_name ?? "");
  const [attrs, setAttrs] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(row.observation.attributes).filter(
        (pair): pair is [string, string] => pair[1] !== null,
      ),
    ),
  );
  const [ncm, setNcm] = useState(row.observation.ncm ?? "");
  const [source, setSource] = useState("");
  const [justification, setJustification] = useState("");
  const [factor, setFactor] = useState("");
  const [conversionSource, setConversionSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const attempt = useRef<{ signature: string; key: string } | null>(null);
  const needsConversion = !!cls && row.observation.unit !== cls.unit;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!cls || busy) return;
    const payload = {
      expected_material_version: row.expected_material_version,
      pdm_class_id: cls.id,
      item_name: item,
      attributes: Object.fromEntries(
        Object.entries(attrs)
          .filter(([name, value]) => cls.attributes.some((a) => a.name === name) && value.trim())
          .map(([k, v]) => [k, v.trim()]),
      ),
      unit: cls.unit,
      ncm: ncm || null,
      source,
      reason: justification,
      conversions: needsConversion
        ? [{ from_unit: row.observation.unit, to_unit: cls.unit, factor, source: conversionSource }]
        : [],
    };
    const signature = JSON.stringify(payload);
    if (attempt.current?.signature !== signature)
      attempt.current = { signature, key: crypto.randomUUID() };
    setBusy(true);
    setError(null);
    try {
      const result = await api.request("post", "/api/v1/manual-reviews/{review_id}/propose", {
        params: { review_id: row.id },
        body: payload,
        idempotencyKey: attempt.current.key,
      });
      onSaved(result.proposal_id);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mt-6">
      <h2 ref={heading} tabIndex={-1} className="mb-2 scroll-mt-24 text-xl font-bold">
        Revisar material {row.observation.material_code}
      </h2>
      <p className="mb-5 text-sm text-muted">
        Os valores extraídos são sugestões. Confira cada valor na fonte antes de encaminhar. Campos
        condicionais são validados pelo PDM ao enviar.
      </p>
      <CompletenessDiagnostics completeness={row.observation.completeness} />
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
        <Field label="Classe PDM">
          <Select
            required
            value={classId}
            disabled={busy}
            onChange={(e) => {
              const next = catalog.classes.find((c) => c.id === e.target.value);
              setClassId(e.target.value);
              setItem(next?.item_names.length === 1 ? next.item_names[0] : "");
              setAttrs({});
              setFactor("");
            }}
          >
            <option value="">Selecione a classe</option>
            {catalog.classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id} · {c.item_names.join(" / ")}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Nome do item">
          <Select
            required
            value={item}
            disabled={busy || !cls}
            onChange={(e) => setItem(e.target.value)}
          >
            <option value="">Selecione o item</option>
            {cls?.item_names.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </Select>
        </Field>
        {cls?.attributes.map((attr) => (
          <Field
            key={attr.name}
            label={attr.name}
            hint={`${attr.required ? "Obrigatório quando aplicável. " : ""}${attr.format}`}
          >
            {attr.allowed_values.length ? (
              <Select
                disabled={busy}
                value={attrs[attr.name] ?? ""}
                onChange={(e) => setAttrs({ ...attrs, [attr.name]: e.target.value })}
              >
                <option value="">Não informado / não aplicável</option>
                {attr.allowed_values.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </Select>
            ) : (
              <Input
                disabled={busy}
                maxLength={2000}
                value={attrs[attr.name] ?? ""}
                onChange={(e) => setAttrs({ ...attrs, [attr.name]: e.target.value })}
              />
            )}
          </Field>
        ))}
        <Field label="Unidade da classe">
          <Input readOnly value={cls?.unit ?? ""} />
        </Field>
        <Field label="NCM" hint="Alterar NCM ou sua base técnica exige também revisão fiscal.">
          <Select value={ncm} disabled={busy || !cls} onChange={(e) => setNcm(e.target.value)}>
            <option value="">Não informado</option>
            {ncm && !cls?.ncm_codes.includes(ncm) && (
              <option value={ncm}>{ncm} (original; conferir)</option>
            )}
            {cls?.ncm_codes.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </Select>
        </Field>
        {needsConversion && (
          <>
            <Field
              label={`Fator de ${row.observation.unit || "unidade ausente"} para ${cls.unit}`}
              hint="Quantidade na unidade de destino por unidade original. Não estime o fator."
            >
              <Input
                required
                value={factor}
                disabled={busy}
                inputMode="decimal"
                pattern="[0-9]+(\.[0-9]+)?"
                onChange={(e) => setFactor(e.target.value)}
              />
            </Field>
            <Field label="Fonte do fator de conversão">
              <Input
                required
                maxLength={2000}
                value={conversionSource}
                disabled={busy}
                onChange={(e) => setConversionSource(e.target.value)}
              />
            </Field>
          </>
        )}
        <Field label="Fonte dos dados conferidos">
          <Textarea
            required
            maxLength={2000}
            rows={3}
            value={source}
            disabled={busy}
            onChange={(e) => setSource(e.target.value)}
            placeholder="Documento, referência e trecho que sustentam os valores."
          />
        </Field>
        <Field label="Justificativa do encaminhamento">
          <Textarea
            required
            maxLength={2000}
            rows={3}
            value={justification}
            disabled={busy}
            onChange={(e) => setJustification(e.target.value)}
          />
        </Field>
        {error && (
          <p role="alert" className="text-alerta md:col-span-2">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3 md:col-span-2">
          <Button type="submit" disabled={busy || !cls}>
            {busy ? "Encaminhando…" : "Criar proposta para aprovação"}
          </Button>
          <Button type="button" variant="ghost" disabled={busy} onClick={onClose}>
            Fechar revisão
          </Button>
        </div>
      </form>
    </Card>
  );
}
