"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Badge, Button, Code, EmptyState, PageHeader, Table, Td, Th } from "@/components/ui";
import { proposalTypeLabel } from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtInt } from "@/lib/format";
import type { components } from "@/types/api.generated";

type Lot = components["schemas"]["LotSummary"];

export const tierLabel: Record<number, string> = {
  1: "Nível 1 · grafia de unidade",
  2: "Nível 2 · descrição e grupo",
};

/** Lotes de correções de forma (#120): a Governança aprova depois de revisar uma amostra. */
export function LotsPage() {
  const { api, backend } = useAuth();
  const router = useRouter();
  const [lots, setLots] = useState<Lot[]>([]);
  const [minSize, setMinSize] = useState(20);
  const [loading, setLoading] = useState(backend);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const keys = useRef(new Map<string, string>());

  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .request("get", "/api/v1/sanitization/lots", { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        setLots(result.items);
        setMinSize(result.min_lot_size);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof ApiError ? reason.message : "Não foi possível carregar os lotes.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, retry]);

  async function open(lot: Lot) {
    const id = `${lot.tier}:${lot.lot_key}`;
    if (!keys.current.has(id)) keys.current.set(id, crypto.randomUUID());
    setOpening(id);
    setError(null);
    try {
      const review = await api.request("post", "/api/v1/sanitization/lots/reviews", {
        body: { lot_key: lot.lot_key, tier: lot.tier },
        idempotencyKey: keys.current.get(id),
      });
      router.push(`/saneamento/lotes/revisao/?id=${encodeURIComponent(review.id)}`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Não foi possível abrir a revisão.");
      setOpening(null);
    }
  }

  return (
    <>
      <PageHeader
        n="02"
        eyebrow="Saneamento em lote"
        title="Correções de forma aprovadas por amostra"
        description={`Nada entra no cadastro sem uma pessoa aprovar. Lotes com ${minSize} ou mais correções do mesmo tipo, regra e classe são aprovados depois de revisar uma amostra sorteada; com qualquer erro, o lote volta para a revisão item a item. Unificação e NCM nunca entram em lote.`}
        actions={
          <Link href="/saneamento/" className="text-sm font-semibold hover:text-verde">
            Voltar à fila
          </Link>
        }
      />
      {loading && (
        <p role="status" className="mb-4 text-sm text-muted">
          Carregando lotes…
        </p>
      )}
      {error && (
        <div role="alert" className="mb-4 text-alerta">
          {error}{" "}
          <Button variant="ghost" onClick={() => setRetry((value) => value + 1)}>
            Tentar novamente
          </Button>
        </div>
      )}
      {!backend ? (
        <EmptyState title="Lotes indisponíveis">
          Conecte o front à API para ver os lotes.
        </EmptyState>
      ) : !loading && !error && lots.length === 0 ? (
        <EmptyState title="Nenhum lote elegível">
          Não há {minSize} ou mais correções pendentes do mesmo tipo, regra e classe. As demais
          seguem na fila individual.
        </EmptyState>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Lote</Th>
              <Th>Nível</Th>
              <Th className="text-right">Propostas</Th>
              <Th className="text-right">Amostra</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {lots.map((lot) => {
              const id = `${lot.tier}:${lot.lot_key}`;
              return (
                <tr key={id} className="hover:bg-ink/60">
                  <Td>
                    <p className="font-semibold">
                      {proposalTypeLabel[lot.proposal_type]}
                      {lot.pdm_class_name ? ` · ${lot.pdm_class_name}` : ""}
                    </p>
                    <Code className="mt-1 text-xs">{lot.rule}</Code>
                  </Td>
                  <Td>
                    <Badge tone={lot.tier === 1 ? "success" : "info"}>{tierLabel[lot.tier]}</Badge>
                  </Td>
                  <Td className="text-right">
                    <Code>{fmtInt(lot.size)}</Code>
                  </Td>
                  <Td className="text-right">
                    <Code>{fmtInt(lot.sample_size)}</Code>
                  </Td>
                  <Td className="text-right">
                    <Button size="sm" disabled={opening !== null} onClick={() => open(lot)}>
                      {opening === id
                        ? "Abrindo…"
                        : lot.open_review_id
                          ? "Continuar revisão"
                          : "Revisar amostra"}
                    </Button>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </>
  );
}
