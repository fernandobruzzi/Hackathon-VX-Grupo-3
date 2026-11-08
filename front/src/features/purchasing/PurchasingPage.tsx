"use client";

import { useEffect, useState } from "react";
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
  Textarea,
  Th,
} from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import {
  FORWARD_NOTICE,
  FORWARD_STATUS,
  forwardQuantity,
  type PurchaseForward,
  type PurchaseForwardStatus,
} from "@/lib/purchasing";
import type { components } from "@/types/api.generated";

type ForwardList = components["schemas"]["PurchaseForwardList"];

function message(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : "Não foi possível concluir a operação. Tente novamente.";
}

export function PurchasingPage() {
  const { api, backend } = useAuth();
  const [status, setStatus] = useState<PurchaseForwardStatus | "">("ENCAMINHADO");
  const [cursor, setCursor] = useState<string | undefined>();
  const [data, setData] = useState<ForwardList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [returning, setReturning] = useState<PurchaseForward | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!backend) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .request("get", "/api/v1/purchase-forwards", {
        query: { status: status || undefined, cursor, limit: 20 },
        signal: controller.signal,
      })
      .then((list) => {
        if (!controller.signal.aborted) setData(list);
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(message(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, backend, status, cursor, retry]);

  async function act(forward: PurchaseForward, accept: boolean) {
    setBusy(forward.id);
    setError(null);
    try {
      if (accept) {
        await api.request("post", "/api/v1/purchase-forwards/{id}/accept", {
          params: { id: forward.id },
          body: { expected_version: forward.version },
        });
      } else {
        await api.request("post", "/api/v1/purchase-forwards/{id}/return", {
          params: { id: forward.id },
          body: { expected_version: forward.version, reason: reason.trim() },
        });
        setReturning(null);
        setReason("");
      }
      setRetry((v) => v + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        n="01"
        eyebrow="Compras"
        title="Encaminhamentos para compras"
        description={`Materiais já cadastrados sem saldo no centro, com o código existente. ${FORWARD_NOTICE}`}
      />
      {!backend ? (
        <EmptyState title="Conecte à API">
          Os encaminhamentos vêm das solicitações de material persistidas.
        </EmptyState>
      ) : (
        <>
          <Card className="mb-6">
            <div className="flex flex-wrap items-end gap-4">
              <Field label="Situação">
                <Select
                  value={status}
                  disabled={loading}
                  onChange={(e) => {
                    setStatus(e.target.value as PurchaseForwardStatus | "");
                    setCursor(undefined);
                  }}
                >
                  <option value="">Todas</option>
                  {Object.entries(FORWARD_STATUS).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button variant="ghost" disabled={loading} onClick={() => setRetry((v) => v + 1)}>
                Atualizar
              </Button>
            </div>
          </Card>
          {error && (
            <p role="alert" className="mb-4 text-alerta">
              {error}
            </p>
          )}
          {loading ? (
            <p role="status">Carregando encaminhamentos…</p>
          ) : !data?.items.length ? (
            <EmptyState title="Nenhum encaminhamento">
              Nada encaminhado para compras nos seus centros com esse filtro.
            </EmptyState>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Material</Th>
                  <Th>Quantidade</Th>
                  <Th>Solicitação</Th>
                  <Th>Situação</Th>
                  <Th>Ação</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <Td>
                      <Code>{row.material_code}</Code>
                      {row.material_description && (
                        <p className="mt-1 max-w-md">{row.material_description}</p>
                      )}
                    </Td>
                    <Td>
                      {forwardQuantity(row)}
                      <p className="mt-1 text-xs text-muted">Centro {row.center_code}</p>
                    </Td>
                    <Td>
                      <Code>{row.request_protocol}</Code>
                      <p className="mt-1 text-xs text-muted">
                        Encaminhado em {fmtDate(row.created_at)}
                      </p>
                    </Td>
                    <Td>
                      <Badge tone={FORWARD_STATUS[row.status].tone}>
                        {FORWARD_STATUS[row.status].label}
                      </Badge>
                      {row.reason && <p className="mt-1 max-w-xs text-sm">{row.reason}</p>}
                    </Td>
                    <Td>
                      {row.can_handle &&
                        (returning?.id === row.id ? (
                          <form
                            className="flex max-w-xs flex-col gap-2"
                            onSubmit={(e) => {
                              e.preventDefault();
                              void act(row, false);
                            }}
                          >
                            <Field label="Motivo da devolução">
                              <Textarea
                                value={reason}
                                required
                                onChange={(e) => setReason(e.target.value)}
                              />
                            </Field>
                            <div className="flex gap-2">
                              <Button
                                type="submit"
                                size="sm"
                                variant="danger"
                                disabled={busy === row.id || !reason.trim()}
                              >
                                Devolver
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={() => setReturning(null)}
                              >
                                Voltar
                              </Button>
                            </div>
                          </form>
                        ) : (
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              disabled={busy === row.id}
                              onClick={() => void act(row, true)}
                            >
                              Aceitar demanda
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={busy === row.id}
                              onClick={() => {
                                setReturning(row);
                                setReason("");
                              }}
                            >
                              Devolver
                            </Button>
                          </div>
                        ))}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {data?.next_cursor && !loading && (
            <Button className="mt-4" variant="ghost" onClick={() => setCursor(data.next_cursor!)}>
              Próxima página
            </Button>
          )}
        </>
      )}
    </>
  );
}
