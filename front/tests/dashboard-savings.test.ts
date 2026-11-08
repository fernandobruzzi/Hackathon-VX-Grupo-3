import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SavingsPanel } from "../src/features/dashboard/SavingsPanel";
import type { DashboardMetrics } from "../src/types/api";
Object.assign(globalThis, { React });

test("economia mostra contagem sem premissa e separa atendimento de estimativa", () => {
  const data = {
    currency: "BRL",
    data_origin: "SYNTHETIC_CHALLENGE_DATA",
    inventory_book_value: "100",
    realized_savings: null,
    estimated_savings: null,
    calculation_version: "savings-v1",
    assumption_source: null,
    components: [
      {
        key: "duplicate_codes",
        label: "Códigos desativados",
        kind: "ESTIMATED",
        count: "2",
        count_unit: "códigos",
        amount_brl: null,
        assumptions: [],
        formula: "códigos × custo anual",
        unavailable_reason: "Sem premissa",
      },
    ],
  } satisfies NonNullable<DashboardMetrics["financial"]>;
  const html = renderToStaticMarkup(React.createElement(SavingsPanel, { data }));
  assert.match(html, /Sem premissa/);
  assert.match(html, /2 códigos/);
  assert.match(html, /dados sintéticos/i);
  const measured = renderToStaticMarkup(
    React.createElement(SavingsPanel, {
      data: {
        ...data,
        components: [
          {
            ...data.components[0],
            key: "stock_fulfilled",
            kind: "MEASURED_KIT_VALUE",
            label: "Valor atendido com estoque",
            amount_brl: "20.00",
            unavailable_reason: null,
          },
        ],
      },
    }),
  );
  assert.match(measured, /Medido no kit/);
  assert.match(measured, /não comprova compra evitada/i);
});
