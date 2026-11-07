import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AutomaticDecision } from "../src/features/sanitization/AutomaticDecision";
Object.assign(globalThis, { React });
const render = (props: React.ComponentProps<typeof AutomaticDecision>) =>
  renderToStaticMarkup(React.createElement(AutomaticDecision, props));
test("aplicação automática não inventa aprovação humana", () => {
  const html = render({ status: "APPLIED", mode: "AUTOMATIC" });
  assert.match(html, /Aplicado automaticamente pelo sistema/);
  assert.doesNotMatch(html, /Aprovado por pessoa/);
});
test("aprovação humana continua identificável", () => {
  assert.match(render({ status: "APPLIED", mode: "HUMAN" }), /Aprovado por pessoa/);
});
test("simulação permanece explícita e mostra motivos para revisão", () => {
  const html = render({
    status: "PENDING",
    automation: {
      mode: "SIMULATE",
      status: "REVIEW",
      policy_version: "safe-corrections-v1",
      execution_id: "id",
      reasons: ["TEXT_LOSS"],
      index_status: "NOT_REQUIRED",
    },
  });
  assert.match(html, /Simulação/);
  assert.match(html, /TEXT_LOSS/);
  assert.doesNotMatch(html, /Aplicado automaticamente/);
});
test("indexação pendente fica visível", () => {
  assert.match(
    render({
      status: "APPLIED",
      mode: "AUTOMATIC",
      automation: {
        mode: "APPLY",
        status: "APPLIED",
        policy_version: "safe-corrections-v1",
        execution_id: "id",
        reasons: ["SAFE_CORRECTION"],
        index_status: "FAILED",
      },
    }),
    /Atualização da busca pendente/,
  );
});
