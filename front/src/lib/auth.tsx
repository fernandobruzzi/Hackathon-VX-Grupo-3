"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Me, PersonaLabel } from "@/types/api";
import { ApiError, createApiClient } from "@/lib/api";
import { meFor } from "@/lib/permissions";

type AuthMode = "disabled" | "local" | "cognito";
interface AuthCtx {
  me: Me | null;
  ready: boolean;
  backend: boolean;
  authMode: AuthMode;
  api: ReturnType<typeof createApiClient>;
  error: string | null;
  refresh: () => Promise<Me>;
  signIn: (persona?: PersonaLabel) => Promise<boolean>;
  switchPersona: (persona: PersonaLabel) => void;
  signOut: () => Promise<void>;
  theme: "light" | "dark";
  toggleTheme: () => void;
}
const Ctx = createContext<AuthCtx | null>(null);
const KEY = "vx-demo-persona";
const THEME_KEY = "vx-theme";
function read(key: string) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string | null) {
  try {
    value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value);
  } catch {}
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const backend = process.env.NEXT_PUBLIC_DATA_SOURCE !== "mock";
  const [me, setMe] = useState<Me | null>(null);
  const meRef = useRef<Me | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("disabled");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const setSession = useCallback((value: Me | null) => {
    meRef.current = value;
    setMe(value);
  }, []);
  const [api] = useState(() =>
    createApiClient({
      getCsrfToken: () => meRef.current?.csrf_token ?? null,
      onUnauthorized: () => setSession(null),
    }),
  );
  const refresh = useCallback(async () => {
    const value = await api.request("get", "/api/v1/auth/me");
    setSession(value);
    return value;
  }, [api, setSession]);
  useEffect(() => {
    let active = true;
    if (backend) {
      Promise.all([
        api.request("get", "/api/v1/auth/config"),
        (window.location.pathname.startsWith("/auth/callback")
          ? Promise.resolve(null)
          : api.request("get", "/api/v1/auth/me")
        ).catch((error) => {
          if (error instanceof ApiError && error.status === 401) return null;
          throw error;
        }),
      ])
        .then(([config, session]) => {
          if (active) {
            setAuthMode(config.mode);
            if (session || !meRef.current) setSession(session);
          }
        })
        .catch(() => {
          if (active) setError("Não foi possível consultar a sessão da API.");
        })
        .finally(() => {
          if (active) setReady(true);
        });
    } else {
      const persona = read(KEY) as PersonaLabel | null;
      if (persona) setSession(meFor(persona));
      setReady(true);
    }
    const value = read(THEME_KEY) === "dark" ? "dark" : "light";
    setTheme(value);
    document.documentElement.dataset.theme = value;
    return () => {
      active = false;
    };
  }, [api, backend, setSession]);
  const signIn = useCallback(
    async (persona: PersonaLabel = "SOLICITANTE_OPERACAO") => {
      setError(null);
      if (!backend) {
        write(KEY, persona);
        setSession(meFor(persona));
        return true;
      }
      if (authMode === "cognito") {
        window.location.assign("/api/v1/auth/sso-start");
        return false;
      }
      if (authMode !== "local") {
        setError("Autenticação não configurada no servidor.");
        return false;
      }
      try {
        const session = await api.request("post", "/api/v1/auth/local-session", {
          body: { persona },
        });
        setSession(session);
        return true;
      } catch (error) {
        setError(error instanceof ApiError ? error.message : "Não foi possível entrar.");
        return false;
      }
    },
    [api, authMode, backend, setSession],
  );
  const switchPersona = useCallback(
    (persona: PersonaLabel) => {
      if (!backend || authMode === "local") void signIn(persona);
    },
    [authMode, backend, signIn],
  );
  const signOut = useCallback(async () => {
    if (backend) await api.request("post", "/api/v1/auth/logout", { body: {} });
    write(KEY, null);
    setSession(null);
  }, [api, backend, setSession]);
  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next = current === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      write(THEME_KEY, next);
      return next;
    });
  }, []);
  return (
    <Ctx.Provider
      value={{
        me,
        ready,
        backend,
        authMode,
        api,
        error,
        refresh,
        signIn,
        switchPersona,
        signOut,
        theme,
        toggleTheme,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
export function useAuth() {
  const context = useContext(Ctx);
  if (!context) throw new Error("useAuth fora do AuthProvider");
  return context;
}
