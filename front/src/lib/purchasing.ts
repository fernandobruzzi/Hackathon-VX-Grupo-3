import type { Tone } from "@/components/ui";
import type { components } from "@/types/api.generated";

export type PurchaseForward = components["schemas"]["PurchaseForward"];
export type PurchaseForwardStatus = PurchaseForward["status"];

/**
 * Rótulos do encaminhamento. Ele é a demanda registrada para Compras: nenhum estado indica compra
 * realizada, pedido ao fornecedor ou item recebido (docs/solicitacao-material.md, seção 8).
 */
export const FORWARD_STATUS: Record<PurchaseForwardStatus, { label: string; tone: Tone }> = {
  ENCAMINHADO: { label: "Encaminhado para compras", tone: "info" },
  ACEITO: { label: "Demanda aceita por Compras", tone: "success" },
  DEVOLVIDO: { label: "Devolvido por Compras", tone: "warning" },
  CANCELADO: { label: "Encaminhamento cancelado", tone: "neutral" },
};

export const FORWARD_NOTICE =
  "O encaminhamento registra a demanda para Compras. Ele não confirma pedido ao fornecedor, compra realizada nem recebimento do item.";

/** Quantidade decimal sem zeros à direita, mantendo a unidade do material. */
export function forwardQuantity(forward: Pick<PurchaseForward, "quantity" | "unit">) {
  const [whole, fraction = ""] = forward.quantity.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return `${trimmed ? `${whole},${trimmed}` : whole} ${forward.unit}`;
}
