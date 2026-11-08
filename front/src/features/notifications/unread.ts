"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";

export const NOTIFICATIONS_CHANGED = "vx:notifications-changed";

/** Total real de não lidas (#249); `undefined` sem sessão conectada ou se a consulta falhar. */
export function useUnreadNotifications(path: string | null): number | undefined {
  const { api, me, backend, sessionRevision } = useAuth();
  const [count, setCount] = useState<number | undefined>(undefined);
  const [tick, setTick] = useState(0);
  const allowed = !!me && backend && can(me, "requests:read_own");

  useEffect(() => {
    const refresh = () => setTick((value) => value + 1);
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    window.addEventListener(NOTIFICATIONS_CHANGED, refresh);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED, refresh);
  }, []);

  useEffect(() => {
    if (!allowed) {
      setCount(undefined);
      return;
    }
    const controller = new AbortController();
    api
      .request("get", "/api/v1/notifications", { query: { limit: 1 }, signal: controller.signal })
      .then((result) => !controller.signal.aborted && setCount(result.unread_count))
      // Sem total confiável, o contador some em vez de mostrar zero.
      .catch(() => !controller.signal.aborted && setCount(undefined));
    return () => controller.abort();
  }, [allowed, api, path, sessionRevision, tick]);

  return allowed ? count : undefined;
}
