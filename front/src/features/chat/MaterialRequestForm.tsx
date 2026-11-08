"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { Button, Card } from "@/components/ui";
import type { MaterialCardData, MaterialRequestDetail } from "@/types/api";

/** Medidas e referências do produto não são interpretadas como quantidade solicitada. */
export function MaterialRequestForm({
  card,
  center,
  busy,
  submitted,
  openRequestWarning,
  onConfirm,
}: {
  card: MaterialCardData;
  center: string;
  busy?: boolean;
  submitted: MaterialRequestDetail | null;
  openRequestWarning?: string | null;
  onConfirm: (quantity: string, unit: string, acknowledgeOpenRequests: boolean) => void;
}) {
  const id = useId();
  const units = [
    ...new Set((card.existing?.inventory ?? []).map((row) => row.unit).filter(Boolean)),
  ];
  const suggestedUnit = units.length === 1 ? units[0] : "";
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState(suggestedUnit);
  const [unitEdited, setUnitEdited] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!unitEdited) setUnit(suggestedUnit);
  }, [suggestedUnit, unitEdited]);
  if (submitted)
    return (
      <Card id="chat-material-need" className="flex flex-col gap-3" role="status">
        <p className="font-bold text-verde">Solicitação {submitted.protocol} registrada</p>
        <p className="text-sm break-words">
          {submitted.quantity} {submitted.unit} · {center}
        </p>
        <p className="text-sm text-muted">
          {submitted.status === "EM_IDENTIFICACAO"
            ? "Cadastro vai revisar a identificação do material."
            : submitted.status === "AGUARDANDO_CADASTRO"
              ? "O cadastro está em revisão e permanece vinculado à sua solicitação."
              : submitted.status === "ENCERRADA"
                ? "Esta solicitação está encerrada."
                : "Material identificado. Sua necessidade está registrada para atendimento."}
        </p>
        {submitted.registration_order_id && (
          <Link href="/pedidos/" className="text-sm text-verde underline">
            Acompanhar revisão do cadastro
          </Link>
        )}
        <p className="text-xs text-muted">Inicie uma nova conversa para solicitar outro item.</p>
      </Card>
    );
  const confirm = () => {
    const value = quantity.trim();
    if (!/^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$/.test(value) || !/[1-9]/.test(value)) {
      setError(
        "Informe uma quantidade positiva, com até seis casas decimais. Use ponto para decimais.",
      );
      return;
    }
    if (!unit.trim() || !center) {
      setError("Informe a unidade e selecione o centro de destino.");
      return;
    }
    setError(null);
    onConfirm(value, unit.trim(), !!openRequestWarning && acknowledged);
  };
  return (
    <Card
      id="chat-material-need"
      tabIndex={-1}
      role="region"
      className="flex flex-col gap-4"
      aria-label="Confirmar solicitação de material"
    >
      <div>
        <p className="font-bold">Quanto você precisa?</p>
        <p className="mt-1 text-sm text-muted">
          Informe a quantidade e a unidade para concluir a solicitação.
        </p>
        <p className="mt-2 text-sm break-words">
          <span className="font-semibold">Centro de destino:</span>{" "}
          {center || "Selecione um centro"}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm font-semibold" htmlFor={`${id}-quantity`}>
          Quantidade
          <input
            id={`${id}-quantity`}
            inputMode="decimal"
            value={quantity}
            disabled={busy}
            onChange={(event) => {
              setQuantity(event.target.value);
              setError(null);
              setAcknowledged(false);
            }}
            maxLength={25}
            placeholder="Ex.: 10"
            aria-describedby={error ? `${id}-error` : undefined}
            className="h-11 min-w-0 rounded-md bg-ink px-3 font-mono text-text ring-1 ring-surface-2 outline-none focus:ring-2 focus:ring-verde"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold" htmlFor={`${id}-unit`}>
          Unidade
          <input
            id={`${id}-unit`}
            value={unit}
            disabled={busy}
            maxLength={100}
            placeholder="Ex.: PC"
            onChange={(event) => {
              setUnitEdited(true);
              setUnit(event.target.value);
              setError(null);
              setAcknowledged(false);
            }}
            className="h-11 min-w-0 rounded-md bg-ink px-3 text-text ring-1 ring-surface-2 outline-none focus:ring-2 focus:ring-verde"
          />
        </label>
      </div>
      {error && (
        <p id={`${id}-error`} role="alert" className="text-sm text-alerta">
          {error}
        </p>
      )}
      <p className="text-xs leading-5 text-muted">
        Se a identificação ainda exigir revisão, a solicitação seguirá para Cadastro. Confirmar
        registra sua necessidade; reserva, compra e entrega são etapas posteriores.
      </p>
      {openRequestWarning && (
        <div className="flex flex-col gap-3 text-sm">
          <p role="alert" className="text-aviso">
            {openRequestWarning}
          </p>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={acknowledged}
              disabled={busy}
              onChange={(event) => setAcknowledged(event.target.checked)}
              className="mt-1"
            />
            Estou ciente e quero criar outra solicitação.
          </label>
        </div>
      )}
      <Button
        type="button"
        onClick={confirm}
        disabled={busy || !center || (!!openRequestWarning && !acknowledged)}
        className="w-full"
      >
        <span className="min-w-0 leading-5 whitespace-normal">
          {busy ? "Aguarde…" : "Confirmar solicitação de material"}
        </span>
      </Button>
    </Card>
  );
}
