import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { FORWARD_NOTICE, FORWARD_STATUS, forwardQuantity } from "../src/lib/purchasing";

const forbidden = /\b(comprad[oa]s?|recebid[oa]s?|compra realizada|entregue)\b/i;

test("estados do encaminhamento nunca dizem que houve compra ou recebimento", () => {
  for (const { label } of Object.values(FORWARD_STATUS)) assert.doesNotMatch(label, forbidden);
  assert.equal(FORWARD_STATUS.ENCAMINHADO.label, "Encaminhado para compras");
  const page = readFileSync(
    new URL("../src/features/purchasing/PurchasingPage.tsx", import.meta.url),
    "utf8",
  );
  const visible = page.replace(FORWARD_NOTICE, "");
  assert.doesNotMatch(visible, forbidden);
});

test("o aviso deixa claro que é só a demanda para Compras", () => {
  assert.match(FORWARD_NOTICE, /demanda para Compras/);
  assert.match(FORWARD_NOTICE, /não confirma/);
});

test("quantidade usa vírgula decimal e mantém a unidade", () => {
  assert.equal(forwardQuantity({ quantity: "10.000000", unit: "PC" }), "10 PC");
  assert.equal(forwardQuantity({ quantity: "2.500000", unit: "KG" }), "2,5 KG");
});
