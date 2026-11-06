"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Code,
  EmptyState,
  Field,
  PageHeader,
  Textarea,
} from "@/components/ui";
import { proposalTypeLabel } from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtInt } from "@/lib/format";
import type { components } from "@/types/api.generated";
import { tierLabel } from "./LotsPage";

type Review = components["schemas"]["LotReview"];
type Verdict = "CORRECT" | "WRONG";
type Decision = components["schemas"]["LotDecisionResponse"];

const outcomeLabel = { APPLIED: "aplicadas", STALE: "desatualizadas", SKIPPED: "não aplicadas" };

/** Revisão da amostra de um lote (#120): a amostra vem sorteada do servidor e é igual a cada leitura. */
export function LotReviewPage() {
  const { api, backend } = useAuth();
  const id = useSearchParams().get("id");
  const [review, setReview] = useState<Review | null>(null);
  const [marks, setMarks] = useState<Record<string, Verdict>>({});
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [retry, setRetry] = useState(0);
  const key = useRef<string | null>(null);

  useEffect(() => {
    if (!id || !backend) return;
    const controller = new AbortController();
    setReview(null);
    setError(null);
    api
      .request("get", "/api/v1/sanitization/lots/reviews/{id}", {
        params: { id },
        signal: controller.signal,
      })
      .then((value) => {
        if (controller.signal.aborted) return;
        setReview(value);
        setMarks(value.marks as Record<string, Verdict>);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof ApiError ? reason.message : "Não foi possível carregar o lote.",
          );
      });
    return () => controller.abort();
  }, [api, backend, id, retry]);

  if (!id || !backend)
    return (
      <EmptyState title="Lote indisponível">
        Abra a revisão a partir da lista de lotes, com o front conectado à API.
      </EmptyState>
    );
  if (error && !review)
    return (
      <div role="alert" className="text-alerta">
        {error} <Button onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
      </div>
    );
  if (!review)
    return (
      <p role="status" className="text-muted">
        Carregando amostra…
      </p>
    );

  const marked = review.sample.filter((item) => marks[item.proposal_id]).length;
  const complete = marked === review.sample.length;
  const wrong = review.sample.filter((item) => marks[item.proposal_id] === "WRONG").length;
  const open = review.status === "OPEN" && !decision;

  async function submit() {
    if (!review) return;
    key.current ??= crypto.randomUUID();
    setSaving(true);
    setError(null);
    try {
      const result = await api.request("post", "/api/v1/sanitization/lots/reviews/{id}/decide", {
        params: { id: review.id },
        body: {
          expected_version: review.version,
          marks: review.sample.map((item) => ({
            proposal_id: item.proposal_id,
            verdict: marks[item.proposal_id],
          })),
          reason,
        },
        idempotencyKey: key.current,
      });
      setDecision(result);
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "Não foi possível registrar a decisão.",
      );
      if (reason instanceof ApiError && reason.status !== 503) key.current = null;
    } finally {
      setSaving(false);
    }
  }

  const status = decision?.status ?? review.status;
  const result = decision?.result ?? review.result;
  return (
    <>
      <PageHeader
        n="02"
        eyebrow="Revisão por amostra"
        title={`${proposalTypeLabel[review.proposal_type]}${review.pdm_class_name ? ` · ${review.pdm_class_name}` : ""}`}
        description={`Confira cada item da amostra. Com zero erros, as ${fmtInt(review.size)} propostas do lote são aplicadas uma a uma, cada uma com auditoria própria. Com qualquer erro, nada é aplicado e o lote volta para a revisão individual.`}
        actions={
          <Link href="/saneamento/lotes/" className="text-sm font-semibold hover:text-verde">
            Voltar aos lotes
          </Link>
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Badge tone={review.tier === 1 ? "success" : "info"}>{tierLabel[review.tier]}</Badge>
        <Code className="text-xs">{review.rule}</Code>
        <span className="text-sm text-muted">
          Amostra de {review.sample.length} de {fmtInt(review.size)} propostas
        </span>
      </div>

      {status !== "OPEN" && result && (
        <Card tone="block" className="mb-6" role="status">
          {status === "APPROVED" && result.counts ? (
            <p className="text-lg font-bold">
              Lote aprovado:{" "}
              {(Object.keys(outcomeLabel) as (keyof typeof outcomeLabel)[])
                .map((k) => `${fmtInt(result.counts?.[k] ?? 0)} ${outcomeLabel[k]}`)
                .join(" · ")}
            </p>
          ) : (
            <p className="text-lg font-bold">
              Lote devolvido para a revisão individual: {result.wrong_ids?.length ?? 0} item(ns)
              errado(s) na amostra. Regra registrada: {result.rule}.
            </p>
          )}
          <Link href="/saneamento/" className="mt-2 inline-block text-sm font-semibold underline">
            Ir para a fila individual
          </Link>
        </Card>
      )}

      <ol className="mb-6 flex flex-col gap-3">
        {review.sample.map((item, index) => {
          const verdict = marks[item.proposal_id];
          return (
            <li key={item.proposal_id}>
              <Card className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-muted">
                    {index + 1}/{review.sample.length} · material{" "}
                    <Code>{item.material_code ?? "—"}</Code>
                  </p>
                  <p className="mt-1 text-sm">
                    {item.original_description ?? "Sem descrição original"}
                  </p>
                  <ul className="mt-2 flex flex-col gap-1 text-sm">
                    {item.changes.map((change) => (
                      <li key={change.field}>
                        <span className="font-semibold">{change.field}</span>:{" "}
                        <Code>{change.before ?? "—"}</Code> → <Code>{change.after}</Code>
                      </li>
                    ))}
                  </ul>
                  {item.proposed_description && (
                    <p className="mt-2 text-sm">
                      Descrição proposta: <Code>{item.proposed_description}</Code>
                    </p>
                  )}
                </div>
                <div
                  role="radiogroup"
                  aria-label={`Item ${index + 1} da amostra`}
                  className="flex gap-2"
                >
                  {(["CORRECT", "WRONG"] as const).map((value) => (
                    <Button
                      key={value}
                      size="sm"
                      role="radio"
                      aria-checked={verdict === value}
                      disabled={!open || saving}
                      variant={
                        verdict === value ? (value === "CORRECT" ? "primary" : "danger") : "ghost"
                      }
                      onClick={() =>
                        setMarks((previous) => ({ ...previous, [item.proposal_id]: value }))
                      }
                    >
                      {value === "CORRECT" ? "Correto" : "Errado"}
                    </Button>
                  ))}
                </div>
              </Card>
            </li>
          );
        })}
      </ol>

      {open && (
        <Card className="flex flex-col gap-4">
          <Field label="Justificativa" hint="Fica registrada na auditoria do lote e de cada item.">
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
          </Field>
          {error && (
            <p role="alert" className="text-sm text-alerta">
              {error}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant={wrong ? "danger" : "primary"}
              disabled={!complete || !reason.trim() || saving}
              onClick={submit}
            >
              {saving
                ? "Registrando…"
                : wrong
                  ? "Devolver lote para revisão individual"
                  : `Aprovar lote (${fmtInt(review.size)} propostas)`}
            </Button>
            <span className="text-sm text-muted">
              {marked}/{review.sample.length} itens marcados
              {wrong ? ` · ${wrong} errado(s)` : ""}
            </span>
          </div>
        </Card>
      )}
    </>
  );
}
