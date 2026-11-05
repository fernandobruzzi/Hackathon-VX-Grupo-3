"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Me, PersonaLabel } from "@/types/api";
import { meFor } from "@/lib/permissions";

/**
 * Wireframe: sessão simulada no navegador.
 * Integração: trocar por GET /api/v1/auth/me e POST /api/v1/auth/demo/switch
 * (cookie __Host-vx_session + X-CSRF-Token). O seletor só alterna sessões já autenticadas.
 */
interface AuthCtx {
  me: Me | null;
  ready: boolean;
  signIn: (persona?: PersonaLabel) => void;
  switchPersona: (persona: PersonaLabel) => void;
  signOut: () => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);
const KEY = "vx-demo-persona";
const THEME_KEY = "vx-theme";

function read(key: string) { try { return localStorage.getItem(key); } catch { return null; } }
function write(key: string, v: string | null) { try { v === null ? localStorage.removeItem(key) : localStorage.setItem(key, v); } catch {} }

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const p = read(KEY) as PersonaLabel | null;
    if (p) setMe(meFor(p));
    const t = read(THEME_KEY) === "dark" ? "dark" : "light";
    setTheme(t);
    document.documentElement.dataset.theme = t;
    setReady(true);
  }, []);

  const signIn = useCallback((persona: PersonaLabel = "SOLICITANTE_OPERACAO") => { write(KEY, persona); setMe(meFor(persona)); }, []);
  const switchPersona = useCallback((persona: PersonaLabel) => { write(KEY, persona); setMe(meFor(persona)); }, []);
  const signOut = useCallback(() => { write(KEY, null); setMe(null); }, []);
  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const n = t === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = n;
      write(THEME_KEY, n);
      return n;
    });
  }, []);

  return <Ctx.Provider value={{ me, ready, signIn, switchPersona, signOut, theme, toggleTheme }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth fora do AuthProvider");
  return c;
}
