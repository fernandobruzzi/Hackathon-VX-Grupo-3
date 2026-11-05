"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { Badge, Button, Card, Code, Field, PageHeader, Select, Table, Td, Th, type Tone } from "@/components/ui";
import { fmtDate, fmtInt } from "@/lib/format";
import { batchJobs } from "@/mocks/data";
import type { BatchJob } from "@/types/api";

const statusTone: Record<BatchJob["status"], [Tone, string]> = { QUEUED: ["neutral", "Na fila"], RUNNING: ["info", "Rodando"], SUCCEEDED: ["success", "Concluído"], FAILED: ["danger", "Falhou"] };
const typeLabel: Record<BatchJob["job_type"], string> = { SANITIZE: "Saneamento", IMPORT_ORDERS: "Importar pedidos", ENRICH_REAL_PRODUCTS: "Enriquecer produtos reais" };

/** Integração: POST /api/v1/batch/jobs (202 + job_id) e GET /api/v1/batch/jobs/{id} (progresso, heartbeat). */
export function BatchPage() {
  const [jobs, setJobs] = useState(batchJobs);
  const [type, setType] = useState<BatchJob["job_type"]>("SANITIZE");
  const running = jobs.find((j) => j.status === "RUNNING");

  const start = () => setJobs((js) => [{
    id: `job-00${js.length + 4}`, job_type: type, status: "QUEUED", requested_by: "Fernanda · Cadastro", pdm_version: "pdm-kit-v1", ncm_version: "ncm-demo-v1",
    progress: { processed: 0, total: type === "IMPORT_ORDERS" ? 520 : type === "ENRICH_REAL_PRODUCTS" ? 15 : 23554 }, counts: { proposals: 0, merges: 0, ncm: 0, enrichment: 0 },
    started_at: new Date().toISOString(), finished_at: null,
  }, ...js]);

  return (
    <>
      <PageHeader n="02" eyebrow="Processamento em lote" title="Rodar o saneamento na base inteira" description="O lote só gera propostas. A aplicação na base mestre sempre passa pela fila de revisão." />
      <div className="mb-6 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <Card className="flex flex-col gap-4">
          <p className="text-xs font-extrabold uppercase tracking-[0.04em] text-verde">Novo job</p>
          <Field label="Tipo"><Select value={type} onChange={(e) => setType(e.target.value as BatchJob["job_type"])}>{Object.entries(typeLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Versão PDM"><Select><option>pdm-kit-v1</option></Select></Field>
            <Field label="Versão NCM"><Select><option>ncm-demo-v1</option></Select></Field>
          </div>
          <Field label="Escopo" hint="Vazio = todas as 44 classes PDM."><Select><option>Todas as classes · ATIVO, BLOQUEADO, OBSOLETO</option></Select></Field>
          <Button onClick={start} className="self-start"><Play className="size-4" /> Iniciar job</Button>
        </Card>
        {running && (
          <Card tone="block" className="flex flex-col gap-4">
            <div className="flex items-center justify-between"><span className="text-xs font-extrabold uppercase tracking-[0.04em] text-esmeralda">Em execução · {running.id}</span><Code className="text-on-profundo/80">heartbeat há 8 s</Code></div>
            <p className="text-[40px] font-extrabold leading-none text-esmeralda">{Math.round((running.progress.processed / running.progress.total) * 100)}%</p>
            <div className="h-2.5 rounded-full bg-apoio"><div className="h-full rounded-full bg-esmeralda" style={{ width: `${(running.progress.processed / running.progress.total) * 100}%` }} /></div>
            <p className="font-mono text-sm">{fmtInt(running.progress.processed)} de {fmtInt(running.progress.total)} materiais</p>
            <div className="grid grid-cols-4 gap-3 border-t border-white/15 pt-4 text-sm">
              {[["propostas", running.counts.proposals], ["unificações", running.counts.merges], ["NCM", running.counts.ncm], ["enriquec.", running.counts.enrichment]].map(([l, v]) => (
                <div key={l as string}><p className="text-xl font-extrabold">{fmtInt(v as number)}</p><p className="text-xs text-on-profundo/75">{l}</p></div>
              ))}
            </div>
          </Card>
        )}
      </div>
      <Table>
        <thead><tr><Th>Job</Th><Th>Tipo</Th><Th>Status</Th><Th>Progresso</Th><Th>Propostas</Th><Th>Versões</Th><Th>Início</Th></tr></thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <Td><Code>{j.id}</Code><p className="text-xs text-muted">{j.requested_by}</p></Td>
              <Td>{typeLabel[j.job_type]}</Td>
              <Td><Badge tone={statusTone[j.status][0]}>{statusTone[j.status][1]}</Badge></Td>
              <Td><Code>{fmtInt(j.progress.processed)}/{fmtInt(j.progress.total)}</Code></Td>
              <Td><Code>{fmtInt(j.counts.proposals)}</Code></Td>
              <Td><Code className="text-muted">{j.pdm_version} · {j.ncm_version}</Code></Td>
              <Td><Code className="text-muted">{fmtDate(j.started_at)}</Code></Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </>
  );
}
