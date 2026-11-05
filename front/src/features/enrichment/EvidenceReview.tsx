"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, ExternalLink, X } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  Code,
  Eyebrow,
  PageHeader,
  Table,
  Td,
  Th,
  type Tone,
} from "@/components/ui";
import { ProposalStatusBadge } from "@/components/ui/status";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { enrichment } from "@/mocks/data";
import type { EnrichmentProposal, EvidenceItem } from "@/types/api";

const confTone: Record<EvidenceItem["confidence"], Tone> = {
  ALTA: "success",
  MEDIA: "warning",
  BAIXA: "danger",
};

export function EvidenceList() {
  return (
    <>
      <PageHeader
        n="03"
        eyebrow="Enriquecimento"
        title="Dados novos esperando conferência"
        description="Cada valor sugerido vem com a fonte, o trecho usado e a confiança. Nada é gravado sem aprovação da Governança PDM."
      />
      <Table>
        <thead>
          <tr>
            <Th>Código</Th>
            <Th>Descrição atual</Th>
            <Th>Atributos novos</Th>
            <Th>Divergências</Th>
            <Th>Status</Th>
            <Th />
          </tr>
        </thead>
        <tbody>
          {enrichment.map((e) => (
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
                  href={`/enriquecimento/${e.proposal_id}/`}
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
    </>
  );
}

/** Integração: GET /api/v1/enrichment/{proposal_id} e POST /api/v1/sanitization/{id}/decide (proposta ENRICHMENT). */
export function EvidenceReview({ proposal }: { proposal: EnrichmentProposal }) {
  const { me } = useAuth();
  const [status, setStatus] = useState(proposal.status);
  const canDecide = can(me, "enrichment:decide") && status === "PENDING";
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
          {proposal.evidence.map((e) => (
            <tr key={e.attribute}>
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
                  href={e.source_url}
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
              </Td>
              <Td>
                <Badge tone={confTone[e.confidence]}>{e.confidence.toLowerCase()}</Badge>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <div className="flex flex-wrap items-center gap-3">
        {canDecide ? (
          <>
            <Button variant="danger" onClick={() => setStatus("REJECTED")}>
              <X className="size-4" /> Rejeitar
            </Button>
            <Button onClick={() => setStatus("APPLIED")}>
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
                Somente a Governança PDM aprova enriquecimento.
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
