import type { components } from "@/types/api.generated";

export type MaterialRequest = components["schemas"]["MaterialRequestSummary"];
export type RequestDetail = components["schemas"]["MaterialRequestDetail"];
export type RequestStatus = MaterialRequest["status"];

export const stages: Record<RequestStatus, { label: string; team: string; pending: string }> = {
  EM_IDENTIFICACAO: {
    label: "Em identificação",
    team: "Cadastro",
    pending: "Identificar o material e confirmar os dados necessários ao atendimento.",
  },
  AGUARDANDO_CADASTRO: {
    label: "Aguardando cadastro",
    team: "Cadastro / Fiscal",
    pending: "Concluir o cadastro e as revisões necessárias para liberar o material.",
  },
  EM_ATENDIMENTO: {
    label: "Em atendimento",
    team: "Almoxarifado / Compras",
    pending: "Definir o atendimento das quantidades por estoque ou compras.",
  },
  ENCERRADA: {
    label: "Encerrada",
    team: "Sem etapa ativa",
    pending: "Nenhuma etapa em andamento. Consulte o motivo no histórico.",
  },
};

/** Preserva todas as casas da quantidade sem conversão para ponto flutuante. */
export function formatQuantity(value: string): string {
  const [integer, fraction] = value.split(".");
  const decimals = fraction?.replace(/0+$/, "");
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (decimals ? `,${decimals}` : "");
}

export function quantityOrUnavailable(value: string | null | undefined): string {
  return value == null ? "Não informada" : formatQuantity(value);
}

export function pendingActions(detail: RequestDetail): string {
  if (detail.status !== "EM_ATENDIMENTO") return stages[detail.status].pending;
  const positive = (value: string | undefined) => value != null && /[1-9]/.test(value);
  const actions = [];
  if (positive(detail.reserved_quantity))
    actions.push("Aguardando entrega das quantidades reservadas pelo Almoxarifado.");
  if (detail.purchase_forwards?.some((forward) => forward.status === "ENCAMINHADO"))
    actions.push("Aguardando análise da demanda por Compras.");
  if (positive(detail.pending_quantity))
    actions.push("Definir o atendimento da quantidade ainda pendente.");
  return actions.join(" ") || "Aguardando atualização do atendimento.";
}

export const eventLabels: Record<string, string> = {
  MATERIAL_REQUEST_CREATED: "Solicitação criada",
  MATERIAL_REQUEST_CANCELLED: "Solicitação cancelada",
  MATERIAL_REQUEST_PARTIAL_FULFILLMENT: "Atendimento dividido entre estoque e compras",
  MATERIAL_REQUEST_FORWARDED_TO_PURCHASING: "Encaminhada para compras",
  MATERIAL_REQUEST_CLOSED: "Atendimento encerrado",
  MATERIAL_REQUEST_PURCHASE_RETURNED: "Demanda devolvida por Compras",
};

export const closureLabels: Record<string, string> = {
  CANCELADA: "Cancelada pelo solicitante",
  ATENDIDA_ESTOQUE: "Atendida pelo estoque",
  ENCAMINHADA_COMPRAS: "Demanda aceita por Compras",
  ATENDIDA_PARCIAL_COMPRAS: "Atendida por estoque e demanda aceita por Compras",
};

export function requestDate(value: string): string {
  return new Date(value).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
