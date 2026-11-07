import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AuditAction, AuditChanges } from "../src/features/audit/AuditPresentation";
import type { AuditEvent } from "../src/types/api";
Object.assign(globalThis, { React });
const event: AuditEvent = {
  id: "a",
  actor: "Fiscal",
  actor_type: "USER",
  effective_role: "ROLE_AUDITOR_FISCAL",
  action: "PROPOSAL_APPROVE_FISCAL",
  entity: "proposal p",
  reason: "Conferido",
  request_id: "req-1",
  created_at: "2026-11-07T10:00:00Z",
};
const changes = (before?: AuditEvent["before"], after?: AuditEvent["after"]) =>
  renderToStaticMarkup(React.createElement(AuditChanges, { event: { ...event, before, after } }));
test("ações reais têm rótulo operacional e conservam código técnico", () => {
  for (const [action, label] of [
    ["ORDER_SUBMITTED", "Pedido enviado para revisão"],
    ["PROPOSAL_APPROVE_TECHNICAL", "Proposta aprovada pela Governança"],
    ["PROPOSAL_APPROVE_FISCAL", "Proposta aprovada pelo Fiscal"],
    ["PROPOSAL_AUTO_APPLY", "Correção aplicada automaticamente"],
  ]) {
    const html = renderToStaticMarkup(React.createElement(AuditAction, { action }));
    assert.ok(html.includes(label));
    assert.ok(html.includes(action));
  }
  assert.match(
    renderToStaticMarkup(React.createElement(AuditAction, { action: "FUTURE_ACTION" })),
    /Ação ainda não traduzida.*FUTURE_ACTION/,
  );
});
test("compara materiais pelo id mesmo reordenados e apresenta campos suportados", () => {
  const html = changes(
    {
      status: "PENDING",
      materials: [
        {
          id: "1",
          material_code: "M01",
          unit: "PC",
          ncm: "001",
          pdm_description: "Antes",
          status: "ATIVO",
          active_code_target: "old",
        },
        { id: "2", unit: "KG" },
      ],
    },
    {
      status: "APPLIED",
      materials: [
        { id: "2", unit: "KG" },
        {
          id: "1",
          material_code: "M01",
          unit: "UN",
          ncm: "002",
          pdm_description: "Depois",
          status: "BLOQUEADO",
          active_code_target: "new",
        },
      ],
    },
  );
  for (const text of [
    "Unidade",
    "NCM",
    "Descrição PDM",
    "Status",
    "Código principal",
    "PC",
    "UN",
    "001",
    "002",
    "Antes",
    "Depois",
    "M01",
    "Alterado",
  ])
    assert.ok(html.includes(text), text);
  assert.equal((html.match(/>Unidade</g) ?? []).length, 1);
});
test("ausência, null e dados incompletos não comprovam mudanças nem viram zero", () => {
  const html = changes(
    { materials: [{ id: "1", unit: null }] },
    { materials: [{ id: "1", unit: "UN", ncm: "001" }] },
  );
  assert.match(html, /Não informado/);
  assert.match(html, /Não registrado/);
  assert.match(html, /Comparação indisponível/);
  assert.doesNotMatch(html, />Alterado</);
  assert.match(changes(), /Antes e depois indisponíveis/);
});
test("fallback preserva somente registro recebido, incluindo execução automática", () => {
  const html = changes(undefined, {
    automatic_correction: { run_id: "exec-123" },
    future: { code: "future-value" },
  });
  assert.match(html, /Dados registrados/);
  assert.match(html, /exec-123/);
  assert.match(html, /future-value/);
  assert.doesNotMatch(html, /total_value|price/);
});

test("eventos do contrato continuam legíveis com dados incompletos e ator preservado", async () => {
  const { readFileSync } = await import("node:fs");
  const fixtures = JSON.parse(
    readFileSync(new URL("../../api/contracts/fixtures/examples.json", import.meta.url), "utf8"),
  );
  const events: AuditEvent[] = fixtures.find((row: { name: string }) => row.name === "audit")
    .response.items;
  for (const item of events) {
    const html = renderToStaticMarkup(React.createElement(AuditChanges, { event: item }));
    assert.ok(html.includes("Anterior"));
    assert.ok(html.includes("Posterior"));
    assert.ok(html.includes("Dados registrados"));
  }
});

test("campos desconhecidos e snapshots malformados ficam no fallback sem inventar pares", () => {
  const html = changes(
    { materials: [null, "invalid", { unit: "PC" }], future_field: 0 },
    { materials: [{ unit: "UN" }], future_field: 1 },
  );
  assert.match(html, /Nenhuma alteração comparável/);
  assert.match(html, /future_field/);
  assert.doesNotMatch(html, />Alterado</);
});

test("ações desconhecidas não herdam propriedades do objeto de rótulos", () => {
  for (const action of ["__proto__", "constructor", "toString"]) {
    const html = renderToStaticMarkup(React.createElement(AuditAction, { action }));
    assert.match(html, /Ação ainda não traduzida/);
    assert.ok(html.includes(action));
  }
});
