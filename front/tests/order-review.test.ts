import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { OrderReviewPanel } from "../src/features/orders/OrderReviewPanel";
import { meFor } from "../src/lib/permissions";

Object.assign(globalThis, {
  React,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: { location: { pathname: "/pedidos" } },
  document: { documentElement: { dataset: {} } },
});
const fixtures = JSON.parse(
  readFileSync(new URL("../../api/contracts/fixtures/examples.json", import.meta.url), "utf8"),
);
for (const persona of ["GESTOR_CADASTRO", "AUDITOR_FISCAL"] as const) {
  test(`${persona}: revisa a ficha e repete decisão sem resposta com chave estável`, async () => {
    const previousFetch = globalThis.fetch;
    const detail = structuredClone(
      fixtures.find((row: { name: string }) => row.name === "order-review").response,
    );
    detail.order.status = persona === "GESTOR_CADASTRO" ? "READY_FOR_REVIEW" : "PENDING_FISCAL";
    let decided = 0;
    let lost = true;
    const posts: { key: string | null; body: Record<string, unknown> }[] = [];
    globalThis.fetch = async (url, init) => {
      if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
      if (String(url).endsWith("/auth/me")) return Response.json(meFor(persona));
      if (init?.method !== "POST") return Response.json(detail);
      posts.push({
        key: new Headers(init.headers).get("Idempotency-Key"),
        body: JSON.parse(String(init.body)),
      });
      if (lost) throw new TypeError("Resposta perdida após confirmação");
      assert.equal(posts.at(-1)?.key, posts[0].key);
      return Response.json({ ...detail.order, status: "REGISTERED" });
    };
    let view!: ReactTestRenderer;
    try {
      await act(async () => {
        view = create(
          React.createElement(
            AuthProvider,
            null,
            React.createElement(OrderReviewPanel, {
              id: detail.order.id,
              onClose: () => {},
              onDecided: () => {
                decided++;
              },
            }),
          ),
        );
      });
      const rendered = JSON.stringify(view.toJSON());
      assert.match(rendered, /Texto original/);
      assert.match(rendered, /Descrição proposta/);
      assert.match(rendered, /Existência e vigência oficial desconhecidas/);
      assert.ok(rendered.includes(detail.order.original_text));
      await act(async () => {
        view.root
          .findByType("textarea")
          .props.onChange({ target: { value: "Ficha técnica conferida" } });
        if (persona === "AUDITOR_FISCAL") {
          view.root
            .findByType("select")
            .props.onChange({ target: { value: detail.ncm_assessment.suggested_ncm_codes[0] } });
          view.root
            .findByType("input")
            .props.onChange({ target: { value: "Ficha do fabricante" } });
        }
      });
      assert.equal(view.root.findAllByType("select").length, persona === "AUDITOR_FISCAL" ? 1 : 0);
      const save = () =>
        view.root
          .findAllByType("button")
          .find((b) =>
            b.children.some((child) => typeof child === "string" && child.includes("Aprovar")),
          )!
          .props.onClick();
      await act(async () => {
        await save();
      });
      assert.equal(decided, 0);
      lost = false;
      await act(async () => {
        await save();
      });
      assert.equal(decided, 1);
      assert.deepEqual(posts[0], posts[1]);
      assert.equal(posts[0].body.expected_version, detail.order.version);
      if (persona === "AUDITOR_FISCAL") {
        assert.equal(posts[0].body.ncm_code, detail.ncm_assessment.suggested_ncm_codes[0]);
        assert.equal(posts[0].body.ncm_source, "Ficha do fabricante");
        assert.equal(posts[0].body.ncm_evaluation_hash, detail.ncm_assessment.evaluation_hash);
      } else assert.equal(posts[0].body.ncm_code, undefined);
    } finally {
      await act(async () => view?.unmount());
      globalThis.fetch = previousFetch;
    }
  });
}
