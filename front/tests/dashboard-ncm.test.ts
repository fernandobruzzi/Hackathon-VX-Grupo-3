import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { NcmSection } from "../src/features/dashboard/NcmSection";
import { dashboard } from "../src/mocks/data";

Object.assign(globalThis, { React });

test("NCM separa ausência, decisão fiscal e medição documental", () => {
  const html = renderToStaticMarkup(React.createElement(NcmSection, { ncm: dashboard.ncm }));
  assert.match(html, /Tratamento de NCM/);
  assert.match(html, /Sem snapshot posterior/);
  assert.match(html, /Sem decisões fiscais/);
  assert.match(html, /Somente formato/);
  assert.match(html, /Medição de desenvolvimento/);
  assert.match(html, /rótulos documentais/);
  assert.match(html, /benchmark-ncm-v2/);
  assert.doesNotMatch(html, /R\$/);
});
