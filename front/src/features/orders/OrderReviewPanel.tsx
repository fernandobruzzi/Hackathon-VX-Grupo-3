"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Code, Field, Input, Select, Textarea } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { components } from "@/types/api.generated";

type Review = components["schemas"]["OrderReview"];
export function OrderReviewPanel({
  id,
  onClose,
  onDecided,
}: {
  id: string;
  onClose: () => void;
  onDecided: () => void;
}) {
  const { api, me } = useAuth();
  const [detail, setDetail] = useState<Review | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [ncm, setNcm] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const attempts = useRef(new Map<string, string>());
  useEffect(() => {
    const request = new AbortController();
    controller.current = request;
    setDetail(null);
    setError(null);
    api
      .request("get", "/api/v1/registration-orders/{id}", {
        params: { id },
        signal: request.signal,
      })
      .then((value) => {
        if (!request.signal.aborted) {
          setDetail(value);
          setNcm(value.ncm_proposed ?? "");
        }
      })
      .catch((err: unknown) => {
        if (!request.signal.aborted)
          setError(err instanceof ApiError ? err.message : "Não foi possível consultar a ficha.");
      });
    return () => request.abort();
  }, [api, id, me, retry]);
  const identityReview = detail?.order.missing_attributes.some((reason) =>
    reason.startsWith("REVISAO DE IDENTIDADE:"),
  );
  const technical = detail?.order.status === "READY_FOR_REVIEW" && can(me, "orders:decide");
  const fiscal = detail?.order.status === "PENDING_FISCAL" && can(me, "ncm:decide");
  const canReopen = detail?.order.status === "PENDING_FISCAL" && can(me, "orders:decide");
  const decide = async (decision: "APPROVE" | "REJECT") => {
    if (!detail || !controller.current) return;
    const signal = controller.current.signal;
    const body = {
      expected_version: detail.order.version,
      decision,
      reason,
      ...(fiscal && decision === "APPROVE"
        ? {
            ncm_code: ncm,
            ncm_source: source,
            ncm_evaluation_hash: detail.ncm_assessment.evaluation_hash,
          }
        : {}),
    };
    const fingerprint = JSON.stringify({ id, ...body });
    const key = attempts.current.get(fingerprint) ?? crypto.randomUUID();
    attempts.current.set(fingerprint, key);
    setBusy(true);
    setError(null);
    try {
      await api.request("post", "/api/v1/registration-orders/{id}/decide", {
        params: { id },
        body,
        idempotencyKey: key,
      });
      if (!signal.aborted) onDecided();
    } catch (err) {
      if (!signal.aborted)
        setError(err instanceof ApiError ? err.message : "Não foi possível registrar a decisão.");
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  };
  const reopen = async () => {
    if (!detail || !controller.current) return;
    const signal = controller.current.signal;
    const body = { expected_version: detail.order.version, reason };
    const fingerprint = JSON.stringify({ id, operation: "reopen", ...body });
    const key = attempts.current.get(fingerprint) ?? crypto.randomUUID();
    attempts.current.set(fingerprint, key);
    setBusy(true);
    setError(null);
    try {
      await api.request("post", "/api/v1/registration-orders/{id}/reopen-technical-review", {
        params: { id },
        body,
        idempotencyKey: key,
      });
      if (!signal.aborted) onDecided();
    } catch (err) {
      if (!signal.aborted)
        setError(err instanceof ApiError ? err.message : "Não foi possível reavaliar o pedido.");
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  };
  return (
    <section className="my-4 rounded-md bg-surface-2 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-bold">Revisão do pedido {id.slice(0, 8)}</h2>
        <Button variant="ghost" disabled={busy} onClick={onClose}>
          Fechar revisão
        </Button>
      </div>
      {error && (
        <p role="alert" className="mb-3 text-alerta">
          {error}{" "}
          {!detail && (
            <Button size="sm" onClick={() => setRetry((value) => value + 1)}>
              Tentar novamente
            </Button>
          )}
        </p>
      )}
      {!detail && !error && <p role="status">Carregando ficha…</p>}
      {detail && (
        <div className="grid gap-4">
          <div>
            <h3 className="font-semibold">Texto original</h3>
            <p>{detail.order.original_text}</p>
          </div>
          <div>
            <h3 className="font-semibold">Anexo original</h3>
            <p>{detail.attachment_text || "Sem anexo"}</p>
          </div>
          <p>
            Classe: <Code>{detail.order.pdm_class_id ?? "Sem classe"}</Code> · Item:{" "}
            {detail.item_name ?? "Não definido"} · Versão do pedido: {detail.order.version}
          </p>
          <div>
            <h3 className="font-semibold">Atributos da ficha</h3>
            <dl>
              {Object.entries(detail.attributes).map(([name, value]) => (
                <div key={name} className="flex gap-2 text-sm">
                  <dt className="font-semibold">{name}:</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <h3 className="font-semibold">Descrição proposta</h3>
            <p>{detail.formatted_description ?? "Ficha incompleta"}</p>
          </div>
          <p>
            Duplicidade:{" "}
            {detail.candidate_material_ids.length
              ? detail.candidate_material_ids.join(", ")
              : "Nenhuma identidade existente encontrada nas regras atuais."}
          </p>
          <div>
            <h3 className="font-semibold">Referências NCM do PDM</h3>
            <ul>
              {detail.ncm_references.map((ref, i) => (
                <li key={i}>
                  {ref.codes.join(", ")} · {ref.condition}
                </li>
              ))}
            </ul>
            <p>NCM proposto: {detail.ncm_proposed ?? "Escolha fiscal explícita necessária"}</p>
            <p className="text-sm text-aviso">
              Existência e vigência oficial desconhecidas: snapshot oficial indisponível. Coerência
              com o PDM não confirma vigência.
            </p>
          </div>
          <details>
            <summary>Versões da avaliação</summary>
            <p className="text-sm break-all">
              PDM {detail.pdm_version} · SHA256 {detail.pdm_source_sha256} · Índice{" "}
              {detail.index_version} · Avaliação fiscal {detail.ncm_assessment.evaluation_hash}
            </p>
          </details>
          {detail.fiscal_decision && (
            <div>
              <h3 className="font-semibold">Decisão fiscal registrada</h3>
              <p>
                NCM {detail.fiscal_decision.ncm_code} · Fonte: {detail.fiscal_decision.source}
              </p>
              <p>Justificativa: {detail.fiscal_decision.reason}</p>
            </div>
          )}
          {identityReview && (
            <p role="alert" className="text-aviso">
              A identidade exige revisão técnica das evidências antes da aprovação.
            </p>
          )}
          {fiscal && !detail.technical_review_current && (
            <p role="alert" className="text-aviso">
              A ficha ou as regras mudaram após a aprovação técnica. É necessária nova revisão antes
              de publicar.
            </p>
          )}
          {fiscal && (
            <>
              <Field label="NCM a publicar">
                <Select value={ncm} onChange={(event) => setNcm(event.target.value)}>
                  <option value="">Selecione após conferir as condições</option>
                  {detail.ncm_assessment.suggested_ncm_codes.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Fonte da decisão fiscal">
                <Input
                  value={source}
                  maxLength={1000}
                  onChange={(event) => setSource(event.target.value)}
                />
              </Field>
            </>
          )}
          {(technical || fiscal || canReopen) && (
            <>
              <Field label="Justificativa da decisão">
                <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
              </Field>
              <div className="flex gap-2">
                {canReopen && (
                  <Button disabled={busy || !reason.trim()} onClick={reopen}>
                    Reavaliar e devolver à revisão técnica
                  </Button>
                )}
                {(technical || fiscal) && (
                  <>
                    <Button
                      disabled={
                        busy ||
                        !reason.trim() ||
                        identityReview ||
                        (fiscal && (!ncm || !source.trim() || !detail.technical_review_current))
                      }
                      onClick={() => decide("APPROVE")}
                    >
                      {fiscal ? "Aprovar NCM e publicar" : "Aprovar parte técnica"}
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={busy || !reason.trim()}
                      onClick={() => decide("REJECT")}
                    >
                      Rejeitar pedido
                    </Button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
