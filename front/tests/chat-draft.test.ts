import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { ChatPage } from "../src/features/chat/ChatPage";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const session = (id: string, content: string) => ({
  session_id: id,
  session_version: 3,
  center_code: "1100",
  processing: false,
  order_id: null,
  messages: [{ id: `${id}-m`, author: "user", content, created_at: "2026-11-06T12:00:00Z" }],
  calls: [],
  material_card: null,
});
const SESSIONS: Record<string, ReturnType<typeof session>> = {
  "saved-chat": session("saved-chat", "pedido salvo"),
  "other-chat": session("other-chat", "outro pedido"),
};

function SwitchPersona() {
  const { switchPersona } = useAuth();
  return React.createElement("button", {
    "aria-label": "Trocar persona",
    onClick: () => switchPersona("GESTOR_CADASTRO"),
  });
}

async function setup() {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
  const originalFetch = globalThis.fetch;
  const reads: string[] = [];
  const writes: Record<string, unknown>[] = [];
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
        return Response.json(
          { error: { code: "X", message: "falhou", details: {}, request_id: "t" } },
          { status: 500 },
        );
      }
      const id = url.match(/\/sessions\/([^/?]+)/)?.[1];
      if (id) {
        reads.push(id);
        return Response.json(SESSIONS[id]);
      }
      return Response.json({
        items: [
          { id: "saved-chat", title: "Pedido salvo", updated_at: "2026-11-06T12:00:00Z" },
          { id: "other-chat", title: "Outro pedido", updated_at: "2026-11-06T11:00:00Z" },
        ],
        next_cursor: null,
      });
    },
  });
  let view!: ReactTestRenderer;
  await act(async () => {
    view = create(
      React.createElement(
        AuthProvider,
        null,
        React.createElement(ChatPage),
        React.createElement(SwitchPersona),
      ),
    );
  });
  const json = () => JSON.stringify(view.toJSON());
  const button = (label: string) =>
    view.root
      .findAllByType("button")
      .find(
        (item) =>
          item.props["aria-label"] === label ||
          item.children.some((child) => typeof child === "string" && child.includes(label)),
      );
  const click = async (label: string) => {
    const target = button(label);
    assert.ok(target, `botão ${label}`);
    await act(async () => target.props.onClick());
  };
  const type = async (value: string) =>
    act(async () => view.root.findByType("textarea").props.onChange({ target: { value } }));
  const guard = () => view.root.findAllByProps({ role: "group" });
  const cleanup = async () => {
    await act(async () => view.unmount());
    globalThis.fetch = originalFetch;
    delete process.env.NEXT_PUBLIC_DATA_SOURCE;
  };
  return { view: () => view, json, button, click, type, guard, reads, writes, cleanup };
}

test("sem rascunho, Nova conversa e outra conversa continuam diretas", async () => {
  const t = await setup();
  try {
    await t.click("Retomar conversa: Pedido salvo");
    assert.match(t.json(), /pedido salvo/);
    await t.click("Retomar conversa: Outro pedido");
    assert.equal(t.guard().length, 0);
    assert.match(t.json(), /outro pedido/);
    await t.type("   ");
    await t.click("Nova conversa");
    assert.equal(t.guard().length, 0);
    assert.doesNotMatch(t.json(), /outro pedido/);
    assert.deepEqual(t.reads, ["saved-chat", "other-chat"]);
  } finally {
    await t.cleanup();
  }
});

test("com rascunho, Nova conversa pede confirmação e continuar preserva texto, conversa e centro", async () => {
  const t = await setup();
  try {
    await t.click("Retomar conversa: Pedido salvo");
    await t.type("descrição longa ainda não enviada");
    await t.click("Nova conversa");
    assert.equal(t.guard().length, 1);
    assert.match(t.json(), /mensagem não enviada/);
    assert.match(t.json(), /Iniciar uma nova conversa apaga esse texto/);
    assert.equal(
      t.view().root.findByType("textarea").props.value,
      "descrição longa ainda não enviada",
    );

    await t.click("Continuar editando");
    assert.equal(t.guard().length, 0);
    assert.equal(
      t.view().root.findByType("textarea").props.value,
      "descrição longa ainda não enviada",
    );
    assert.match(t.json(), /pedido salvo/);
    assert.equal(t.view().root.findByProps({ id: "center" }).props.value, "1100");
    assert.equal(t.writes.length, 0, "proteger o rascunho não envia mensagem");

    // Escape também volta à edição.
    await t.click("Nova conversa");
    await act(async () => t.guard()[0].props.onKeyDown({ key: "Escape" }));
    assert.equal(t.guard().length, 0);
    assert.match(t.json(), /pedido salvo/);

    await t.click("Nova conversa");
    await t.click("Descartar mensagem");
    assert.equal(t.guard().length, 0);
    assert.equal(t.view().root.findByType("textarea").props.value, "");
    assert.doesNotMatch(t.json(), /pedido salvo/);
    assert.equal(t.view().root.findAllByProps({ "aria-current": "true" }).length, 0);
    assert.equal(t.writes.length, 0);
  } finally {
    await t.cleanup();
  }
});

test("com rascunho, abrir outra conversa só carrega depois do descarte e uma única vez", async () => {
  const t = await setup();
  try {
    await t.click("Retomar conversa: Pedido salvo");
    await t.type("rascunho");
    await t.click("Retomar conversa: Outro pedido");
    assert.match(t.json(), /Abrir outra conversa apaga esse texto/);
    assert.deepEqual(t.reads, ["saved-chat"], "nada é carregado antes da confirmação");
    assert.match(t.json(), /pedido salvo/);

    await t.click("Descartar mensagem");
    assert.deepEqual(t.reads, ["saved-chat", "other-chat"]);
    assert.match(t.json(), /outro pedido/);
    assert.equal(t.view().root.findByType("textarea").props.value, "");
    assert.equal(t.guard().length, 0);
  } finally {
    await t.cleanup();
  }
});

test("atualizar ou reabrir a mesma conversa mantém o rascunho sem confirmação", async () => {
  const t = await setup();
  try {
    await t.click("Retomar conversa: Pedido salvo");
    await t.type("continuar daqui");
    await t.click("Atualizar conversa");
    assert.equal(t.guard().length, 0);
    assert.equal(t.view().root.findByType("textarea").props.value, "continuar daqui");
    await t.click("Retomar conversa: Pedido salvo");
    assert.equal(t.guard().length, 0);
    assert.equal(t.view().root.findByType("textarea").props.value, "continuar daqui");
    assert.deepEqual(t.reads, ["saved-chat", "saved-chat", "saved-chat"]);
  } finally {
    await t.cleanup();
  }
});

test("trocar de persona não deixa o rascunho nem a confirmação para a outra identidade", async () => {
  const t = await setup();
  try {
    await t.type("texto confidencial");
    await t.click("Retomar conversa: Pedido salvo");
    assert.equal(t.guard().length, 1);
    await t.click("Trocar persona");
    assert.doesNotMatch(t.json(), /texto confidencial/);
    assert.doesNotMatch(t.json(), /mensagem não enviada/);
  } finally {
    await t.cleanup();
  }
});
