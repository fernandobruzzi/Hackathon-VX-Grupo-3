import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { OrderComplementForm } from "../src/features/orders/OrderComplementForm";
import { meFor } from "../src/lib/permissions";
import type { RegistrationOrder } from "../src/types/api";

Object.assign(globalThis, {
  React,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: { location: { pathname: "/pedidos" } },
  document: { documentElement: { dataset: {} } },
});

test("complemento envia versão, informação, fonte e motivo; erro não confirma sucesso", async () => {
  const oldFetch = globalThis.fetch;
  let fail = true;
  let sent: Record<string, unknown> | null = null;
  let saved: RegistrationOrder | null = null;
  const order: RegistrationOrder = {
    id: "pedido",
    origin: "IMPORT",
    requester: null,
    original_text: "Original",
    center_code: "2200",
    pdm_class_id: "PDM001",
    status: "INCOMPLETE",
    missing_attributes: ["BITOLA"],
    material_code: null,
    updated_at: "2026-11-06T00:00:00Z",
    version: 7,
  };
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
    if (String(url).endsWith("/auth/me")) return Response.json(meFor("GESTOR_CADASTRO"));
    assert.ok(String(url).endsWith("/pedido/complement"));
    sent = JSON.parse(String(init?.body));
    if (fail)
      return Response.json(
        {
          error: {
            code: "VERSION_CONFLICT",
            message: "Pedido alterado",
            request_id: "req-test",
            details: {},
          },
        },
        { status: 409 },
      );
    return Response.json({
      ...order,
      version: 8,
      status: "READY_FOR_REVIEW",
      missing_attributes: [],
    });
  };
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(
        React.createElement(
          AuthProvider,
          null,
          React.createElement(OrderComplementForm, {
            order,
            onSaved: (value) => {
              saved = value;
            },
            onCancel: () => {},
          }),
        ),
      );
    });
    await act(async () => {
      view.root.findByType("textarea").props.onChange({ target: { value: "BITOLA: M12" } });
      const inputs = view.root.findAllByType("input");
      inputs[0].props.onChange({ target: { value: "Desenho técnico" } });
      inputs[1].props.onChange({ target: { value: "Conferido" } });
    });
    const save = () => view.root.findAllByType("button")[0].props.onClick();
    await act(async () => {
      await save();
    });
    assert.equal(saved, null);
    assert.match(
      String(view.root.findByProps({ role: "alert" }).props.children),
      /Pedido alterado/,
    );
    assert.deepEqual(sent, {
      expected_version: 7,
      text: "BITOLA: M12",
      source: "Desenho técnico",
      reason: "Conferido",
    });
    fail = false;
    await act(async () => {
      await save();
    });
    assert.equal((saved as RegistrationOrder | null)?.status, "READY_FOR_REVIEW");
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = oldFetch;
  }
});
