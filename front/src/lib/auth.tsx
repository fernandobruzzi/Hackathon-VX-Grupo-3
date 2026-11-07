"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Me, PersonaLabel } from "@/types/api";
import { ApiError, StaleSessionError, createApiClient } from "@/lib/api";
import { QueueNavigationProvider } from "@/features/sanitization/QueueNavigation";
import { meFor } from "@/lib/permissions";

type AuthMode = "disabled" | "local" | "cognito";
interface AuthCtx {
  me: Me | null;
  ready: boolean;
  backend: boolean;
  authMode: AuthMode;
  api: ReturnType<typeof createApiClient>;
  error: string | null;
  sessionBusy: boolean;
  sessionRevision: number;
  refresh: () => Promise<Me>;
  signIn: (persona?: PersonaLabel) => Promise<boolean>;
  switchPersona: (persona: PersonaLabel) => void;
  /** Resolve `true` quando o navegador vai sair da aplicação para encerrar a sessão do provedor. */
  signOut: () => Promise<boolean>;
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
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sessionRevision, setSessionRevision] = useState(0);
  const revision = useRef(0);
  const refreshing = useRef(0);
  const transitioning = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const setSession = useCallback((value: Me | null) => {
    revision.current += 1;
    setSessionRevision(revision.current);
    meRef.current = value;
    setMe(value);
  }, []);
  const [api] = useState(() =>
    createApiClient({
      getCsrfToken: () => meRef.current?.csrf_token ?? null,
      onUnauthorized: () => setSession(null),
      getSessionRevision: () => revision.current,
    }),
  );
  const refresh = useCallback(async () => {
    if (transitioning.current) throw new StaleSessionError();
    const request = ++refreshing.current;
    const started = revision.current;
    const value = await api.request("get", "/api/v1/auth/me");
    if (request !== refreshing.current || started !== revision.current)
      throw new StaleSessionError();
    setSession(value);
    return value;
  }, [api, setSession]);

  useEffect(() => {
    let active = true;
    const started = revision.current;
    const request = ++refreshing.current;
    if (backend) {
      const config = api
        .request("get", "/api/v1/auth/config")
        .then((value) => {
          if (active) setAuthMode(value.mode);
        })
        .catch((error) => {
          if (active) setError("Não foi possível consultar a configuração de autenticação.");
          throw error;
        });
      const callback = window.location.pathname.startsWith("/auth/callback");
      const session = (callback ? Promise.resolve(null) : api.request("get", "/api/v1/auth/me"))
        .catch((error) => {
          if (error instanceof ApiError && error.status === 401) return null;
          throw error;
        })
        .then((value) => {
          if (!callback && active && started === revision.current && request === refreshing.current)
            setSession(value);
        });
      Promise.all([config, session])
        .catch((error) => {
          if (active && started === revision.current && !(error instanceof StaleSessionError)) {
            setError("Não foi possível consultar a sessão da API.");
          }
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

  const beginTransition = useCallback(() => {
    // O ref impede dois cliques no mesmo ciclo, antes de o React desabilitar os botões.
    if (transitioning.current) return false;
    transitioning.current = true;
    revision.current += 1;
    refreshing.current += 1;
    setSessionBusy(true);
    setError(null);
    return true;
  }, []);
  const endTransition = useCallback(() => {
    transitioning.current = false;
    setSessionBusy(false);
  }, []);
  const reconcileSession = useCallback(async () => {
    // Uma falha de transporte pode ocorrer depois de o navegador já receber o novo cookie.
    try {
      setSession(await api.request("get", "/api/v1/auth/me"));
    } catch {
      setSession(null);
    }
  }, [api, setSession]);

  const signIn = useCallback(
    async (persona: PersonaLabel = "SOLICITANTE_OPERACAO") => {
      if (!beginTransition()) return false;
      let navigating = false;
      try {
        if (!backend) {
          write(KEY, persona);
          setSession(meFor(persona));
          return true;
        }
        if (authMode === "cognito") {
          window.location.assign("/api/v1/auth/sso-start");
          navigating = true;
          return false;
        }
        if (authMode !== "local") {
          setError("Autenticação não configurada no servidor.");
          return false;
        }
        const session = await api.request("post", "/api/v1/auth/local-session", {
          body: { persona },
        });
        setSession(session);
        return true;
      } catch (error) {
        await reconcileSession();
        setError(
          error instanceof ApiError
            ? error.message
            : "Não foi possível confirmar a entrada. Confira a sessão e tente novamente.",
        );
        return false;
      } finally {
        if (!navigating) endTransition();
      }
    },
    [api, authMode, backend, beginTransition, endTransition, reconcileSession, setSession],
  );

  const switchPersona = useCallback(
    (persona: PersonaLabel) => {
      if (!backend || authMode === "local") {
        void signIn(persona);
        return;
      }
      if (authMode !== "cognito" || !beginTransition()) return;
      void (async () => {
        let navigating = false;
        try {
          await api.request("post", "/api/v1/auth/demo/switch", {
            body: { session_handle: persona },
          });
          // A página nova confere /auth/me e não conserva dados privados do usuário anterior.
          window.location.reload();
          navigating = true;
        } catch (error) {
          if (error instanceof ApiError && error.error.code === "DEMO_SESSION_NOT_FOUND") {
            window.location.assign("/api/v1/auth/sso-start?prompt=login");
            navigating = true;
            return;
          }
          await reconcileSession();
          setError(
            error instanceof ApiError
              ? error.message
              : "Não foi possível confirmar a troca de persona. Tente novamente.",
          );
        } finally {
          if (!navigating) endTransition();
        }
      })();
    },
    [api, authMode, backend, beginTransition, endTransition, reconcileSession, signIn],
  );

  const signOut = useCallback(async () => {
    if (!beginTransition()) throw new Error("Aguarde a atualização da sessão.");
    let navigating = false;
    try {
      const result = backend
        ? await api.request("post", "/api/v1/auth/logout", { body: {} })
        : undefined;
      write(KEY, null);
      setSession(null);
      // No Cognito, a sessão do Hosted UI sobrevive ao logout da API: sem encerrá-la,
      // o próximo login volta à mesma conta sem pedir senha.
      const providerLogout = result?.provider_logout_url;
      if (providerLogout?.startsWith("https://")) {
        window.location.assign(providerLogout);
        navigating = true;
      }
      return navigating;
    } catch (error) {
      await reconcileSession();
      setError("Não foi possível confirmar a saída. Confira a sessão e tente novamente.");
      throw error;
    } finally {
      if (!navigating) endTransition();
    }
  }, [api, backend, beginTransition, endTransition, reconcileSession, setSession]);
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
        sessionBusy,
        sessionRevision,
        refresh,
        signIn,
        switchPersona,
        signOut,
        theme,
        toggleTheme,
      }}
    >
      <QueueNavigationProvider sessionKey={`${sessionRevision}:${sessionBusy}`}>
        {children}
      </QueueNavigationProvider>
    </Ctx.Provider>
  );
}
export function useAuth() {
  const context = useContext(Ctx);
  if (!context) throw new Error("useAuth fora do AuthProvider");
  return context;
}
