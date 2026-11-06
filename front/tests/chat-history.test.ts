import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { ChatPage } from "../src/features/chat/ChatPage";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const saved = {
  session_id: "saved-chat",
  session_version: 4,
  center_code: "1100",
  processing: false,
  order_id: null,
  messages: [
    {
      id: "old-message",
      author: "user",
      content: "pedido salvo",
      created_at: "2026-11-06T12:00:00Z",
    },
  ],
  calls: [],
  material_card: null,
};
function SwitchPersona() {
  const { switchPersona } = useAuth();
  return React.createElement("button", {
    "aria-label": "Trocar persona",
    onClick: () => switchPersona("GESTOR_CADASTRO"),
  });
}
test("retoma ao voltar/recarregar, usa versão do servidor e Nova conversa preserva histórico", async () => {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
  const originalFetch = globalThis.fetch;
  const writes: Record<string, unknown>[] = [];
  const reads: string[] = [];
  let current = { ...saved };
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
          {
            error: {
              code: "VERSION_CONFLICT",
              message: "Atualize a conversa",
              details: {},
              request_id: "test",
            },
          },
          { status: 409 },
        );
      }
      reads.push(url);
      return Response.json(
        url.includes("/sessions/")
          ? current
          : {
              items: [
                { id: saved.session_id, title: "Pedido salvo", updated_at: "2026-11-06T12:00:00Z" },
              ],
              next_cursor: null,
            },
      );
    },
  });
  let view!: ReactTestRenderer;
  const mount = async () => {
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
  };
  const select = async () => {
    await act(async () =>
      view.root
        .findByProps({ "aria-label": "Conversas salvas" })
        .props.onChange({ target: { value: saved.session_id } }),
    );
  };
  const send = async () => {
    await act(async () =>
      view.root.findByType("textarea").props.onChange({ target: { value: "continuar" } }),
    );
    await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  };
  try {
    await mount();
    await select();
    assert.match(JSON.stringify(view.toJSON()), /pedido salvo/);
    await send();
    assert.equal(writes[0].session_id, saved.session_id);
    assert.equal(writes[0].expected_session_version, 4);
    assert.equal(writes[0].center_code, "1100");
    current = { ...saved, session_version: 7 };
    await act(async () =>
      view.root.findByProps({ "aria-label": "Atualizar conversa" }).props.onClick(),
    );
    await send();
    assert.equal(writes[1].expected_session_version, 7);
    await act(async () => view.unmount());
    await mount();
    assert.doesNotMatch(JSON.stringify(view.toJSON()), /pedido salvo/);
    await select();
    assert.match(JSON.stringify(view.toJSON()), /pedido salvo/);
    await act(async () =>
      view.root
        .findAllByType("button")
        .find((button) => button.children.includes(" Nova conversa"))!
        .props.onClick(),
    );
    await send();
    assert.equal(writes[2].session_id, null);
    assert.equal(writes[2].expected_session_version, 0);
    await select();
    await act(async () =>
      view.root.findByProps({ "aria-label": "Trocar persona" }).props.onClick(),
    );
    assert.doesNotMatch(JSON.stringify(view.toJSON()), /pedido salvo/);
    assert.ok(reads.filter((url) => url.endsWith("/sessions/saved-chat")).length >= 3);
  } finally {
    await act(async () => view.unmount());
    globalThis.fetch = originalFetch;
    delete process.env.NEXT_PUBLIC_DATA_SOURCE;
  }
});

test("processamento exige atualização e leitura tardia não recupera conversa descartada", async () => {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
  const originalFetch = globalThis.fetch;
  let resolveRead!: (value: Response) => void;
  let response = { ...saved, processing: true, submission: null };
  let delay = false;
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
    fetch: async (url: string) => {
      if (url.includes("/sessions/"))
        return delay
          ? new Promise<Response>((resolve) => {
              resolveRead = resolve;
            })
          : Response.json(response);
      return Response.json({
        items: [
          { id: saved.session_id, title: "Pedido salvo", updated_at: "2026-11-06T12:00:00Z" },
        ],
        next_cursor: null,
      });
    },
  });
  let view!: ReactTestRenderer;
  const select = () =>
    act(async () => {
      void view.root
        .findByProps({ "aria-label": "Conversas salvas" })
        .props.onChange({ target: { value: saved.session_id } });
    });
  try {
    await act(async () => {
      view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
    });
    await select();
    assert.match(JSON.stringify(view.toJSON()), /está processando um turno/);
    assert.equal(view.root.findByType("textarea").props.disabled, true);
    response = { ...response, processing: false, session_version: 5 };
    await act(async () =>
      view.root.findByProps({ "aria-label": "Atualizar conversa" }).props.onClick(),
    );
    assert.equal(view.root.findByType("textarea").props.disabled, false);
    delay = true;
    await select();
    await act(async () =>
      view.root
        .findAllByType("button")
        .find((button) => button.children.includes(" Nova conversa"))!
        .props.onClick(),
    );
    await act(async () => resolveRead(Response.json(saved)));
    assert.doesNotMatch(JSON.stringify(view.toJSON()), /pedido salvo/);
    assert.equal(view.root.findByProps({ "aria-label": "Conversas salvas" }).props.value, "");
  } finally {
    await act(async () => view.unmount());
    globalThis.fetch = originalFetch;
    delete process.env.NEXT_PUBLIC_DATA_SOURCE;
  }
});
