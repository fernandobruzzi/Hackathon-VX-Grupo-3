import assert from "node:assert/strict";
import { test } from "node:test";
import { can, meFor, PERSONAS, ROLE_PERMISSIONS } from "../src/lib/permissions";

const decisions = [
  "orders:decide",
  "merge:decide",
  "enrichment:decide",
  "ncm:decide",
  "batch:run",
  "queue:read",
  "queue:read_audit",
] as const;

test("Almoxarifado e Compras têm só as ações da própria fila", () => {
  assert.equal(can(meFor("ALMOXARIFADO"), "stock:reserve", "stock:deliver", "stock:reverse"), true);
  assert.equal(can(meFor("ALMOXARIFADO"), "purchasing:read", "purchasing:handle"), false);
  assert.equal(can(meFor("COMPRAS"), "purchasing:read", "purchasing:handle"), true);
  assert.equal(can(meFor("COMPRAS"), "stock:reserve", "stock:deliver", "stock:reverse"), false);
});

test("os papéis operacionais não aprovam cadastro, NCM nem unificação", () => {
  for (const role of ["ROLE_ALMOXARIFADO", "ROLE_COMPRAS"] as const)
    assert.deepEqual(
      ROLE_PERMISSIONS[role].filter((p) => (decisions as readonly string[]).includes(p)),
      [],
    );
});

test("ações de estoque e compras não vazam para os papéis existentes", () => {
  const operational = [
    "stock:reserve",
    "stock:deliver",
    "stock:reverse",
    "purchasing:read",
    "purchasing:handle",
  ];
  for (const persona of PERSONAS.filter((p) => !["ALMOXARIFADO", "COMPRAS"].includes(p.label)))
    assert.equal(can(meFor(persona.label), ...(operational as never[])), false, persona.label);
});
