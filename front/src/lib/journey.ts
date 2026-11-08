import type { components } from "@/types/api.generated";

export type RequestJourney = components["schemas"]["RequestJourney"];
type Indicator = RequestJourney["unavailable"][number]["indicator"];
type Reason = RequestJourney["unavailable"][number]["reason"];

/** Motivo exibido quando a API não tem dados para um indicador; nunca há estimativa. */
export const UNAVAILABLE_REASON: Record<Reason, string> = {
  NO_REQUESTS: "Nenhuma solicitação nos centros autorizados.",
  NO_RESOLVED_REQUESTS: "Nenhuma solicitação atendida até agora.",
  NO_CHAT_LINKED_REQUESTS: "Nenhuma solicitação vinculada a uma conversa com busca de identidade.",
};

export type JourneyRow = {
  key: string;
  label: string;
  /** Valor formatado, ou null quando indisponível. */
  value: string | null;
  note: string;
};

const int = new Intl.NumberFormat("pt-BR");

/** Horas com vírgula decimal; abaixo de uma hora, em minutos. */
export function fmtHours(hours: number) {
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  return `${hours.toFixed(1).replace(".", ",").replace(/,0$/, "")} h`;
}

function reason(journey: RequestJourney, indicator: Indicator) {
  const item = journey.unavailable.find((entry) => entry.indicator === indicator);
  return item ? UNAVAILABLE_REASON[item.reason] : "Sem dados suficientes.";
}

function count(value: number | undefined | null) {
  return value === null || value === undefined ? null : int.format(value);
}

/** Atendimento pelo estoque, parcial e por compras em linhas separadas, como a API devolve. */
export function fulfillmentRows(journey: RequestJourney): JourneyRow[] {
  const closed = journey.closed;
  const note = closed ? "" : reason(journey, "requests");
  return [
    {
      key: "stock",
      label: "Atendidas pelo estoque",
      value: count(closed?.atendida_estoque),
      note,
    },
    {
      key: "partial",
      label: "Atendidas em parte pelo estoque, resto com Compras",
      value: count(closed?.atendida_parcial_compras),
      note,
    },
    {
      key: "purchasing",
      label: "Encaminhadas integralmente a Compras",
      value: count(closed?.encaminhada_compras),
      note,
    },
    {
      key: "cancelled",
      label: "Canceladas pelo solicitante",
      value: count(closed?.cancelada),
      note,
    },
    {
      key: "rejected",
      label: "Encerradas por cadastro rejeitado",
      value: count(closed?.cadastro_rejeitado),
      note,
    },
  ];
}

/** Indicadores de resultado da jornada, com o motivo quando indisponíveis. */
export function outcomeRows(journey: RequestJourney): JourneyRow[] {
  const time = journey.resolution_time;
  return [
    {
      key: "resolution",
      label: "Tempo até o atendimento (mediana)",
      value: time ? fmtHours(time.median_hours) : null,
      note: time
        ? `90% em até ${fmtHours(time.p90_hours)} · ${int.format(time.resolved_requests)} solicitações atendidas`
        : reason(journey, "resolution_time"),
    },
    {
      key: "registration",
      label: "Cadastros evitados",
      value: count(journey.registration_avoided),
      note:
        journey.registration_avoided === null
          ? reason(journey, "registration_avoided")
          : "Encaminhadas a Compras com o código existente, sem pedido de cadastro.",
    },
    {
      key: "duplicate",
      label: "Duplicidades evitadas",
      value: count(journey.identified_under_other_code),
      note:
        journey.identified_under_other_code === null
          ? reason(journey, "identified_under_other_code")
          : "Itens identificados sob um código ativo pela busca de identidade.",
    },
  ];
}
