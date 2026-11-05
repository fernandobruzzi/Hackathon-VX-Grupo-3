"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button, EmptyState } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import type { Proposal } from "@/types/api";
import { ProposalReview } from "./ProposalReview";

export function RemoteProposalReview() {
  const { api, backend } = useAuth();
  const id = useSearchParams().get("id");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!id || !backend) return;
    const controller = new AbortController();
    setProposal(null);
    setError(null);
    api
      .request("get", "/api/v1/sanitization/{id}", { params: { id }, signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setProposal(value);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(
            error instanceof ApiError ? error.message : "Não foi possível carregar a proposta.",
          );
      });
    return () => controller.abort();
  }, [api, backend, id, retry]);
  if (!id || !backend)
    return (
      <EmptyState title="Proposta indisponível">
        Informe um identificador e conecte o front à API.
      </EmptyState>
    );
  if (error)
    return (
      <div role="alert" className="text-alerta">
        {error} <Button onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
      </div>
    );
  if (!proposal)
    return (
      <p role="status" className="text-muted">
        Carregando proposta…
      </p>
    );
  return <ProposalReview key={proposal.id} proposal={proposal} />;
}
