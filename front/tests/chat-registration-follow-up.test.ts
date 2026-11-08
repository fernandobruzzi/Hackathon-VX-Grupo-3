import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer, type ReactTestInstance } from "react-test-renderer";
import { ChatPage } from "../src/features/chat/ChatPage";
import { AuthProvider } from "../src/lib/auth";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const textOf = (node: ReactTestInstance): string =>
  node.children.map((child) => (typeof child === "string" ? child : textOf(child))).join("");

const card = {
  pdm_class_id: "PDM001",
  pdm_class_name: "Parafuso sextavado",
  attributes: { BITOLA: "M12" },
  pdm_description: "PARAFUSO SEXTAVADO M12",
  validation_status: "VALID",
  missing_attributes: [],
  ncm: { suggested: null, status: "PENDING_VALIDATION" },
  duplicate_check_status: "NO_MATCH",
  similar_candidates: [],
  can_submit: true,
};
const registration = {
  session_id: "cadastro-1",
  session_version: 2,
  order_id: "pedido-1",
  status: "READY_FOR_REVIEW",
};

test("confirma envio, encerra em leitura e começa um cadastro vazio pelo histórico", async () => {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
  const originalFetch = globalThis.fetch;
  let legacy = false;
  const materialRequest = {
    session_id: "cadastro-1",
    session_version: 2,
    material_request: {
      id: "request-1",
      protocol: "SM-00000001",
      status: "AGUARDANDO_CADASTRO",
      quantity: "3.000000",
      unit: "PC",
      registration_order_id: "pedido-1",
    },
  };
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  Object.assign(globalThis, {
    self: globalThis,
    window: {
      matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
      addEventListener() {},
      removeEventListener() {},
    },
    document: { documentElement: { dataset: {} } },
    localStorage: {
      getItem: (key: string) => (key === "vx-demo-persona" ? "SOLICITANTE_OPERACAO" : null),
    },
    fetch: async (path: string, init: RequestInit) => {
      if (init.method === "POST") {
        writes.push({ path, body: JSON.parse(init.body as string) });
        if (path.endsWith("/request-material")) return Response.json(materialRequest);
        return Response.json({
          request_id: "req-1",
          session_id: writes.length === 1 ? "cadastro-1" : "cadastro-2",
          session_version: 1,
          order_id: null,
          status: "READY_TO_SUBMIT",
          assistant_message: "Ficha pronta.",
          tool_calls: [],
          material_card: card,
        });
      }
      if (path.includes("/sessions/cadastro-1"))
        return Response.json({
          ...registration,
          center_code: "1100",
          processing: false,
          calls: [],
          messages: [
            { id: "msg-1", author: "user", content: "Parafuso M12", created_at: "2026-11-08" },
          ],
          material_card: { ...card, can_submit: false },
          submission: registration,
          material_request_submission: legacy ? null : materialRequest,
        });
      return Response.json({
        items: [{ id: "cadastro-1", title: "Parafuso", updated_at: "2026-11-08T12:00:00Z" }],
        next_cursor: null,
      });
    },
  });
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
    });
    const click = async (label: string) => {
      const button = view.root
        .findAllByType("button")
        .find((item) => item.props["aria-label"] === label || textOf(item).trim() === label);
      assert.ok(button, label);
      await act(async () => button.props.onClick());
    };
    const send = async (value: string) => {
      await act(async () => view.root.findByType("textarea").props.onChange({ target: { value } }));
      await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
    };
    const rendered = () => JSON.stringify(view.toJSON());

    await act(async () =>
      view.root.findByType("select").props.onChange({ target: { value: "1100" } }),
    );
    await send("Parafuso M12");
    assert.doesNotMatch(rendered(), /Quer fazer mais cadastros/);
    await act(async () => {
      view.root.findByProps({ placeholder: "Ex.: 10" }).props.onChange({ target: { value: "3" } });
      view.root.findByProps({ placeholder: "Ex.: PC" }).props.onChange({ target: { value: "PC" } });
    });
    await click("Confirmar solicitação de material");
    assert.match(rendered(), /Solicitação SM-00000001 registrada/);
    assert.match(rendered(), /Quer fazer outra solicitação/);
    assert.equal(view.root.findByType("textarea").props.disabled, true);

    await click("Encerrar");
    assert.match(rendered(), /Conversa encerrada/);
    assert.match(rendered(), /Parafuso M12/);
    assert.doesNotMatch(rendered(), /Quer fazer outra solicitação/);
    assert.equal(view.root.findByType("textarea").props.disabled, true);
    assert.equal(writes.length, 2);

    await click("Retomar conversa: Parafuso");
    assert.match(rendered(), /Quer fazer outra solicitação/);
    await click("Nova solicitação");
    assert.doesNotMatch(rendered(), /Parafuso M12|Ficha pronta|pedido-1/);
    assert.equal(view.root.findByType("select").props.value, "1100");
    assert.equal(view.root.findByType("textarea").props.disabled, false);
    assert.equal(view.root.findByType("textarea").props.value, "");
    assert.equal(writes.length, 2);

    await send("Rolamento 6205");
    assert.equal(writes[2].body.session_id, null);
    assert.equal(writes[2].body.expected_session_version, 0);
    assert.equal(writes[2].body.center_code, "1100");
    legacy = true;
    await click("Retomar conversa: Parafuso");
    assert.match(rendered(), /Pedido enviado para revisão/);
    assert.match(rendered(), /Quer fazer mais cadastros/);
    await click("Encerrar");
    assert.match(rendered(), /Conversa encerrada/);
  } finally {
    if (view) await act(async () => view.unmount());
    globalThis.fetch = originalFetch;
    delete process.env.NEXT_PUBLIC_DATA_SOURCE;
  }
});
