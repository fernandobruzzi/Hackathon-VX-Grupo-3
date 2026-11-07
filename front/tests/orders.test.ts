import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { OrdersPage } from "../src/features/orders/OrdersPage";
import { meFor } from "../src/lib/permissions";

Object.assign(globalThis, {
  React,
  self: globalThis,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: { location: { pathname: "/pedidos" } },
  document: { documentElement: { dataset: {} } },
});

for (const pending of [false, true]) {
  test(`identidade pendente bloqueia aprovação, preserva rejeição: ${pending}`, async () => {
    const previousFetch = globalThis.fetch;
    globalThis.fetch = async (url) => {
      if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
      if (String(url).endsWith("/auth/me")) return Response.json(meFor("GESTOR_CADASTRO"));
      return Response.json({
        items: [
          {
            id: "identity-review",
            origin: "CHAT",
            requester: "Solicitante",
            original_text: "MANTO METSO N1234567",
            center_code: "1300",
            pdm_class_id: "PDM110",
            status: "READY_FOR_REVIEW",
            missing_attributes: pending
              ? ["REVISAO DE IDENTIDADE: REVISAO_DE_PECA_NAO_CONFIRMADA"]
              : [],
            material_code: null,
            updated_at: "2026-11-06T00:00:00Z",
            version: 1,
          },
        ],
        next_cursor: null,
      });
    };
    let view!: ReactTestRenderer;
    try {
      await act(async () => {
        view = create(React.createElement(AuthProvider, null, React.createElement(OrdersPage)));
      });
      const button = (label: string) =>
        view.root
          .findAllByType("button")
          .find((item) =>
            item.children.some((child) => typeof child === "string" && child.includes(label)),
          );
      assert.equal(button("Aprovar parte técnica")?.props.disabled, pending);
      assert.equal(button("Rejeitar")?.props.disabled, false);
    } finally {
      await act(async () => view?.unmount());
      globalThis.fetch = previousFetch;
    }
  });
}

test("pedidos percorre mais de 100 itens e reinicia por aba e identidade", async () => {
  const previousFetch = globalThis.fetch;
  const queries: URLSearchParams[] = [];
  let session = meFor("GESTOR_CADASTRO");
  let holdMore = false;
  let releaseMore!: (response: Response) => void;
  let auth!: ReturnType<typeof useAuth>;
  const Harness = () => {
    auth = useAuth();
    return React.createElement(OrdersPage);
  };
  const order = (i: number) => ({
    id: `pedido-${i}`,
    origin: "CHAT",
    requester: "Mesmo nome",
    original_text: `Texto ${i}`,
    center_code: "1300",
    pdm_class_id: null,
    status: "INCOMPLETE",
    missing_attributes: ["BITOLA"],
    material_code: null,
    updated_at: "2026-11-06T00:00:00Z",
    version: 1,
  });
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
    if (String(url).endsWith("/auth/me")) return Response.json(session);
    const query = new URL(String(url), "http://localhost").searchParams;
    queries.push(query);
    const offset = Number(query.get("cursor") ?? 0);
    if (offset && holdMore)
      return new Promise<Response>((resolve) => {
        releaseMore = resolve;
      });
    return Response.json({
      items: Array.from({ length: offset ? 5 : 100 }, (_, i) => order(offset + i)),
      next_cursor: offset ? null : "100",
    });
  };
  let view!: ReactTestRenderer;
  const click = async (label: string) => {
    await act(async () => {
      const button = view.root
        .findAllByType("button")
        .find((b) =>
          b.children.some((child) => typeof child === "string" && child.includes(label)),
        );
      assert.ok(button, label);
      await button.props.onClick();
    });
  };
  const rows = () => view.root.findAllByType("tbody")[0].findAllByType("tr").length;
  try {
    await act(async () => {
      view = create(React.createElement(AuthProvider, null, React.createElement(Harness)));
    });
    assert.equal(queries.at(-1)?.get("mine"), "true");
    assert.equal(rows(), 100);
    await click("Carregar mais pedidos");
    assert.equal(queries.at(-1)?.get("cursor"), "100");
    assert.equal(rows(), 105);
    await click("Todos");
    assert.equal(queries.at(-1)?.get("mine"), "false");
    assert.equal(queries.at(-1)?.get("cursor"), null);
    assert.equal(rows(), 100);
    holdMore = true;
    await click("Carregar mais pedidos");
    await click("Para aprovar");
    await act(async () => {
      releaseMore(Response.json({ items: [order(999)], next_cursor: null }));
    });
    assert.equal(rows(), 100);
    assert.equal(queries.at(-1)?.get("status"), "READY_FOR_REVIEW");
    assert.equal(queries.at(-1)?.get("cursor"), null);
    session = meFor("AUDITOR_FISCAL");
    await act(async () => {
      await auth.refresh();
    });
    assert.equal(queries.at(-1)?.get("status"), "PENDING_FISCAL");
    assert.equal(queries.at(-1)?.get("cursor"), null);
    session = meFor("SOLICITANTE_OPERACAO");
    await act(async () => {
      await auth.refresh();
    });
    assert.equal(queries.at(-1)?.get("mine"), "true");
    assert.equal(queries.at(-1)?.get("status"), null);
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = previousFetch;
  }
});
