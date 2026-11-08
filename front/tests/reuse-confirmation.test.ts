import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { MaterialCard } from "../src/features/chat/MaterialCard";
Object.assign(globalThis, { React, IS_REACT_ACT_ENVIRONMENT: true });

test("reutilização exige ação estruturada explícita no código exibido", async () => {
  const examples = JSON.parse(
    readFileSync(new URL("../../api/contracts/fixtures/examples.json", import.meta.url), "utf8"),
  );
  const card = examples.find((e: { name: string }) => e.name === "chat-pick-candidate").response
    .material_card;
  const actions: unknown[] = [];
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(
        React.createElement(MaterialCard, {
          card,
          onReply: (message, action) => actions.push({ message, action }),
        }),
      );
    });
    assert.equal(actions.length, 0);
    await act(async () => {
      view.root
        .findAllByType("button")
        .find((b) => b.children.includes("Confirmar reutilização"))!
        .props.onClick();
    });
    assert.deepEqual(actions, [
      {
        message: `É o item ${card.existing.material_code}`,
        action: { type: "PICK_CANDIDATE", material_code: card.existing.material_code },
      },
    ]);
  } finally {
    await act(async () => view?.unmount());
  }
});
