import assert from "node:assert/strict";
import { test, type TestContext } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { ApiError, StaleSessionError } from "../src/lib/api";
import { meFor } from "../src/lib/permissions";
import { PersonaSwitcher } from "../src/components/shell/AppShell";
import { SignOutButton } from "../src/components/shell/SignOutButton";
import type { Me } from "../src/types/api";

Object.assign(globalThis, { React, IS_REACT_ACT_ENVIRONMENT: true });
const requester = meFor("SOLICITANTE_OPERACAO");
const governance = meFor("GESTOR_CADASTRO");
const fiscal = meFor("AUDITOR_FISCAL");

type Pending = {
  path: string;
  method: string;
  body: Record<string, unknown> | undefined;
  resolve: (response: Response) => void;
  reject: (error: Error) => void;
};

async function setup(
  t: TestContext,
  options: { holdInitial?: boolean; mode?: string; callback?: boolean; holdConfig?: boolean } = {},
) {
  const originals = {
    fetch: globalThis.fetch,
    window: globalThis.window,
    document: globalThis.document,
    localStorage: globalThis.localStorage,
  };
  const oldSource = process.env.NEXT_PUBLIC_DATA_SOURCE;
  process.env.NEXT_PUBLIC_DATA_SOURCE = "api";
  let current!: ReturnType<typeof useAuth>;
  let callbackResult: Promise<unknown> | undefined;
  let server: Me | null = requester;
  let holdMe = options.holdInitial ?? false;
  const requests: Pending[] = [];
  const navigations: string[] = [];
  Object.assign(globalThis, {
    window: {
      location: {
        pathname: options.callback ? "/auth/callback/" : "/chat/",
        assign: (path: string) => navigations.push(path),
        reload: () => navigations.push("reload"),
      },
    },
    document: { documentElement: { dataset: {} } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    fetch: (path: string, init: RequestInit) => {
      if (path === "/api/v1/auth/config" && !options.holdConfig)
        return Promise.resolve(Response.json({ mode: options.mode ?? "local" }));
      if (path === "/api/v1/auth/me" && !holdMe)
        return Promise.resolve(Response.json(server ?? {}, { status: server ? 200 : 401 }));
      return new Promise<Response>((resolve, reject) =>
        requests.push({
          path,
          method: init.method!,
          body: init.body ? JSON.parse(init.body as string) : undefined,
          resolve,
          reject,
        }),
      );
    },
  });
  function Probe() {
    current = useAuth();
    React.useEffect(() => {
      if (options.callback) {
        callbackResult = current.api
          .request("post", "/api/v1/auth/sso-callback", { body: { code: "test", state: "test" } })
          .then(() => current.refresh())
          .catch((error) => error);
      }
    }, []);
    return null;
  }
  let view!: ReactTestRenderer;
  await act(async () => {
    view = create(
      React.createElement(
        AuthProvider,
        null,
        React.createElement(Probe),
        React.createElement(PersonaSwitcher),
        React.createElement(SignOutButton, { onSignedOut: () => navigations.push("/login/") }),
      ),
    );
  });
  t.after(async () => {
    await act(async () => view.unmount());
    Object.assign(globalThis, originals);
    if (oldSource === undefined) delete process.env.NEXT_PUBLIC_DATA_SOURCE;
    else process.env.NEXT_PUBLIC_DATA_SOURCE = oldSource;
  });
  return {
    get auth() {
      return current;
    },
    get callbackResult() {
      return callbackResult;
    },
    view,
    requests,
    navigations,
    holdMe(value: boolean) {
      holdMe = value;
    },
    server(value: Me | null) {
      server = value;
    },
    async respond(request: Pending, value: unknown, status = 200) {
      await act(async () => request.resolve(Response.json(value, { status })));
    },
    async reject(request: Pending) {
      await act(async () => request.reject(new TypeError("network failed")));
    },
  };
}

test("troca de persona serializa escritas e desabilita o seletor real", async (t) => {
  const h = await setup(t);
  const toggle = () =>
    h.view.root
      .findAllByType("button")
      .find((button) => button.props["aria-expanded"] !== undefined)!;
  let first!: Promise<boolean>;
  await act(async () => {
    first = h.auth.signIn("GESTOR_CADASTRO");
    assert.equal(await h.auth.signIn("AUDITOR_FISCAL"), false);
    await assert.rejects(h.auth.signOut(), /Aguarde/);
  });
  assert.equal(h.requests.length, 1);
  assert.equal(h.auth.sessionBusy, true);
  assert.equal(toggle().props.disabled, true);
  assert.match(JSON.stringify(h.view.toJSON()), /Atualizando sessão/);
  h.server(governance);
  await h.respond(h.requests[0], governance);
  assert.equal(await first, true);
  assert.equal(h.auth.me?.user.id, governance.user.id);
  assert.equal(toggle().props.disabled, false);
  await act(async () => {
    h.auth.switchPersona("AUDITOR_FISCAL");
  });
  h.server(fiscal);
  await h.respond(h.requests[1], fiscal);
  assert.equal(h.auth.me?.user.id, fiscal.user.id);
  assert.equal(h.auth.sessionBusy, false);
});

test("consulta inicial atrasada não substitui um login confirmado", async (t) => {
  const h = await setup(t, { holdInitial: true });
  assert.equal(h.auth.authMode, "local");
  await act(async () => {
    void h.auth.signIn("GESTOR_CADASTRO");
  });
  h.server(governance);
  await h.respond(h.requests[1], governance);
  await h.respond(h.requests[0], requester);
  assert.equal(h.auth.me?.user.id, governance.user.id);
  assert.equal(h.auth.ready, true);
  assert.equal(h.auth.error, null);
});

for (const action of ["login", "logout"] as const) {
  test(`refresh atrasado não desfaz ${action}`, async (t) => {
    const h = await setup(t);
    h.holdMe(true);
    let old!: Promise<unknown>;
    await act(async () => {
      old = h.auth.refresh().catch((error) => error);
    });
    h.holdMe(false);
    await act(async () => {
      if (action === "login") void h.auth.signIn("GESTOR_CADASTRO");
      else void h.auth.signOut();
    });
    h.server(action === "login" ? governance : null);
    await h.respond(h.requests[1], action === "login" ? governance : {});
    await h.respond(h.requests[0], requester);
    assert.ok((await old) instanceof StaleSessionError);
    assert.equal(h.auth.me?.user.id ?? null, action === "login" ? governance.user.id : null);
  });
}

for (const status of [200, 401]) {
  test(`resposta ${status} antiga não altera uma sessão nova`, async (t) => {
    const h = await setup(t);
    let old!: Promise<unknown>;
    await act(async () => {
      old = h.auth.api.request("get", "/api/v1/materials").catch((error) => error);
    });
    await act(async () => {
      void h.auth.signIn("GESTOR_CADASTRO");
    });
    h.server(governance);
    await h.respond(h.requests[1], governance);
    await h.respond(h.requests[0], {}, status);
    assert.ok((await old) instanceof StaleSessionError);
    assert.equal(h.auth.me?.user.id, governance.user.id);
  });
}

test("401 da sessão atual continua encerrando a sessão", async (t) => {
  const h = await setup(t);
  let result!: Promise<unknown>;
  await act(async () => {
    result = h.auth.api.request("get", "/api/v1/materials").catch((error) => error);
  });
  await h.respond(h.requests[0], {}, 401);
  assert.ok((await result) instanceof ApiError);
  assert.equal(h.auth.me, null);
});

test("dois refreshes conservam o mais recente mesmo quando o antigo termina primeiro", async (t) => {
  const h = await setup(t);
  h.holdMe(true);
  let first!: Promise<unknown>, last!: Promise<Me>;
  await act(async () => {
    first = h.auth.refresh().catch((error) => error);
    last = h.auth.refresh();
  });
  await h.respond(h.requests[0], requester);
  assert.ok((await first) instanceof StaleSessionError);
  await h.respond(h.requests[1], governance);
  assert.equal((await last).user.id, governance.user.id);
  assert.equal(h.auth.me?.user.id, governance.user.id);
});

for (const changedCookie of [false, true]) {
  test(`falha no login reconcilia a sessão com cookie ${changedCookie ? "alterado" : "anterior"} e libera nova tentativa`, async (t) => {
    const h = await setup(t);
    await act(async () => {
      void h.auth.signIn("GESTOR_CADASTRO");
    });
    h.server(changedCookie ? governance : requester);
    await h.reject(h.requests[0]);
    assert.equal(h.auth.me?.user.id, (changedCookie ? governance : requester).user.id);
    assert.equal(h.auth.sessionBusy, false);
    assert.match(h.auth.error!, /confirmar a entrada/);
    await act(async () => {
      void h.auth.signIn("AUDITOR_FISCAL");
    });
    h.server(fiscal);
    await h.respond(h.requests[1], fiscal);
    assert.equal(h.auth.me?.user.id, fiscal.user.id);
    assert.equal(h.auth.error, null);
  });
}

test("falha na reconciliação não mantém uma identidade que já não pode confirmar", async (t) => {
  const h = await setup(t);
  await act(async () => {
    void h.auth.signIn("GESTOR_CADASTRO");
  });
  h.holdMe(true);
  await h.reject(h.requests[0]);
  assert.equal(h.auth.sessionBusy, true);
  await h.reject(h.requests[1]);
  assert.equal(h.auth.me, null);
  assert.equal(h.auth.sessionBusy, false);
});

test("logout pendente impede novo login e falha consulta a sessão atual", async (t) => {
  const h = await setup(t);
  let logout!: Promise<unknown>;
  await act(async () => {
    logout = h.auth.signOut().catch((error) => error);
    assert.equal(await h.auth.signIn("AUDITOR_FISCAL"), false);
  });
  assert.equal(h.requests.length, 1);
  h.server(requester);
  await h.reject(h.requests[0]);
  assert.ok((await logout) instanceof Error);
  assert.equal(h.auth.me?.user.id, requester.user.id);
  assert.equal(h.auth.sessionBusy, false);
});

test("Cognito serializa a troca até a navegação e mantém a verificação no servidor", async (t) => {
  const h = await setup(t, { mode: "cognito" });
  await act(async () => {
    h.auth.switchPersona("GESTOR_CADASTRO");
    h.auth.switchPersona("AUDITOR_FISCAL");
  });
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].path, "/api/v1/auth/demo/switch");
  assert.deepEqual(h.requests[0].body, { session_handle: "GESTOR_CADASTRO" });
  await h.respond(h.requests[0], governance);
  assert.deepEqual(h.navigations, ["reload"]);
  assert.equal(h.auth.sessionBusy, true);
});

test("callback Cognito conclui enquanto a configuração inicial ainda está pendente", async (t) => {
  const h = await setup(t, { callback: true, holdConfig: true, mode: "cognito" });
  const callback = h.requests.find((request) => request.path === "/api/v1/auth/sso-callback")!;
  const config = h.requests.find((request) => request.path === "/api/v1/auth/config")!;
  h.server(governance);
  await h.respond(callback, { authenticated: true });
  assert.deepEqual(await h.callbackResult, governance);
  await h.respond(config, { mode: "cognito" });
  assert.equal(h.auth.me?.user.id, governance.user.id);
  assert.equal(h.auth.authMode, "cognito");
  assert.equal(h.auth.ready, true);
  assert.equal(h.auth.error, null);
});

test("persona Cognito ainda não autenticada pede login sem liberar outra troca", async (t) => {
  const h = await setup(t, { mode: "cognito" });
  await act(async () => h.auth.switchPersona("AUDITOR_FISCAL"));
  await h.respond(
    h.requests[0],
    {
      error: {
        code: "DEMO_SESSION_NOT_FOUND",
        message: "Entre com a conta.",
        request_id: "test",
        details: {},
      },
    },
    404,
  );
  assert.deepEqual(h.navigations, ["/api/v1/auth/sso-start?prompt=login"]);
  assert.equal(h.auth.sessionBusy, true);
});

test("falha na configuração continua visível mesmo com o perfil inicial confirmado", async (t) => {
  const h = await setup(t, { holdConfig: true });
  assert.equal(h.auth.me?.user.id, requester.user.id);
  await h.reject(h.requests[0]);
  assert.equal(h.auth.ready, true);
  assert.match(h.auth.error!, /configuração de autenticação/);
});

test("botão de saída serializa cliques e informa progresso antes de redirecionar", async (t) => {
  const h = await setup(t, { mode: "cognito" });
  const control = () => h.view.root.findByProps({ "aria-label": "Sair da conta" });
  await act(async () => {
    void control().props.onClick();
    void control().props.onClick();
  });
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].path, "/api/v1/auth/logout");
  assert.equal(control().props.disabled, true);
  assert.equal(control().props["aria-busy"], true);
  assert.match(JSON.stringify(h.view.toJSON()), /Saindo/);
  assert.deepEqual(h.navigations, []);
  await h.respond(h.requests[0], {});
  assert.equal(h.auth.me, null);
  assert.deepEqual(h.navigations, ["/login/"]);
});

test("botão de saída permite repetir após falha com identidade reconciliada", async (t) => {
  const h = await setup(t, { mode: "cognito" });
  const control = () => h.view.root.findByProps({ "aria-label": "Sair da conta" });
  await act(async () => {
    void control().props.onClick();
  });
  await h.reject(h.requests[0]);
  assert.equal(h.auth.me?.user.id, requester.user.id);
  assert.match(h.auth.error ?? "", /Não foi possível confirmar a saída/);
  assert.equal(control().props.disabled, false);
  assert.deepEqual(h.navigations, []);
  await act(async () => {
    void control().props.onClick();
  });
  assert.equal(h.requests.length, 2);
  await h.respond(h.requests[1], {});
  assert.equal(h.auth.me, null);
  assert.deepEqual(h.navigations, ["/login/"]);
});
