import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { ChatPage } from "../src/features/chat/ChatPage";
import { can, meFor, ROLE_PERMISSIONS } from "../src/lib/permissions";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const TURN = {
  request_id: "req-diagnostico",
  session_id: "sessao-1",
  session_version: 1,
  order_id: null,
  status: "NEEDS_INPUT",
  assistant_message: "Qual é a classe de resistência?",
  tool_calls: [
    {
      id: "tool-call-001",
      name: "validate_and_format_pdm",
      transport: "MCP_STDIO",
      input: { pdm_class_id: "PDM001" },
      status: "SUCCEEDED",
      duration_ms: 3.2,
      result: { validation_status: "INCOMPLETE" },
    },
  ],
  material_card: {
    pdm_class_id: "PDM001",
    pdm_class_name: "PARAFUSO SEXTAVADO",
    attributes: { BITOLA: "M12" },
    pdm_description: null,
    validation_status: "INCOMPLETE",
    missing_attributes: ["CLASSE RESISTENCIA"],
    ncm: { suggested: null, status: "PENDING_VALIDATION" },
    duplicate_check_status: "PENDING",
    similar_candidates: [],
    can_submit: false,
  },
};

async function renderAs(persona: string) {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
  const originalFetch = globalThis.fetch;
  Object.assign(globalThis, {
    window: {
      matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
      addEventListener() {},
      removeEventListener() {},
    },
    document: { documentElement: { dataset: {} } },
    localStorage: { getItem: (key: string) => (key === "vx-demo-persona" ? persona : null) },
    fetch: (_url: unknown, init: RequestInit) =>
      Promise.resolve(
        Response.json(init.method === "GET" ? { items: [], next_cursor: null } : TURN),
      ),
  });
  let view!: ReactTestRenderer;
  await act(async () => {
    view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
  });
  await act(async () =>
    view.root.findByType("textarea").props.onChange({ target: { value: "parafuso M12" } }),
  );
  await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  return {
    view,
    async cleanup() {
      await act(async () => view.unmount());
      globalThis.fetch = originalFetch;
      delete process.env.NEXT_PUBLIC_DATA_SOURCE;
    },
  };
}

for (const persona of ["SOLICITANTE_OPERACAO", "GESTOR_CADASTRO", "AUDITOR_FISCAL"]) {
  test(`${persona} não vê a aba, o contador nem os detalhes das chamadas MCP`, async () => {
    const { view, cleanup } = await renderAs(persona);
    try {
      const rendered = JSON.stringify(view.toJSON());
      assert.match(rendered, /Qual é a classe de resistência/);
      assert.match(rendered, /PARAFUSO SEXTAVADO/);
      assert.doesNotMatch(rendered, /Chamadas MCP|validate_and_format_pdm|MCP_STDIO/);
    } finally {
      await cleanup();
    }
  });
}

test("Dev/TI vê a aba Chamadas MCP com o contador e os detalhes do turno", async () => {
  const { view, cleanup } = await renderAs("DEV_TI");
  try {
    assert.match(JSON.stringify(view.toJSON()), /Chamadas MCP/);
    const tab = view.root
      .findAllByProps({ role: "tab" })
      .find((button) => button.findAllByType("span").length > 0)!;
    assert.equal(tab.findByType("span").children.join(""), "1");
    await act(async () => tab.props.onClick());
    assert.match(JSON.stringify(view.toJSON()), /validate_and_format_pdm/);
  } finally {
    await cleanup();
  }
});

test("só a role Dev/TI tem diagnóstico, sem poderes de aprovação ou publicação", () => {
  assert.equal(can(meFor("DEV_TI"), "chat:diagnostics"), true);
  for (const persona of ["SOLICITANTE_OPERACAO", "GESTOR_CADASTRO", "AUDITOR_FISCAL"] as const)
    assert.equal(can(meFor(persona), "chat:diagnostics"), false);
  const decisions = [
    "orders:decide",
    "merge:decide",
    "enrichment:decide",
    "ncm:decide",
    "batch:run",
  ];
  assert.deepEqual(
    ROLE_PERMISSIONS.ROLE_DEV_TI.filter((permission) => decisions.includes(permission)),
    [],
  );
});
