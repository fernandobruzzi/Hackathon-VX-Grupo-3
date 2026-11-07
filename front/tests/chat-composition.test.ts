import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { ChatPage } from "../src/features/chat/ChatPage";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

async function setup(state: "editable" | "processing" | "submitted" = "editable") {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
  const originalFetch = globalThis.fetch;
  const writes: Record<string, unknown>[] = [];
  let finish!: (response: Response) => void;
  Object.assign(globalThis, {
    window: {
      matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
      addEventListener() {},
      removeEventListener() {},
    },
    document: { documentElement: { dataset: {} } },
    localStorage: {
      getItem: (key: string) => (key === "vx-demo-persona" ? "SOLICITANTE_OPERACAO" : null),
      setItem() {},
    },
    fetch: async (url: string, init: RequestInit) => {
      if (init.method === "POST") {
        writes.push(JSON.parse(init.body as string));
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      }
      return Response.json(
        url.includes("/sessions/")
          ? {
              session_id: "saved",
              session_version: 3,
              center_code: "1100",
              processing: state === "processing",
              order_id: null,
              messages: [],
              calls: [],
              material_card: null,
              submission:
                state === "submitted" ? { order_id: "order", status: "READY_FOR_REVIEW" } : null,
            }
          : {
              items: [{ id: "saved", title: "Pedido salvo", updated_at: "2026-11-06T12:00:00Z" }],
              next_cursor: null,
            },
      );
    },
  });
  let view!: ReactTestRenderer;
  await act(async () => {
    view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
  });
  if (state !== "editable")
    await act(async () => {
      view.root.findByProps({ "aria-label": "Retomar conversa: Pedido salvo" }).props.onClick();
    });
  const input = () => view.root.findByType("textarea");
  const type = (value: string) => act(async () => input().props.onChange({ target: { value } }));
  const compose = (phase: "Start" | "End") =>
    act(async () => input().props[`onComposition${phase}`]?.({}));
  const enter = async (nativeEvent = {}, shiftKey = false) => {
    let prevented = false;
    await act(async () =>
      input().props.onKeyDown({
        key: "Enter",
        shiftKey,
        nativeEvent,
        preventDefault() {
          prevented = true;
        },
      }),
    );
    return prevented;
  };
  const submit = () =>
    act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  const cleanup = async () => {
    await act(async () => view.unmount());
    if (finish)
      await act(async () =>
        finish(
          Response.json(
            {
              error: { code: "FAILED", message: "falhou", details: {}, request_id: "test" },
            },
            { status: 500 },
          ),
        ),
      );
    globalThis.fetch = originalFetch;
    delete process.env.NEXT_PUBLIC_DATA_SOURCE;
  };
  return { view, input, type, compose, enter, submit, writes, cleanup };
}

test("Enter confirma composição sem enviar nem limpar; novo Enter envia texto completo uma vez", async () => {
  const t = await setup();
  try {
    await t.compose("Start");
    await t.type("部品");
    assert.equal(await t.enter(), false, "confirmação continua como edição nativa");
    assert.equal(t.writes.length, 0);
    assert.equal(t.input().props.value, "部品");
    await t.type("部品の注文");
    await t.compose("End");
    assert.equal(await t.enter(), true);
    await t.enter();
    assert.equal(t.writes.length, 1);
    assert.equal(t.writes[0].message, "部品の注文");
    assert.equal(t.input().props.value, "");
    assert.equal(t.input().props.disabled, true, "turno pendente bloqueia envio duplicado");
  } finally {
    await t.cleanup();
  }
});

test("sinais nativos de composição protegem Enter mesmo quando compositionend chega primeiro", async () => {
  const t = await setup();
  try {
    await t.compose("Start");
    await t.type("部品");
    await t.compose("End");
    assert.equal(await t.enter({ isComposing: true }), false);
    assert.equal(await t.enter({ isComposing: false, keyCode: 229 }), false);
    assert.equal(t.writes.length, 0);
    assert.equal(t.input().props.value, "部品");
    await t.enter();
    assert.equal(t.writes.length, 1);
  } finally {
    await t.cleanup();
  }
});

test("Shift+Enter permite quebra de linha e Enviar submete texto confirmado", async () => {
  const t = await setup();
  try {
    await t.compose("Start");
    await t.type("部品");
    await t.compose("End");
    assert.equal(await t.enter({}, true), false, "não impede a quebra de linha do navegador");
    await t.type("部品\n10 unidades");
    assert.equal(t.view.root.findByProps({ "aria-label": "Enviar" }).props.disabled, false);
    await t.submit();
    assert.equal(t.writes.length, 1);
    assert.equal(t.writes[0].message, "部品\n10 unidades");
  } finally {
    await t.cleanup();
  }
});

for (const state of ["editable", "processing", "submitted"] as const) {
  test(`mantém bloqueio de ${state === "editable" ? "mensagem vazia" : state}`, async () => {
    const t = await setup(state);
    try {
      await t.type(state === "editable" ? "   " : "nova mensagem");
      await t.enter();
      await t.submit();
      assert.equal(t.writes.length, 0);
      assert.equal(t.view.root.findByProps({ "aria-label": "Enviar" }).props.disabled, true);
    } finally {
      await t.cleanup();
    }
  });
}
