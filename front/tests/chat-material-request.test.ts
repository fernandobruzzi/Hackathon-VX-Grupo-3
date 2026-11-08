import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer, type ReactTestInstance } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { meFor } from "../src/lib/permissions";
import { ChatPage } from "../src/features/chat/ChatPage";

(globalThis as Record<string, unknown>).React = React;
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as Record<string, unknown>).self = globalThis;
const sid = "23823823-0000-4000-8000-000000000001";
const textOf = (node: ReactTestInstance): string =>
  node.children.map((child) => (typeof child === "string" ? child : textOf(child))).join("");

async function setup(
  mode: "existing" | "registration" | "review",
  lost = false,
  delayed = false,
  readOnly = false,
  warnOpen = false,
) {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "api";
  const originalFetch = globalThis.fetch;
  const me = meFor("SOLICITANTE_OPERACAO");
  if (readOnly)
    me.permissions = me.permissions.filter((permission) => permission !== "requests:create");
  me.scope = { center_codes: ["1200"], center_names: { "1200": "Fábrica de testes" } };
  const card = {
    pdm_class_id: "PDM001",
    pdm_class_name: "PARAFUSO SEXTAVADO",
    attributes: {},
    pdm_description: null,
    validation_status: mode === "review" ? "INCOMPLETE" : "VALID",
    missing_attributes: [],
    ncm: { suggested: null, status: "PENDING_VALIDATION" },
    duplicate_check_status:
      mode === "existing" ? "MATCH_FOUND" : mode === "registration" ? "NO_MATCH" : "PENDING",
    can_submit: mode === "registration",
    similar_candidates: [],
    ...(mode === "existing"
      ? {
          existing: {
            material_code: "23800001",
            status: "ATIVO",
            pdm_description: "Parafuso já identificado",
            match_type: "EXACT_IDENTITY",
            reason: "Mesmo item.",
            inventory: [],
          },
        }
      : {}),
  };
  const row = {
    id: "23823823-0000-4000-8000-000000000002",
    protocol: "SM-00000238",
    requester_user_id: me.user.id,
    original_text: "Parafuso M12x50, resistência 8.8",
    material_id: mode === "existing" ? "23823823-0000-4000-8000-000000000003" : null,
    registration_order_id: mode === "registration" ? "23823823-0000-4000-8000-000000000004" : null,
    quantity: "3.000000",
    unit: "PC",
    center_code: "1200",
    chat_session_id: sid,
    status:
      mode === "existing"
        ? "EM_ATENDIMENTO"
        : mode === "registration"
          ? "AGUARDANDO_CADASTRO"
          : "EM_IDENTIFICACAO",
    closure_reason: null,
    version: 1,
    can_cancel: true,
    history: [],
    created_at: "2026-11-08T00:00:00Z",
    updated_at: "2026-11-08T00:00:00Z",
  };
  const response = { session_id: sid, session_version: 2, material_request: row };
  const writes: { body: Record<string, unknown>; key: string | null }[] = [];
  let saved = false;
  let resolve!: (response: Response) => void;
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
      if (url.endsWith("/chat/message"))
        return Response.json({
          request_id: "test",
          session_id: sid,
          session_version: 1,
          order_id: null,
          status:
            mode === "existing"
              ? "EXISTING"
              : mode === "registration"
                ? "READY_TO_SUBMIT"
                : "NEEDS_INPUT",
          assistant_message: "Confira a ficha e informe a quantidade e a unidade.",
          tool_calls: [],
          material_card: card,
        });
      if (url.endsWith("/request-material")) {
        writes.push({
          body: JSON.parse(init.body as string),
          key: new Headers(init.headers).get("Idempotency-Key"),
        });
        if (warnOpen && !writes.at(-1)!.body.acknowledge_open_requests)
          return Response.json(
            {
              error: {
                code: "OPEN_REQUESTS_EXIST",
                message:
                  "Já existe solicitação aberta deste material para este centro. Confirme para criar outra.",
                request_id: "test",
                details: {},
              },
            },
            { status: 409 },
          );
        saved = true;
        if (delayed)
          return new Promise<Response>((done) => {
            resolve = done;
          });
        if (lost) throw new TypeError("resposta perdida");
        return Response.json(response);
      }
      if (url.includes("/sessions/"))
        return Response.json({
          session_id: sid,
          session_version: saved ? 2 : 1,
          center_code: "1200",
          processing: false,
          order_id: row.registration_order_id,
          submission:
            mode === "registration" && saved
              ? {
                  session_id: sid,
                  session_version: 2,
                  order_id: row.registration_order_id,
                  status: "READY_FOR_REVIEW",
                }
              : null,
          material_request_submission: saved ? response : null,
          messages: [],
          calls: [],
          material_card: card,
        });
      return Response.json({
        items: [{ id: sid, title: "Solicitação salva", updated_at: "2026-11-08T00:00:00Z" }],
        next_cursor: null,
      });
    },
  });
  let view!: ReactTestRenderer;
  await act(async () => {
    view = create(React.createElement(AuthProvider, null, React.createElement(ChatPage)));
  });
  await act(async () =>
    view.root.findByType("textarea").props.onChange({ target: { value: row.original_text } }),
  );
  await act(async () => view.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  const button = (label: string) =>
    view.root.findAllByType("button").find((node) => textOf(node).trim() === label)!;
  const fill = async () => {
    await act(async () => {
      view.root.findByProps({ placeholder: "Ex.: 10" }).props.onChange({ target: { value: "3" } });
      view.root.findByProps({ placeholder: "Ex.: PC" }).props.onChange({ target: { value: "PC" } });
    });
  };
  return {
    view,
    writes,
    response,
    button,
    fill,
    resolve: () => resolve(Response.json(response)),
    json: () => JSON.stringify(view.toJSON()),
    cleanup: async () => {
      await act(async () => view.unmount());
      globalThis.fetch = originalFetch;
      delete process.env.NEXT_PUBLIC_DATA_SOURCE;
    },
  };
}

for (const mode of ["existing", "registration", "review"] as const) {
  test(`chat confirma solicitação ${mode} somente depois de quantidade/unidade e ação explícita`, async () => {
    const t = await setup(mode);
    try {
      assert.equal(
        t.writes.length,
        0,
        "nem a medida M12x50 nem a resistência 8.8 viram quantidade",
      );
      assert.match(t.json(), /Fábrica de testes/);
      await act(async () => t.button("Confirmar solicitação de material").props.onClick());
      assert.equal(t.writes.length, 0);
      assert.match(t.json(), /quantidade positiva/);
      await t.fill();
      assert.equal(t.view.root.findAllByProps({ role: "alert" }).length, 0);
      await act(async () => t.button("Confirmar solicitação de material").props.onClick());
      assert.equal(t.writes.length, 1);
      assert.deepEqual(t.writes[0].body, {
        acknowledge_open_requests: false,
        expected_session_version: 1,
        quantity: "3",
        unit: "PC",
      });
      assert.ok(t.writes[0].key);
      assert.match(t.json(), /SM-00000238/);
      assert.equal(t.view.root.findByType("textarea").props.disabled, true);
      assert.equal(t.view.root.findAllByProps({ placeholder: "Ex.: 10" }).length, 0);
    } finally {
      await t.cleanup();
    }
  });
}

test("resposta perdida é reconciliada pelo histórico sem duplicar a confirmação", async () => {
  const t = await setup("registration", true);
  try {
    await t.fill();
    await act(async () => t.button("Confirmar solicitação de material").props.onClick());
    assert.equal(t.writes.length, 1);
    assert.match(t.json(), /SM-00000238/);
    assert.equal(t.view.root.findByType("textarea").props.disabled, true);
  } finally {
    await t.cleanup();
  }
});

test("confirmação tardia não restaura a conversa anterior depois de Nova conversa", async () => {
  const t = await setup("review", false, true);
  try {
    await t.fill();
    let pending!: Promise<void>;
    await act(async () => {
      pending = t.button("Confirmar solicitação de material").props.onClick();
    });
    assert.equal(t.writes.length, 1);
    assert.equal(t.button("Aguarde…").props.disabled, true);
    await act(async () => t.button("Nova conversa").props.onClick());
    await act(async () => {
      t.resolve();
      await pending;
    });
    assert.doesNotMatch(t.json(), /SM-00000238/);
    assert.equal(t.view.root.findByType("textarea").props.disabled, false);
  } finally {
    await t.cleanup();
  }
});

test("histórico de cadastro novo restaura o protocolo da solicitação principal", async () => {
  const t = await setup("registration");
  try {
    await t.fill();
    await act(async () => t.button("Confirmar solicitação de material").props.onClick());
    await act(async () => t.button("Nova conversa").props.onClick());
    assert.doesNotMatch(t.json(), /SM-00000238/);
    await act(async () =>
      t.view.root
        .findByProps({ "aria-label": "Retomar conversa: Solicitação salva" })
        .props.onClick(),
    );
    assert.match(t.json(), /SM-00000238/);
    assert.equal(t.view.root.findByType("textarea").props.disabled, true);
  } finally {
    await t.cleanup();
  }
});

test("conversa sem permissão de criação não oferece confirmação", async () => {
  const t = await setup("review", false, false, true);
  try {
    assert.equal(t.view.root.findAllByProps({ placeholder: "Ex.: 10" }).length, 0);
    assert.equal(t.writes.length, 0);
    assert.match(t.json(), /não criar solicitações/);
  } finally {
    await t.cleanup();
  }
});

test("aviso de necessidade aberta exige confirmação explícita antes de criar outra", async () => {
  const t = await setup("existing", false, false, false, true);
  try {
    await t.fill();
    await act(async () => t.button("Confirmar solicitação de material").props.onClick());
    assert.equal(t.writes.length, 1);
    assert.match(t.json(), /Já existe solicitação aberta/);
    assert.doesNotMatch(t.json(), /SM-00000238/);
    assert.equal(t.button("Confirmar solicitação de material").props.disabled, true);
    await act(async () =>
      t.view.root.findByProps({ type: "checkbox" }).props.onChange({ target: { checked: true } }),
    );
    assert.equal(t.writes.length, 1);
    await act(async () => t.button("Confirmar solicitação de material").props.onClick());
    assert.equal(t.writes.length, 2);
    assert.equal(t.writes[1].body.acknowledge_open_requests, true);
    assert.match(t.json(), /SM-00000238/);
  } finally {
    await t.cleanup();
  }
});
