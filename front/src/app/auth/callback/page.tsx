"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Seta } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function CallbackPage() {
  const { api, refresh } = useAuth();
  const router = useRouter();
  const pending = useRef<Promise<string> | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    if (!pending.current) {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code"),
        state = params.get("state");
      window.history.replaceState(null, "", "/auth/callback/");
      pending.current =
        !code || !state || params.has("error")
          ? Promise.reject(new Error("Login inválido"))
          : api
              .request("post", "/api/v1/auth/sso-callback", { body: { code, state } })
              .then(async () => {
                await refresh();
                return "/chat/";
              });
    }
    pending.current
      .then((path) => {
        if (active) router.replace(path);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [api, refresh, router]);
  return (
    <div className="grid min-h-dvh place-items-center">
      <div className="flex flex-col items-center gap-4">
        <Seta className="h-12 w-11" />
        <p>
          {error ? "Não foi possível concluir o login. Tente novamente." : "Validando sua sessão…"}
        </p>
        {error && <Button onClick={() => router.replace("/login/")}>Voltar ao login</Button>}
      </div>
    </div>
  );
}
