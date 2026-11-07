"use client";

import { createContext, useContext, useMemo, type MutableRefObject } from "react";
import type { components } from "@/types/api.generated";
import type { ProposalType } from "@/types/api";

export type Area = "TECHNICAL" | "FISCAL" | "HISTORY";
export type Summary = components["schemas"]["ProposalSummary"];
export interface QueueNavigation {
  area: Area;
  type: ProposalType | "ALL";
  items: Summary[];
  cursor: string | null;
  nextCursor: string | null;
  loaded: boolean;
  pageCount: number;
  anchor: string | null;
  scrollY: number;
}
const Context = createContext<MutableRefObject<QueueNavigation | null> | null>(null);

/** Apenas memória: o AuthProvider recria este contexto em toda transição de sessão. */
export function QueueNavigationProvider({
  children,
  sessionKey,
}: {
  children: React.ReactNode;
  sessionKey: string;
}) {
  const navigation = useMemo<MutableRefObject<QueueNavigation | null>>(
    () => ({ current: null }),
    [sessionKey],
  );
  return <Context.Provider value={navigation}>{children}</Context.Provider>;
}
export function useQueueNavigation() {
  const navigation = useContext(Context);
  if (!navigation) throw new Error("Fila fora do contexto de navegação");
  return navigation;
}
export function belongsToQueue(item: Summary, area: Area) {
  if (area === "HISTORY") return item.status !== "PENDING";
  return (
    item.status === "PENDING" &&
    (area === "TECHNICAL" ? item.technical_review_status : item.fiscal_review_status) === "PENDING"
  );
}
export function mergeQueueItems(previous: Summary[], incoming: Summary[]) {
  return [...new Map([...previous, ...incoming].map((item) => [item.id, item])).values()];
}
