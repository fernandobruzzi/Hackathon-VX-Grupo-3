"use client";

import { useRef, useState } from "react";
import { Button, Field, Input, Textarea } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { RegistrationOrder } from "@/types/api";

export function OrderComplementForm({
  order,
  onSaved,
  onCancel,
}: {
  order: RegistrationOrder;
  onSaved: (order: RegistrationOrder) => void;
  onCancel: () => void;
}) {
  const { api } = useAuth();
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const attempts = useRef(new Map<string, string>());
  const save = async () => {
    const body = { expected_version: order.version, text, source, reason };
    const fingerprint = JSON.stringify({ id: order.id, ...body });
    const key = attempts.current.get(fingerprint) ?? crypto.randomUUID();
    attempts.current.set(fingerprint, key);
    setBusy(true);
    setError(null);
    try {
      const result = await api.request("post", "/api/v1/registration-orders/{id}/complement", {
        params: { id: order.id },
        body,
        idempotencyKey: key,
      });
      onSaved(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível salvar o complemento.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="my-4 rounded-md bg-surface-2 p-4">
      <h2 className="mb-3 font-bold">Complementar pedido {order.id.slice(0, 8)}</h2>
      <p className="mb-3 text-sm text-muted">
        Falta: {order.missing_attributes.join(", ") || "revisão do PDM"}. O texto original será
        preservado.
      </p>
      <div className="grid gap-3">
        <Field label="Informações complementares">
          <Textarea value={text} maxLength={10000} onChange={(e) => setText(e.target.value)} />
        </Field>
        <Field label="Origem da informação">
          <Input value={source} maxLength={1000} onChange={(e) => setSource(e.target.value)} />
        </Field>
        <Field label="Motivo">
          <Input value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {error && (
          <p role="alert" className="text-alerta">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            disabled={busy || !text.trim() || !source.trim() || !reason.trim()}
            onClick={save}
          >
            Salvar e reavaliar
          </Button>
          <Button variant="ghost" disabled={busy} onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </div>
    </section>
  );
}
