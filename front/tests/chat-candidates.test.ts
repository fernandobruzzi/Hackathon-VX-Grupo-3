import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { ChatPage } from "../src/features/chat/ChatPage";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const LONG =
  "PARAFUSO SEXTAVADO M12 X 50 ACO CARBONO CLASSE 8.8 ZINCADO BRANCO DIN 933 ROSCA TOTAL PARA FIXACAO ESTRUTURAL";
const CANDIDATES = [
  { material_code: "00001234", status: "ATIVO", pdm_description: LONG, active_code_target: null },
  {
    material_code: "00005678",
    status: "BLOQUEADO",
    pdm_description: "PARAFUSO SEXTAVADO M12 X 50 ACO CARBONO",
    active_code_target: "00001234",
  },
];

const turn = (version: number, candidates: typeof CANDIDATES, message: string) => ({
  request_id: `req-${version}`,
  session_id: "sessao-1",
  session_version: version,
  order_id: null,
  status: "NEEDS_INPUT",
  assistant_message: message,
  tool_calls: [],
  material_card: {
    pdm_class_id: "PDM001",
    pdm_class_name: "PARAFUSO SEXTAVADO",
    attributes: { BITOLA: "M12" },
    pdm_description: null,
    validation_status: "VALID",
    missing_attributes: [],
    ncm: { suggested: null, status: "PENDING_VALIDATION" },
    duplicate_check_status: "PENDING",
    similar_candidates: candidates,
    can_submit: false,
  },
});

const ASK =
  "Encontrei 2 itens parecidos na base. Se o seu item estiver na lista, escolha “É este” ou responda com o código. Se nenhum corresponder, responda “Nenhum desses é o meu item”.";

async function setup(responses: unknown[]) {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
  const posted: Record<string, unknown>[] = [];
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
    fetch: (_url: unknown, init: RequestInit) => {
      if (init.method === "GET")
        return Promise.resolve(Response.json({ items: [], next_cursor: null }));
      posted.push(JSON.parse(init.body as string));
      return Promise.resolve(Response.json(responses[posted.length - 1]));
    },
  });
  let view!: ReactTestRenderer;
  await act(async () => {
    view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
  });
  await act(async () =>
    view.root.findByType("textarea").props.onChange({ target: { value: "parafuso M12x50" } }),
  );
  await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  return {
    view,
    posted,
    async cleanup() {
      await act(async () => view.unmount());
      globalThis.fetch = originalFetch;
      delete process.env.NEXT_PUBLIC_DATA_SOURCE;
    },
  };
}

const conversation = (view: ReactTestRenderer) =>
  view.root.findByProps({ "aria-label": "Mensagens da conversa" });
const text = (node: ReactTestInstance) => JSON.stringify(node.children.map(flatten));
function flatten(node: ReactTestInstance | string): unknown {
  return typeof node === "string" ? node : node.children.map(flatten);
}
const buttons = (node: ReactTestInstance, label: string) =>
  node.findAllByType("button").filter((button) => text(button).includes(label));

test("itens parecidos aparecem em tópicos na conversa, com código, descrição e status", async () => {
  const { view, cleanup } = await setup([turn(1, CANDIDATES, ASK)]);
  try {
    const list = conversation(view).findByProps({ "aria-label": "Itens parecidos na base" });
    const items = list.findAllByType("li");
    assert.equal(items.length, 2);
    CANDIDATES.forEach((candidate, index) => {
      assert.match(text(items[index]), new RegExp(candidate.material_code));
      assert.ok(text(items[index]).includes(candidate.pdm_description));
      const badge = items[index].findAll((node) => node.props.value === candidate.status);
      assert.ok(badge.length > 0, `status ${candidate.status} visível`);
    });
    assert.match(text(items[1]), /o código a usar é/);
    // O texto da mensagem não concatena códigos: eles ficam só nos tópicos.
    const paragraph = conversation(view)
      .findAllByType("p")
      .find((p) => text(p).includes("Encontrei"))!;
    assert.doesNotMatch(text(paragraph), /00001234|00005678/);
    assert.match(text(conversation(view)), /Nenhum corresponde ao que você procura/);
  } finally {
    await cleanup();
  }
});

test("“É este” na conversa envia a escolha estruturada e some da resposta antiga", async () => {
  const { view, posted, cleanup } = await setup([
    turn(1, CANDIDATES, ASK),
    turn(2, [], "Esse item já existe."),
  ]);
  try {
    await act(async () => buttons(conversation(view), "É este")[0].props.onClick());
    assert.deepEqual(posted[1].action, { type: "PICK_CANDIDATE", material_code: "00001234" });
    assert.equal(posted[1].message, "É o item 00001234");
    assert.equal(buttons(conversation(view), "É este").length, 0);
    assert.equal(buttons(conversation(view), "Nenhum desses").length, 0);
  } finally {
    await cleanup();
  }
});

test("“Nenhum desses é o meu item” na conversa descarta os itens exibidos", async () => {
  const { view, posted, cleanup } = await setup([turn(1, CANDIDATES, ASK), turn(2, [], "Ok.")]);
  try {
    await act(async () => buttons(conversation(view), "Nenhum desses")[0].props.onClick());
    assert.deepEqual(posted[1].action, { type: "DISMISS_CANDIDATES" });
  } finally {
    await cleanup();
  }
});

test("conversa e ficha listam os mesmos itens com as mesmas ações", async () => {
  const { view, cleanup } = await setup([turn(1, CANDIDATES, ASK)]);
  try {
    const lists = view.root.findAllByProps({ "aria-label": "Itens parecidos na base" });
    assert.equal(lists.length, 2, "uma lista na conversa e outra na ficha");
    const codes = (list: ReactTestInstance) =>
      list.findAllByType("li").map((li) => text(li).match(/\d{8}/)![0]);
    assert.deepEqual(codes(lists[0]), codes(lists[1]));
    assert.equal(buttons(lists[0], "É este").length, buttons(lists[1], "É este").length);
  } finally {
    await cleanup();
  }
});
