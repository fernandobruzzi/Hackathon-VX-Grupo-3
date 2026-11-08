import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { ChatPage } from "../src/features/chat/ChatPage";
import { meFor } from "../src/lib/permissions";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

test("seletor envia código do centro e chat distingue timeout de outras falhas 503", async () => {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "api";
  const originalFetch = globalThis.fetch;
  const me = meFor("SOLICITANTE_OPERACAO");
  me.scope = {
    center_codes: ["1100", "0010"],
    center_names: { "1100": "USINA DE BENEFICIAMENTO" },
  };
  const writes: Record<string, unknown>[] = [];
  let agentError = { code: "AGENT_UNAVAILABLE", message: "O assistente está indisponível." };
  Object.assign(globalThis, {
    window: {
      location: { pathname: "/chat/" },
      matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
      addEventListener() {},
      removeEventListener() {},
    },
    document: { documentElement: { dataset: {} } },
    localStorage: { getItem: () => null },
    fetch: async (url: string, init: RequestInit) => {
      if (url.endsWith("/auth/config")) return Response.json({ mode: "local" });
      if (url.endsWith("/auth/me")) return Response.json(me);
      if (init.method === "POST") {
        writes.push(JSON.parse(init.body as string));
        return Response.json(
          { error: { ...agentError, details: {}, request_id: "test" } },
          { status: 503 },
        );
      }
      return Response.json({ items: [], next_cursor: null });
    },
  });
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
    });
    const selector = view.root.findByProps({ id: "center" });
    const options = selector.findAllByType("option");
    assert.deepEqual(
      options.map((option) => [option.props.value, option.children.join("")]),
      [
        ["1100", "USINA DE BENEFICIAMENTO"],
        ["0010", "0010"],
      ],
    );
    await act(async () => selector.props.onChange({ target: { value: "1100" } }));
    await act(async () =>
      view.root.findByType("textarea").props.onChange({ target: { value: "parafuso" } }),
    );
    await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
    assert.equal(writes[0].center_code, "1100");
    assert.equal(view.root.findByProps({ role: "alert" }).children.join(""), agentError.message);
    for (const [code, expected] of [
      ["AGENT_TIMEOUT", "O assistente não respondeu a tempo. Tente enviar de novo."],
      ["AGENT_BUSY", "O assistente está ocupado. Aguarde alguns instantes e tente enviar de novo."],
      ["AGENT_UNAVAILABLE", "Não foi possível falar com o servidor."],
    ]) {
      agentError = { code, message: "" };
      await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
      assert.equal(view.root.findByProps({ role: "alert" }).children.join(""), expected);
      assert.equal(view.root.findByType("textarea").props.value, "parafuso");
    }
  } finally {
    if (view) await act(async () => view.unmount());
    globalThis.fetch = originalFetch;
    delete process.env.NEXT_PUBLIC_DATA_SOURCE;
  }
});

for (const outcome of ["success", "failure"] as const) {
  test(`Nova conversa ignora ${outcome} tardio sem finalizar o novo turno`, async () => {
    process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
    const pending: {
      resolve: (value: Response) => void;
      reject: (error: Error) => void;
      body: Record<string, unknown>;
      signal: AbortSignal;
    }[] = [];
    const originalFetch = globalThis.fetch;
    Object.assign(globalThis, {
      window: {
        matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
        addEventListener() {},
        removeEventListener() {},
      },
      document: { documentElement: { dataset: {} } },
      localStorage: {
        getItem: (key: string) => (key === "vx-demo-persona" ? "SOLICITANTE_OPERACAO" : null),
      },
      fetch: (_url: unknown, init: RequestInit) =>
        init.method === "GET"
          ? Promise.resolve(Response.json({ items: [], next_cursor: null }))
          : new Promise<Response>((resolve, reject) =>
              pending.push({
                resolve,
                reject,
                body: JSON.parse(init.body as string),
                signal: init.signal as AbortSignal,
              }),
            ),
    });
    let view!: ReactTestRenderer;
    const send = async (text: string) => {
      await act(async () =>
        view.root.findByType("textarea").props.onChange({ target: { value: text } }),
      );
      await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
    };
    try {
      await act(async () => {
        view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
      });
      await send("antigo");
      await act(async () =>
        view.root
          .findAllByType("button")
          .find((button) => button.children.includes(" Nova conversa"))!
          .props.onClick(),
      );
      await send("novo");
      assert.equal(pending.length, 2, "o novo turno pode começar antes de o antigo terminar");
      assert.equal(pending[0].signal.aborted, true);
      assert.equal(pending[1].body.session_id, null);
      await act(async () => {
        if (outcome === "failure") pending[0].reject(new Error("falha antiga"));
        else
          pending[0].resolve(
            Response.json({
              session_id: "old",
              session_version: 1,
              assistant_message: "resposta antiga",
              tool_calls: [],
              material_card: { missing_attributes: [] },
            }),
          );
      });
      assert.equal(view.root.findByProps({ "aria-label": "Enviar" }).props.disabled, true);
      assert.equal(view.root.findByType("textarea").props.value, "");
      assert.equal(view.root.findAllByProps({ role: "alert" }).length, 0);
      assert.doesNotMatch(JSON.stringify(view.toJSON()), /resposta antiga|sessão v1/);
      await act(async () => pending[1].reject(new Error("falha nova")));
      assert.equal(view.root.findByType("textarea").props.value, "novo");
    } finally {
      if (view) await act(async () => view.unmount());
      globalThis.fetch = originalFetch;
      delete process.env.NEXT_PUBLIC_DATA_SOURCE;
    }
  });
}
