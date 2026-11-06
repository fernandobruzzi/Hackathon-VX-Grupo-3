"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Play, RotateCcw } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  Code,
  EmptyState,
  Field,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
  type Tone,
} from "@/components/ui";
import { ApiError, createApiClient } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtInt } from "@/lib/format";
import type { BatchJob } from "@/types/api";

const statusTone: Record<BatchJob["status"], [Tone, string]> = {
  QUEUED: ["neutral", "Na fila"],
  RUNNING: ["info", "Rodando"],
  SUCCEEDED: ["success", "Concluído"],
  FAILED: ["danger", "Falhou"],
};
const typeLabel: Record<BatchJob["job_type"], string> = {
  SANITIZE: "Saneamento",
  IMPORT_ORDERS: "Importar pedidos",
  ENRICH_REAL_PRODUCTS: "Enriquecer produtos reais",
};
// Só o saneamento roda no batch por enquanto; os outros tipos aparecem desabilitados.
const AVAILABLE_TYPES: BatchJob["job_type"][] = ["SANITIZE"];
const POLL_MS = 2000;

const isActive = (job: BatchJob) => job.status === "QUEUED" || job.status === "RUNNING";
const percent = (job: BatchJob) =>
  job.progress.total ? Math.round((job.progress.processed / job.progress.total) * 100) : 0;

function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.error.code === "JOB_ALREADY_RUNNING")
    return "Já existe um job em andamento. Acompanhe-o abaixo.";
  if (error instanceof ApiError && error.status === 403)
    return "Só a Governança PDM inicia e acompanha o batch.";
  if (error instanceof ApiError) return error.message;
  return "Não foi possível falar com o servidor.";
}

function secondsSince(iso: string | null, now: number) {
  return iso ? Math.max(0, Math.round((now - Date.parse(iso)) / 1000)) : null;
}

export function BatchPage() {
  const { me } = useAuth();
  const api = useMemo(() => createApiClient({ getCsrfToken: () => me?.csrf_token ?? null }), [me]);
  const allowed = me?.permissions.includes("batch:run") ?? false;
  const [jobs, setJobs] = useState<BatchJob[]>([]);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [type, setType] = useState<BatchJob["job_type"]>("SANITIZE");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    try {
      const list = await api.request("get", "/api/v1/batch/jobs", { query: { limit: 20 } });
      setJobs(list.items);
      setDatasetId(list.latest_dataset_id);
      setQueryError(null);
    } catch (e) {
      setQueryError(`Não foi possível atualizar os jobs: ${errorMessage(e)}`);
    } finally {
      setLoaded(true);
      setNow(Date.now());
    }
  }, [api]);

  const active = jobs.find(isActive);

  useEffect(() => {
    if (!allowed) return;
    void load();
  }, [allowed, load]);

  // Acompanha o job enquanto ele está na fila ou rodando.
  useEffect(() => {
    if (!allowed || !active) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [allowed, active, load]);

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (e) {
      setActionError(`Não foi possível ${label}: ${errorMessage(e)}`);
    } finally {
      setBusy(false);
      await load();
    }
  };

  const start = () =>
    run("iniciar o job", () =>
      api.request("post", "/api/v1/batch/jobs", {
        body: {
          dataset_id: datasetId ?? "",
          job_type: type,
          pdm_version: "pdm-kit-v1",
          ncm_version: "ncm-demo-v1",
          scope: { pdm_class_ids: [], include_statuses: ["ATIVO", "BLOQUEADO", "OBSOLETO"] },
        },
      }),
    );

  const resume = (job: BatchJob) =>
    run(`reprocessar o job ${job.id.slice(0, 8)}`, () =>
      api.request("post", "/api/v1/batch/jobs/{id}/resume", {
        params: { id: job.id },
        body: {},
      }),
    );

  const heartbeat = active ? secondsSince(active.heartbeat_at, now) : null;

  return (
    <>
      <PageHeader
        n="02"
        eyebrow="Processamento em lote"
        title="Rodar o saneamento na base inteira"
        description="O lote só gera propostas. A aplicação na base mestre sempre passa pela fila de revisão."
      />
      {!allowed ? (
        <EmptyState title="Acesso restrito à Governança PDM">
          Iniciar e reprocessar o batch é uma ação da Governança. Troque para essa persona para
          acompanhar os jobs.
        </EmptyState>
      ) : (
        <>
          <div className="mb-6 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
            <Card className="flex flex-col gap-4">
              <p className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
                Novo job
              </p>
              <Field label="Tipo">
                <Select
                  value={type}
                  onChange={(e) => setType(e.target.value as BatchJob["job_type"])}
                >
                  {Object.entries(typeLabel).map(([k, v]) => (
                    <option
                      key={k}
                      value={k}
                      disabled={!AVAILABLE_TYPES.includes(k as BatchJob["job_type"])}
                    >
                      {AVAILABLE_TYPES.includes(k as BatchJob["job_type"]) ? v : `${v} (em breve)`}
                    </option>
                  ))}
                </Select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Versão PDM">
                  <Code>pdm-kit-v1</Code>
                </Field>
                <Field label="Versão NCM">
                  <Code>ncm-demo-v1</Code>
                </Field>
              </div>
              <Field label="Escopo">
                <p className="text-sm text-muted">
                  Base inteira. Correções só em material ATIVO; unificações seguem as regras de
                  identidade.
                </p>
              </Field>
              <Button
                onClick={start}
                disabled={busy || !!active || !datasetId}
                className="self-start"
              >
                <Play className="size-4" /> Iniciar job
              </Button>
              {!datasetId && loaded && (
                <p className="text-sm text-aviso">Nenhum dataset carregado: rode o bootstrap.</p>
              )}
              {[actionError, queryError].map(
                (message, index) =>
                  message && (
                    <p key={index} role="alert" className="text-sm text-alerta">
                      {message}
                    </p>
                  ),
              )}
            </Card>
            {active ? (
              <Card tone="block" className="flex flex-col gap-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-extrabold tracking-[0.04em] text-esmeralda uppercase">
                    {statusTone[active.status][1]} · {active.id.slice(0, 8)}
                  </span>
                  <Code className="text-on-profundo/80">
                    {heartbeat === null ? "aguardando a task" : `heartbeat há ${heartbeat} s`}
                  </Code>
                </div>
                <p className="text-[40px] leading-none font-extrabold text-esmeralda">
                  {percent(active)}%
                </p>
                <div className="h-2.5 rounded-full bg-apoio">
                  <div
                    className="h-full rounded-full bg-esmeralda transition-[width]"
                    style={{ width: `${percent(active)}%` }}
                  />
                </div>
                <p className="font-mono text-sm">
                  {fmtInt(active.progress.processed)} de {fmtInt(active.progress.total)} materiais
                  analisados
                </p>
                <div className="grid grid-cols-4 gap-3 border-t border-white/15 pt-4 text-sm">
                  {[
                    ["propostas", active.counts.proposals],
                    ["unificações", active.counts.merges],
                    ["NCM", active.counts.ncm],
                    ["enriquec.", active.counts.enrichment],
                  ].map(([l, v]) => (
                    <div key={l as string}>
                      <p className="text-xl font-extrabold">{fmtInt(v as number)}</p>
                      <p className="text-xs text-on-profundo/75">{l}</p>
                    </div>
                  ))}
                </div>
              </Card>
            ) : (
              <Card className="flex flex-col justify-center gap-2 text-sm leading-6 text-muted">
                <p className="font-bold text-text">Nenhum job em andamento.</p>
                <p>
                  Um job parado ou sem sinal de vida é marcado como falho e pode ser reprocessado:
                  ele continua do último checkpoint, sem duplicar propostas.
                </p>
              </Card>
            )}
          </div>
          {loaded && jobs.length === 0 ? (
            <EmptyState title="Nenhum job ainda">
              Inicie o saneamento para gerar as propostas da base inteira.
            </EmptyState>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Job</Th>
                  <Th>Tipo</Th>
                  <Th>Status</Th>
                  <Th>Progresso</Th>
                  <Th>Propostas</Th>
                  <Th>Início</Th>
                  <Th>Ação</Th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <Td>
                      <Code>{j.id.slice(0, 8)}</Code>
                      <p className="text-xs text-muted">{j.requested_by}</p>
                    </Td>
                    <Td>{typeLabel[j.job_type]}</Td>
                    <Td>
                      <Badge tone={statusTone[j.status][0]}>{statusTone[j.status][1]}</Badge>
                      {j.error && (
                        <p className="mt-1 max-w-xs text-xs text-alerta">
                          <Code>{j.error.code}</Code> {j.error.message}
                        </p>
                      )}
                    </Td>
                    <Td>
                      <Code>
                        {fmtInt(j.progress.processed)}/{fmtInt(j.progress.total)}
                      </Code>
                    </Td>
                    <Td>
                      <Code>{fmtInt(j.counts.proposals)}</Code>
                    </Td>
                    <Td>
                      <Code className="text-muted">
                        {j.started_at ? fmtDate(j.started_at) : "—"}
                      </Code>
                    </Td>
                    <Td>
                      {j.status === "SUCCEEDED" && (
                        <Link href={`/pendencias/?run_id=${j.id}`} className="text-verde underline">
                          Ver pendências
                        </Link>
                      )}
                      {j.status === "FAILED" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => resume(j)}
                          disabled={busy || !!active}
                        >
                          <RotateCcw className="size-4" /> Reprocessar
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </>
      )}
    </>
  );
}
