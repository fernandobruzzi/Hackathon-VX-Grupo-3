import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CompletenessDiagnostics } from "../src/features/manual-reviews/ManualReviewsPage";
import type { components } from "../src/types/api.generated";

(globalThis as Record<string, unknown>).React = React;
type Completeness = components["schemas"]["MaterialCompletenessReview"];

const state = {
  status: "INCOMPLETE",
  missing_required: ["MATERIAL"],
  conditional_pending: [],
  invalid: [],
  not_applicable: [],
  optional_missing: [],
} as const;

test("pendência explica lacunas, diferencia conflitos e mostra o trecho a confirmar", () => {
  const completeness = {
    before: state,
    after_suggestions: state,
    suggestions: {},
    conflicts: { ACABAMENTO: ["ZINCADO", "NATURAL"] },
    record_conflicts: { REFERENCIA: ["ABC123", "ABC456"] },
    classification: { status: "UNRESOLVED", candidate_class_ids: ["PDM001", "PDM050"] },
    gaps: [
      {
        attribute: "MATERIAL",
        reason: "NO_SUPPORTED_EVIDENCE",
        question: "Qual é o MATERIAL? Informe o documento e o trecho correspondente.",
      },
    ],
    assisted_candidates: [
      {
        attribute: "MATERIAL",
        value: "ACO CARBONO",
        source_field: "description",
        excerpt: "MATERIAL: ACO CARBONO <script>não executar</script>",
      },
    ],
  } as unknown as Completeness;
  const html = renderToStaticMarkup(React.createElement(CompletenessDiagnostics, { completeness }));
  assert.match(html, /Classe a confirmar/);
  assert.match(html, /PDM001, PDM050/);
  assert.match(html, /Sem evidência suficiente/);
  assert.match(html, /Qual é o MATERIAL/);
  assert.match(html, /Conflito no registro/);
  assert.match(html, /ABC123, ABC456/);
  assert.match(html, /Conflito entre fontes/);
  assert.match(html, /ZINCADO, NATURAL/);
  assert.match(html, /Confirmação manual necessária/);
  assert.match(html, /ACO CARBONO/);
  assert.match(html, /&lt;script&gt;não executar&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<input|<select|<textarea|<script>/);
});

test("observação antiga continua mostrando faltantes sem inventar diagnóstico", () => {
  const completeness = {
    before: state,
    after_suggestions: state,
    suggestions: { MATERIAL: "ACO CARBONO" },
    conflicts: {},
  } as unknown as Completeness;
  const html = renderToStaticMarkup(React.createElement(CompletenessDiagnostics, { completeness }));
  assert.match(html, /Faltam/);
  assert.match(html, /MATERIAL/);
  assert.match(html, /Revisar sugestões com fontes/);
  assert.doesNotMatch(html, /Classe a confirmar|Confirmação manual necessária/);
});
