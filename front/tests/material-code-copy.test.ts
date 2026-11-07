import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { MaterialCard } from "../src/features/chat/MaterialCard";
import type { MaterialCardData } from "../src/types/api";

Object.assign(globalThis, { React, IS_REACT_ACT_ENVIRONMENT: true });

const cardFor = (code: string): MaterialCardData => ({
  pdm_class_id: "PDM110",
  pdm_class_name: "Componente",
  attributes: { "REFERENCIA FABRICANTE": "REF-NAO-COPIAR" },
  pdm_description: "Descrição PDM",
  validation_status: "VALID",
  missing_attributes: [],
  ncm: { suggested: null, status: "PENDING_VALIDATION" },
  duplicate_check_status: "MATCH_FOUND",
  can_submit: false,
  existing: {
    material_code: code,
    status: "ATIVO",
    pdm_description: "Descrição do item ativo",
    match_type: "EXACT_IDENTITY",
    reason: "Código bloqueado 99999999 resolvido para o destino ativo.",
    inventory: [],
  },
});

async function withCard(
  clipboard: { writeText: (value: string) => Promise<void> } | undefined,
  testBody: (view: ReactTestRenderer) => Promise<void>,
) {
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const originalFetch = globalThis.fetch;
  let requests = 0;
  let view!: ReactTestRenderer;
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard } });
  globalThis.fetch = async () => {
    requests++;
    throw new Error("Copiar não chama a API");
  };
  try {
    await act(async () => {
      view = create(React.createElement(MaterialCard, { card: cardFor("00001234") }));
    });
    await testBody(view);
    assert.equal(requests, 0);
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = originalFetch;
    if (originalNavigator) Object.defineProperty(globalThis, "navigator", originalNavigator);
    else Reflect.deleteProperty(globalThis, "navigator");
  }
}

const feedback = (view: ReactTestRenderer) =>
  view.root.findByProps({ role: "status" }).children.join("");
const copyButton = (view: ReactTestRenderer) => view.root.findByType("button");

test("estoque mostra apenas o nome do centro e usa código quando o nome falta", async () => {
  const card = cardFor("00001234");
  card.existing!.inventory = [
    { center_code: "1200", center_name: "USINA DE BENEFICIAMENTO", quantity: "4", unit: "PC" },
    { center_code: "0010", center_name: null, quantity: "2", unit: "PC" },
  ];
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(React.createElement(MaterialCard, { card }));
    });
    const text = view.root
      .findAllByType("p")
      .map((p) => p.children.join(""))
      .join(" ");
    assert.match(text, /USINA DE BENEFICIAMENTO · 4 PC/);
    assert.doesNotMatch(text, /1200/);
    assert.match(text, /0010 · 2 PC/);
  } finally {
    await act(async () => view?.unmount());
  }
});

test("copia somente o código ativo com zeros e confirma apenas depois da resolução", async () => {
  const values: string[] = [];
  let finish!: () => void;
  await withCard(
    {
      writeText: (value) => {
        values.push(value);
        return new Promise<void>((resolve) => {
          finish = resolve;
        });
      },
    },
    async (view) => {
      let pending!: Promise<void>;
      await act(async () => {
        pending = copyButton(view).props.onClick();
      });
      assert.deepEqual(values, ["00001234"]);
      assert.equal(copyButton(view).props.disabled, true);
      assert.doesNotMatch(feedback(view), /Código copiado/);
      await act(async () => {
        finish();
        await pending;
      });
      assert.equal(feedback(view), "Código copiado.");
      assert.equal(view.root.findByProps({ role: "status" }).props["aria-live"], "polite");
    },
  );
});

for (const unavailable of [false, true]) {
  test(`falha ${unavailable ? "por indisponibilidade" : "por recusa"} orienta cópia manual sem confirmação falsa`, async () => {
    await withCard(
      unavailable
        ? undefined
        : {
            writeText: async () => {
              throw new DOMException("Recusado", "NotAllowedError");
            },
          },
      async (view) => {
        await act(async () => {
          await copyButton(view).props.onClick();
        });
        assert.match(feedback(view), /Não foi possível copiar/);
        assert.match(feedback(view), /Selecione o código acima e copie manualmente/);
        assert.doesNotMatch(feedback(view), /Código copiado/);
        assert.equal(copyButton(view).props.disabled, false);
      },
    );
  });
}

test("troca do código ativo descarta o feedback da cópia anterior", async () => {
  const values: string[] = [];
  let finish!: () => void;
  await withCard(
    {
      writeText: (value) => {
        values.push(value);
        return values.length === 1
          ? new Promise<void>((resolve) => {
              finish = resolve;
            })
          : Promise.resolve();
      },
    },
    async (view) => {
      let pending!: Promise<void>;
      await act(async () => {
        pending = copyButton(view).props.onClick();
      });
      await act(async () => {
        view.update(React.createElement(MaterialCard, { card: cardFor("00005678") }));
      });
      await act(async () => {
        finish();
        await pending;
      });
      assert.equal(feedback(view), "");
      await act(async () => {
        await copyButton(view).props.onClick();
      });
      assert.deepEqual(values, ["00001234", "00005678"]);
      assert.equal(feedback(view), "Código copiado.");
    },
  );
});
