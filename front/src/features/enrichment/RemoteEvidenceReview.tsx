"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button, EmptyState } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import type { EnrichmentProposal } from "@/types/api";
import { EvidenceReview } from "./EvidenceReview";

export function RemoteEvidenceReview() {
  const { api, backend } = useAuth();
  const id = useSearchParams().get("id");
  const [proposal, setProposal] = useState<EnrichmentProposal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!id || !backend) return;
    const controller = new AbortController();
    setProposal(null);
    setError(null);
    api
      .request("get", "/api/v1/enrichment/{proposal_id}", {
        params: { proposal_id: id },
        signal: controller.signal,
      })
      .then((value) => {
        if (!controller.signal.aborted) setProposal(value);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(
            error instanceof ApiError ? error.message : "Não foi possível consultar a proposta.",
          );
      });
    return () => controller.abort();
  }, [api, backend, id, retry]);
  if (!id || !backend) return <EmptyState title="Proposta indisponível" />;
  if (error)
    return (
      <div role="alert" className="text-alerta">
        {error} <Button onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
      </div>
    );
  if (!proposal)
    return (
      <p role="status" className="text-muted">
        Consultando evidências…
      </p>
    );
  return <EvidenceReview key={proposal.proposal_id} proposal={proposal} />;
}
