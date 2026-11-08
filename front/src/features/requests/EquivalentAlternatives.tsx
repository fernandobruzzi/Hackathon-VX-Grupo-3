"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import type { components } from "@/types/api.generated";
import { formatQuantity, type RequestDetail } from "./tracking";

type Alternatives = components["schemas"]["EquivalentAlternatives"];

const blockLabels: Record<string, string> = {
  INACTIVE_MATERIAL: "material inativo",
  UNIT_MISMATCH: "unidade diferente da solicitação",
};

/** Equivalentes autorizados (#246): só com registro aprovado e só quando falta saldo do material. */
export function EquivalentAlternatives({
  detail,
  onChanged,
}: {
  detail: RequestDetail;
  onChanged: (next: RequestDetail) => void;
}) {
  const { api } = useAuth();
  const [data, setData] = useState<Alternatives | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .request("get", "/api/v1/material-requests/{id}/equivalent-alternatives", {
        params: { id: detail.id },
        signal: controller.signal,
      })
      .then((result) => !controller.signal.aborted && setData(result))
      .catch(() => !controller.signal.aborted && setData(null));
    return () => controller.abort();
  }, [api, detail.id, detail.version]);

  if (!data?.shortage || !data.items.length) return null;

  async function substitute() {
    if (!chosen || !confirmed) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.request("post", "/api/v1/material-requests/{id}/substitution", {
        params: { id: detail.id },
        body: { expected_version: detail.version, material_id: chosen, confirm_substitution: true },
      });
      onChanged(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível trocar o material.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Equivalentes autorizados" className="space-y-3">
      <h2 className="text-lg font-bold">Equivalentes autorizados</h2>
      <p className="text-sm">
        O material pedido está sem saldo suficiente neste centro. Estes materiais têm equivalência
        técnica aprovada pela Governança. São itens diferentes, com código e estoque próprios: nada
        é unificado.
      </p>
      <ul className="space-y-3">
        {data.items.map((item) => (
          <li key={item.material_id} className="rounded-lg bg-surface p-4 break-words">
            <label className="flex items-start gap-3">
              <input
                type="radio"
                name="equivalente"
                className="mt-1"
                disabled={!item.selectable}
                checked={chosen === item.material_id}
                onChange={() => setChosen(item.material_id)}
              />
              <span>
                <span className="font-bold">
                  {item.material_code} · {item.description ?? "Sem descrição"}
                </span>
                <br />
                Disponível: {formatQuantity(item.available_quantity)} {item.unit}
                <br />
                <span className="text-sm text-muted">Base da equivalência: {item.basis}</span>
                {!item.selectable && (
                  <span className="block text-sm text-aviso">
                    Indisponível para troca:{" "}
                    {blockLabels[item.blocked_reason ?? ""] ?? item.blocked_reason}
                  </span>
                )}
              </span>
            </label>
          </li>
        ))}
      </ul>
      <label className="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Confirmo a troca do material desta solicitação pelo equivalente escolhido.
      </label>
      {error && <p role="alert">{error}</p>}
      <Button disabled={!chosen || !confirmed || busy} onClick={() => void substitute()}>
        Usar o equivalente
      </Button>
    </section>
  );
}
