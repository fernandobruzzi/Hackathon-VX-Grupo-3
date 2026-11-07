import assert from "node:assert/strict";
import { test, type TestContext } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { PathnameContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { AppShell } from "../src/components/shell/AppShell";
import { QueuePage } from "../src/features/sanitization/QueuePage";
import { meFor } from "../src/lib/permissions";
import { pendingCounts } from "../src/mocks/queue";
import type { PersonaLabel } from "../src/types/api";

Object.assign(globalThis, { React, IS_REACT_ACT_ENVIRONMENT: true });
type Scenario = "empty" | "nonempty" | "paginated" | "unavailable";
const proposal = {
  id: "persisted-proposal",
  version: 1,
  proposal_type: "MERGE",
  status: "PENDING",
  title: "Proposta persistida",
  material_codes: ["001", "002"],
  suggested_primary_code: "001",
  identity: { mode: "TECHNICAL_ATTRIBUTES", summary: "Mesmo material" },
  technical_review_status: "PENDING",
  fiscal_review_status: "PENDING",
  conflicts: [],
  allowed_actions: [],
  ranking_score: 1,
  created_at: "2026-11-06T00:00:00Z",
};

async function setup(t: TestContext, mode: "api" | "mock", scenario: Scenario = "empty") {
  const originalEnv = process.env.NEXT_PUBLIC_DATA_SOURCE;
  const globals = {
    fetch: globalThis.fetch,
    window: globalThis.window,
    document: globalThis.document,
    localStorage: globalThis.localStorage,
    self: globalThis.self,
  };
  process.env.NEXT_PUBLIC_DATA_SOURCE = mode;
  let persona: PersonaLabel = "GESTOR_CADASTRO";
  let current!: ReturnType<typeof useAuth>;
  const queries: string[] = [];
  Object.assign(globalThis, {
    self: globalThis,
    window: { location: { pathname: "/saneamento/" } },
    document: { documentElement: { dataset: {} } },
    localStorage: {
      getItem: (key: string) => (key === "vx-demo-persona" ? persona : null),
      setItem: (_key: string, value: PersonaLabel) => {
        persona = value;
      },
      removeItem() {},
    },
    fetch: async (url: string, init: RequestInit) => {
      if (url === "/api/v1/auth/config") return Response.json({ mode: "local" });
      if (url === "/api/v1/auth/local-session") persona = JSON.parse(init.body as string).persona;
      if (url === "/api/v1/auth/me" || url === "/api/v1/auth/local-session")
        return Response.json(meFor(persona));
      queries.push(url);
      assert.match(url, /^\/api\/v1\/sanitization\/queue/);
      if (scenario === "unavailable") return Response.json({}, { status: 503 });
      return Response.json({
        items: scenario === "empty" ? [] : [proposal],
        next_cursor: scenario === "paginated" ? "another-page" : null,
      });
    },
  });
  function Probe() {
    current = useAuth();
    return null;
  }
  const router = {
    back() {},
    forward() {},
    refresh() {},
    hmrRefresh() {},
    push() {},
    replace() {},
    prefetch() {},
  };
  let view!: ReactTestRenderer;
  await act(async () => {
    view = create(
      React.createElement(
        AppRouterContext.Provider,
        { value: router },
        React.createElement(
          PathnameContext.Provider,
          { value: "/saneamento/" },
          React.createElement(
            AuthProvider,
            null,
            React.createElement(Probe),
            React.createElement(AppShell, null, React.createElement(QueuePage)),
          ),
        ),
      ),
    );
  });
  t.after(async () => {
    await act(async () => view.unmount());
    Object.assign(globalThis, globals);
    if (originalEnv === undefined) delete process.env.NEXT_PUBLIC_DATA_SOURCE;
    else process.env.NEXT_PUBLIC_DATA_SOURCE = originalEnv;
  });
  return {
    view,
    queries,
    get auth() {
      return current;
    },
    link() {
      return view.root
        .findByType("aside")
        .findAllByType("a")
        .find((a) => a.props.href.replace(/\/$/, "") === "/saneamento")!;
    },
    badges() {
      return this.link()
        .findAllByType("span")
        .filter((span) => /^\d+$/.test(span.children.join("")));
    },
  };
}

for (const scenario of ["empty", "nonempty", "paginated", "unavailable"] as const) {
  test(`navegação API omite total indisponível com fila ${scenario}, inclusive após trocar persona`, async (t) => {
    const h = await setup(t, "api", scenario);
    assert.ok(h.link(), "link da fila permanece disponível");
    assert.equal(h.badges().length, 0, "não mostra mock, zero ou tamanho de página como total");
    assert.ok(h.queries.length > 0, "a fila real consultou a API");
    if (scenario === "empty") assert.match(JSON.stringify(h.view.toJSON()), /Fila vazia/);
    if (scenario === "nonempty" || scenario === "paginated")
      assert.match(JSON.stringify(h.view.toJSON()), /Proposta persistida/);
    if (scenario === "paginated") assert.match(JSON.stringify(h.view.toJSON()), /Carregar mais/);
    await act(async () => {
      h.auth.switchPersona("AUDITOR_FISCAL");
    });
    assert.equal(h.auth.me?.user.roles[0], "ROLE_AUDITOR_FISCAL");
    assert.ok(h.link());
    assert.equal(h.badges().length, 0);
    const mobile = h.view.root.findByProps({ "aria-label": "Navegação" });
    assert.ok(
      mobile.findAllByType("option").some((option) => option.props.value === "/saneamento/"),
    );
  });
}

test("modo mock identifica as contagens técnicas e fiscais como simuladas", async (t) => {
  const h = await setup(t, "mock");
  assert.equal(h.badges().length, 1);
  assert.deepEqual(h.badges()[0].children, [String(pendingCounts.technical)]);
  assert.equal(h.badges()[0].props.role, "status");
  assert.equal(h.badges()[0].props.title, "Contagem simulada");
  assert.equal(
    h.badges()[0].props["aria-label"],
    `${pendingCounts.technical} pendências simuladas`,
  );
  await act(async () => {
    h.auth.switchPersona("AUDITOR_FISCAL");
  });
  assert.deepEqual(h.badges()[0].children, [String(pendingCounts.fiscal)]);
  assert.equal(h.badges()[0].props["aria-label"], `${pendingCounts.fiscal} pendências simuladas`);
  assert.equal(h.queries.length, 0, "demonstração não consulta a fila da API");
});
