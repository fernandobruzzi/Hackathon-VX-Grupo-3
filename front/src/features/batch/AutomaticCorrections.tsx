"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { automaticReasonLabel, automaticStatusLabel } from "@/lib/automatic-corrections";
import { Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import type { components } from "@/types/api.generated";

type Report = components["schemas"]["AutomaticCorrectionReport"];
const countLabels: Record<string, string> = {
  evaluated: "Avaliadas",
  eligible: "Elegíveis",
  applied: "Aplicadas pelo sistema",
  review: "Revisão humana",
  stale: "Desatualizadas",
  errors: "Erros",
  index_pending: "Busca pendente",
};
export function AutomaticCorrections({ jobId }: { jobId: string }) {
  const { api, sessionRevision } = useAuth();
  const revision = useRef(sessionRevision);
  revision.current = sessionRevision;
  const [open, setOpen] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [commandKey, setCommandKey] = useState<string | null>(null);
  useEffect(() => {
    setOpen(false);
    setReport(null);
    setCursor(null);
    setError(null);
    setCommandKey(null);
  }, [jobId, sessionRevision]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const load = () =>
      api
        .request("get", "/api/v1/batch/jobs/{id}/automatic-corrections", {
          params: { id: jobId },
          query: { limit: 20, ...(cursor ? { cursor } : {}) },
          signal: controller.signal,
        })
        .then((value) => {
          if (!controller.signal.aborted) {
            setReport(value);
            setError(null);
          }
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted)
            setError(
              e instanceof ApiError ? e.message : "Não foi possível consultar as correções.",
            );
        });
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [api, jobId, open, cursor, retry]);
  useEffect(() => {
    setBusy(false);
  }, [sessionRevision]);
  return (
    <div className="mt-2 max-w-lg text-xs">
      <Button variant="ghost" size="sm" onClick={() => setOpen((value) => !value)}>
        Correções automáticas
      </Button>
      {open && (
        <div className="space-y-2">
          {error && <p role="alert">{error}</p>}
          {!report && !error && <p role="status">Carregando relatório…</p>}
          {report && (
            <>
              <p>
                {report.mode === "SIMULATE"
                  ? "Simulação: nenhuma alteração aplicada"
                  : report.mode === "APPLY"
                    ? "Aplicação pelo sistema"
                    : "Automação desligada"}{" "}
                · {automaticStatusLabel[report.status]}
              </p>
              {Object.entries(report.counts).map(([key, count]) => (
                <p key={key}>
                  {countLabels[key] ?? key}: {count}
                </p>
              ))}
              {Object.entries(report.reasons).map(([reason, count]) => (
                <p key={reason}>
                  {automaticReasonLabel(reason)}: {count}
                </p>
              ))}
              {report.items.map((item) => (
                <p key={item.id}>
                  <Link className="underline" href={`/saneamento/revisao/?id=${item.proposal_id}`}>
                    Proposta {item.proposal_id.slice(0, 8)}
                  </Link>
                  : {automaticStatusLabel[item.status]} ·{" "}
                  {item.reasons.map(automaticReasonLabel).join("; ")}
                  {item.index_error ? ` · ${item.index_error}` : ""}
                </p>
              ))}
              {cursor && (
                <Button size="sm" variant="ghost" onClick={() => setCursor(null)}>
                  Primeira página
                </Button>
              )}
              {report.next_cursor && (
                <Button size="sm" variant="ghost" onClick={() => setCursor(report.next_cursor)}>
                  Próxima página
                </Button>
              )}
              {(report.counts.errors > 0 || report.counts.index_pending > 0) && (
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={async () => {
                    if (busy) return;
                    const started = revision.current;
                    setBusy(true);
                    setError(null);
                    const key = commandKey ?? crypto.randomUUID();
                    setCommandKey(key);
                    try {
                      await api.request(
                        "post",
                        "/api/v1/batch/jobs/{id}/automatic-corrections/retry",
                        { params: { id: jobId }, body: {}, idempotencyKey: key },
                      );
                      if (started !== revision.current) return;
                      setCommandKey(null);
                      setRetry((v) => v + 1);
                    } catch (e) {
                      if (started !== revision.current) return;
                      setError(
                        e instanceof ApiError
                          ? e.message
                          : "Não foi possível retomar. Tente novamente.",
                      );
                    } finally {
                      if (started === revision.current) setBusy(false);
                    }
                  }}
                >
                  Retomar erros e atualização da busca
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
