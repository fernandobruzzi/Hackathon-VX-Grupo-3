"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, ExternalLink, X } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  Code,
  Eyebrow,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Table,
  Td,
  Th,
  type Tone,
} from "@/components/ui";
import { ProposalStatusBadge, ReviewBadge } from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { enrichment } from "@/mocks/data";
import type { EnrichmentProposal, EvidenceItem } from "@/types/api";

const confTone: Record<EvidenceItem["confidence"], Tone> = {
  ALTA: "success",
  MEDIA: "warning",
  BAIXA: "danger",
};

const confidenceReason: Record<string, string> = {
  MANUFACTURER_DOMAIN: "Domínio do fabricante",
  REVIEWED_DISTRIBUTOR_DOMAIN: "Distribuidor revisado",
  EXACT_PART_NUMBER: "Referência exata",
  EXPLICIT_CATALOG_LABEL: "Atributo explícito no catálogo",
};

export function EvidenceList() {
  const { api, backend } = useAuth();
  const [remote, setRemote] = useState<EnrichmentProposal[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(backend);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .request("get", "/api/v1/enrichment", {
        query: { cursor: cursor ?? undefined },
        signal: controller.signal,
      })
      .then((result) => {
        if (!controller.signal.aborted) {
          setRemote((previous) => (cursor ? [...previous, ...result.items] : result.items));
          setNextCursor(result.next_cursor);
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(
            error instanceof ApiError ? error.message : "Não foi possível consultar as evidências.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, cursor, retry]);
  const rows = backend ? remote : enrichment;
  return (
    <>
      <PageHeader
        n="03"
        eyebrow="Enriquecimento"
        title="Evidências e propostas de enriquecimento"
        description="Cada valor sugerido vem com a fonte, o trecho usado e a confiança. Nada é gravado sem aprovação da Governança PDM."
      />
      {error && (
        <div role="alert" className="mb-4 text-alerta">
          {error} <Button onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
        </div>
      )}
      {loading && (
        <p role="status" className="mb-4 text-muted">
          Consultando evidências…
        </p>
      )}
      {!loading && !error && rows.length === 0 && (
        <EmptyState title="Nenhuma proposta de enriquecimento disponível" />
      )}
      <Table>
        <thead>
          <tr>
            <Th>Código</Th>
            <Th>Descrição atual</Th>
            <Th>Evidências</Th>
            <Th>Divergências</Th>
            <Th>Status</Th>
            <Th />
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.proposal_id} className="hover:bg-ink/60">
              <Td>
                <Code>{e.material_code}</Code>
              </Td>
              <Td className="font-mono text-[13px]">{e.original_description}</Td>
              <Td>
                <Code>{e.evidence.length}</Code>
              </Td>
              <Td>
                {e.evidence.some((x) => x.divergence) ? (
                  <Badge tone="warning">{e.evidence.filter((x) => x.divergence).length}</Badge>
                ) : (
                  <span className="text-muted">—</span>
                )}
              </Td>
              <Td>
                <ProposalStatusBadge value={e.status} />
              </Td>
              <Td>
                <Link
                  href={
                    backend
                      ? `/enriquecimento/revisao/?id=${e.proposal_id}`
                      : `/enriquecimento/${e.proposal_id}/`
                  }
                  className="grid size-9 place-items-center rounded-md hover:bg-ink"
                  aria-label="Revisar"
                >
                  <ArrowRight className="size-4" />
                </Link>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {backend && nextCursor && (
        <Button disabled={loading} onClick={() => setCursor(nextCursor)}>
          Carregar mais
        </Button>
      )}
    </>
  );
}

/** Integração: GET /api/v1/enrichment/{proposal_id} e POST /api/v1/sanitization/{id}/decide (proposta ENRICHMENT). */
export function EvidenceReview({ proposal: initial }: { proposal: EnrichmentProposal }) {
  const { me, api, backend } = useAuth();
  const [proposal, setProposal] = useState(initial);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const operation = useRef<{ signature: string; key: string } | null>(null);
  const status = proposal.status;
  const area =
    status !== "PENDING"
      ? null
      : can(me, "enrichment:decide") &&
          (proposal.technical_review_status ?? "PENDING") === "PENDING"
        ? "TECHNICAL"
        : can(me, "ncm:decide") && proposal.fiscal_review_status === "PENDING"
          ? "FISCAL"
          : null;
  const canDecide = area !== null && (!backend || !!proposal.allowed_actions?.length);
  const decide = async (decision: "APPROVE" | "REJECT") => {
    if (!area || busy) return;
    if (!backend) {
      setProposal((previous) => ({
        ...previous,
        status: decision === "APPROVE" ? "APPLIED" : "REJECTED",
      }));
      return;
    }
    const body = {
      expected_version: proposal.version,
      review_area: area as "TECHNICAL" | "FISCAL",
      decision,
      reason,
    };
    const signature = JSON.stringify(body);
    if (operation.current?.signature !== signature)
      operation.current = { signature, key: crypto.randomUUID() };
    setBusy(true);
    setError(null);
    try {
      const response = await api.request("post", "/api/v1/sanitization/{id}/decide", {
        params: { id: proposal.proposal_id },
        body,
        idempotencyKey: operation.current.key,
      });
      setProposal((previous) => ({
        ...previous,
        version: response.version,
        status: response.status,
        technical_review_status: response.technical_review_status,
        fiscal_review_status: response.fiscal_review_status,
        allowed_actions: [],
      }));
      operation.current = null;
      setReason("");
      try {
        setProposal(
          await api.request("get", "/api/v1/enrichment/{proposal_id}", {
            params: { proposal_id: proposal.proposal_id },
          }),
        );
      } catch {
        setError("Decisão registrada. Recarregue a página para consultar o estado atualizado.");
      }
    } catch (error: unknown) {
      setError(
        error instanceof ApiError
          ? error.message
          : "Não foi possível confirmar a decisão. Você pode tentar novamente.",
      );
      if (error instanceof ApiError && error.status === 409) {
        try {
          setProposal(
            await api.request("get", "/api/v1/enrichment/{proposal_id}", {
              params: { proposal_id: proposal.proposal_id },
            }),
          );
        } catch {}
      }
    } finally {
      setBusy(false);
    }
  };
  if (backend && !/^[0-9a-f-]{36}$/i.test(proposal.proposal_id))
    return (
      <EmptyState title="Proposta indisponível">
        <Link href="/enriquecimento/">Consultar a fila de evidências</Link>
      </EmptyState>
    );
  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/enriquecimento/"
        className="inline-flex items-center gap-2 self-start text-sm font-semibold text-verde"
      >
        <ArrowLeft className="size-4" /> Voltar
      </Link>
      <div>
        <Eyebrow n="03">Revisão de evidências</Eyebrow>
        <h1 className="mt-4 text-[28px] font-extrabold">
          Material <span className="font-mono font-medium">{proposal.material_code}</span>
        </h1>
      </div>
      <div className="flex gap-3">
        {proposal.technical_review_status && (
          <ReviewBadge value={proposal.technical_review_status} />
        )}
        {proposal.fiscal_review_status && <ReviewBadge value={proposal.fiscal_review_status} />}
      </div>
      {!!proposal.pending_attributes?.length && (
        <p className="text-sm text-aviso">
          Cadastro ainda incompleto: {proposal.pending_attributes.join(", ")}. Esta aprovação inclui
          somente os valores propostos com evidência, sem publicar uma identidade canônica.
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <p className="text-xs font-extrabold tracking-[0.04em] text-muted uppercase">Antes</p>
          <p className="mt-2 font-mono text-[13px]">{proposal.original_description}</p>
        </Card>
        <Card tone="block">
          <p className="text-xs font-extrabold tracking-[0.04em] text-esmeralda uppercase">
            Depois (proposto)
          </p>
          <p className="mt-2 font-mono text-[13px] leading-5">{proposal.proposed_description}</p>
        </Card>
      </div>
      <Table>
        <thead>
          <tr>
            <Th>Atributo</Th>
            <Th>Atual</Th>
            <Th>Proposto</Th>
            <Th>Fonte e trecho</Th>
            <Th>Confiança</Th>
          </tr>
        </thead>
        <tbody>
          {proposal.evidence.map((e, index) => (
            <tr key={`${e.attribute}:${e.source_url}:${index}`}>
              <Td className="font-semibold">{e.attribute}</Td>
              <Td>
                <Code className={e.current_value ? "" : "font-bold text-aviso"}>
                  {e.current_value ?? "ausente"}
                </Code>
              </Td>
              <Td>
                <Code className="text-verde">{e.proposed_value}</Code>
              </Td>
              <Td>
                <a
                  href={e.source_url.startsWith("https://") ? e.source_url : undefined}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm font-semibold text-verde hover:underline"
                >
                  {e.source_title}
                  <ExternalLink className="size-3" />
                </a>
                <blockquote className="mt-1 border-l-2 border-surface-2 pl-2 font-mono text-xs text-muted">
                  “{e.source_excerpt}” {e.source_page && `· ${e.source_page}`}
                </blockquote>
                {e.divergence && (
                  <p className="mt-1 text-xs font-semibold text-aviso">
                    Divergência: {e.divergence}
                  </p>
                )}
                {e.included_in_proposal === false && (
                  <p className="mt-1 text-xs text-muted">Fora desta aprovação.</p>
                )}
                {e.source_sha256 && (
                  <p className="mt-1 truncate font-mono text-xs text-muted" title={e.source_sha256}>
                    Documento: {e.source_sha256.slice(0, 16)}…
                  </p>
                )}
              </Td>
              <Td>
                <Badge tone={confTone[e.confidence]}>{e.confidence.toLowerCase()}</Badge>
                {e.simulated && <Badge tone="warning">Simulada</Badge>}
                <p className="mt-1 text-xs text-muted">
                  {e.confidence_basis
                    ?.flatMap((basis) => (confidenceReason[basis] ? [confidenceReason[basis]] : []))
                    .join(" · ")}
                </p>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {error && (
        <p role="alert" className="text-alerta">
          {error}
        </p>
      )}
      {canDecide && backend && (
        <Field label="Justificativa">
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength={2000}
          />
        </Field>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {canDecide ? (
          <>
            <Button
              variant="danger"
              disabled={
                busy ||
                (backend && (!reason.trim() || !proposal.allowed_actions?.includes("REJECT")))
              }
              onClick={() => void decide("REJECT")}
            >
              <X className="size-4" /> Rejeitar
            </Button>
            <Button
              disabled={
                busy ||
                (backend && (!reason.trim() || !proposal.allowed_actions?.includes("APPROVE")))
              }
              onClick={() => void decide("APPROVE")}
            >
              <Check className="size-4" /> Aprovar valores com fonte
            </Button>
            <p className="text-xs text-muted">
              O valor gravado é o da proposta persistida, não um valor novo digitado aqui.
            </p>
          </>
        ) : (
          <>
            <ProposalStatusBadge value={status} />
            {status === "PENDING" && (
              <span className="text-sm text-muted">
                Aguardando a revisão pendente da Governança ou do Fiscal.
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
