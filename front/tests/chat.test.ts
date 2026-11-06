import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { ChatPage } from "../src/features/chat/ChatPage";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

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
