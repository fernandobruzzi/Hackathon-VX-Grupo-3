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

test("evidência de estoque mostra quantidade, preço, origem e data sem somar períodos", () => {
  const html = renderToStaticMarkup(
    React.createElement(SavingsPanel, {
      data: {
        currency: "BRL",
        data_origin: "SYNTHETIC_CHALLENGE_DATA",
        inventory_book_value: "100",
        realized_savings: null,
        estimated_savings: null,
        components: [
          {
            key: "stock_fulfilled",
            label: "Valor atendido com estoque",
            kind: "MEASURED_KIT_VALUE",
            count: "2",
            count_unit: "PC",
            amount_brl: "20.00",
            unavailable_reason: null,
            formula: "quantidade × preço original",
            quantities: { PC: "2" },
            stock_evidence: [
              {
                delivery_id: "entrega",
                quantity: "2",
                unit: "PC",
                unit_price: "10",
                source: "Origem preservada",
                recorded_on: "2026-11-08",
                snapshot_ids: ["linha"],
                factors: { linha: "1" },
              },
            ],
          },
        ],
      },
    }),
  );
  assert.match(html, /2 PC/);
  assert.match(html, /Origem preservada/);
  assert.match(html, /2026-11-08/);
  assert.match(html, /10,00/);
  assert.match(html, /total agregado fica indisponível/i);
  assert.doesNotMatch(html, /Soma somente estimativas/);
});
