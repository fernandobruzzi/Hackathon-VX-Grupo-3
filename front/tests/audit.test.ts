import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AuditIdentity } from "../src/features/audit/AuditIdentity";
import type { AuditEvent } from "../src/types/api";

Object.assign(globalThis, { React });

const event: AuditEvent = {
  id: "event",
  actor: "Nome humano que não pertence ao evento automático",
  actor_type: "SYSTEM",
  effective_role: null,
  action: "PROPOSAL_SUPERSEDED",
  entity: "proposta original",
  reason: "Nova revisão",
  request_id: "",
  created_at: "2026-11-06T00:00:00Z",
};
const render = (value: AuditEvent) =>
  renderToStaticMarkup(
    React.createElement(
      "table",
      null,
      React.createElement(
        "tbody",
        null,
        React.createElement("tr", null, React.createElement(AuditIdentity, { event: value })),
      ),
    ),
  );

test("auditoria apresenta sistema sem atribuir usuário ou papel humano", () => {
  const result = render(event);
  assert.match(result, /Sistema/);
  assert.match(result, /Processo automático/);
  assert.doesNotMatch(result, /Nome humano|ROLE_/);
});

test("auditoria preserva usuário e papel efetivo de decisões humanas", () => {
  const result = render({
    ...event,
    actor_type: "USER",
    actor: "Fiscal",
    effective_role: "ROLE_AUDITOR_FISCAL",
  });
  assert.match(result, /Fiscal/);
  assert.match(result, /ROLE_AUDITOR_FISCAL/);
  assert.doesNotMatch(result, /Processo automático/);
});
