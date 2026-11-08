import assert from "node:assert/strict";
import { test } from "node:test";
import React, { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AuthProvider } from "../src/lib/auth";
import { ProposalReview } from "../src/features/sanitization/ProposalReview";
import { ProposalOriginBadge } from "../src/components/ui/status";
import { proposals } from "../src/mocks/queue";
import type { Proposal } from "../src/types/api";
Object.assign(globalThis, { React });

const review = (proposal: Proposal) =>
  renderToStaticMarkup(h(AuthProvider, null, h(ProposalReview, { proposal })));

test("só a sugestão do auditor LLM ganha selo de origem", () => {
  assert.match(
    renderToStaticMarkup(h(ProposalOriginBadge, { value: "LLM_AUDITOR" })),
    /Auditor LLM/,
  );
  assert.equal(renderToStaticMarkup(h(ProposalOriginBadge, { value: "RULES" })), "");
});

test("revisão mostra motivo, trechos, base e aviso de simulado da sugestão do auditor", () => {
  const html = review(proposals.find((p) => p.origin === "LLM_AUDITOR")!);
  assert.match(html, /Sugestão do auditor LLM/);
  assert.match(html, /NCM_MATTER_UNPROVEN/);
  assert.match(html, /ZINCADO BRANCO/);
  assert.match(html, /Inferido/);
  assert.match(html, /Resposta simulada/);
});

test("proposta das regras não mostra o painel do auditor", () => {
  const rules = proposals.find(
    (p) => p.origin === "RULES" && p.proposal_type === "NCM_CORRECTION",
  )!;
  assert.doesNotMatch(review(rules), /auditor LLM/i);
});
