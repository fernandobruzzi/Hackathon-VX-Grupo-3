import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fmtHours, fulfillmentRows, outcomeRows, type RequestJourney } from "../src/lib/journey";

const examples = JSON.parse(
  readFileSync(new URL("../../api/contracts/fixtures/examples.json", import.meta.url), "utf8"),
) as { name: string; response: { journey: RequestJourney } }[];
const journey = (name: string) =>
  examples.find((example) => example.name === name)!.response.journey;

test("estoque, parcial e compras aparecem em linhas separadas", () => {
  const rows = fulfillmentRows(journey("dashboard-quality"));
  const values = Object.fromEntries(rows.map((row) => [row.key, row.value]));
  assert.deepEqual(
    { stock: values.stock, partial: values.partial, purchasing: values.purchasing },
    { stock: "3", partial: "1", purchasing: "2" },
  );
});

test("sem solicitações, todo indicador fica indisponível com o motivo, nunca zero", () => {
  const empty = journey("dashboard-quality-after-snapshot");
  for (const row of [...fulfillmentRows(empty), ...outcomeRows(empty)]) {
    assert.equal(row.value, null, row.key);
    assert.match(row.note, /Nenhuma solicitação/);
  }
});

test("indicador sem base mostra o próprio motivo e os demais continuam disponíveis", () => {
  const rows = Object.fromEntries(
    outcomeRows(journey("dashboard-quality")).map((row) => [row.key, row]),
  );
  assert.equal(rows.duplicate.value, null);
  assert.match(rows.duplicate.note, /conversa/);
  assert.equal(rows.registration.value, "3");
  assert.equal(rows.resolution.value, "5,5 h");
  assert.match(rows.resolution.note, /26,3 h/);
});

test("horas usam vírgula decimal e minutos abaixo de uma hora", () => {
  assert.equal(fmtHours(0.25), "15 min");
  assert.equal(fmtHours(4), "4 h");
  assert.equal(fmtHours(26.25), "26,3 h");
});

test("a jornada não exibe valores financeiros", () => {
  const source = readFileSync(
    new URL("../src/features/dashboard/JourneyIndicators.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(source, /fmtBRL|financial|R\$/);
  assert.match(source, /Indisponível/);
});
