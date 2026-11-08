import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { meFor } from "../src/lib/permissions";
import { RequestTracking } from "../src/features/requests/RequestTracking";
import { formatQuantity, quantityOrUnavailable } from "../src/features/requests/tracking";

Object.assign(globalThis, {
  React,
  self: globalThis,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: { location: { pathname: "/solicitacoes/" } },
  document: { documentElement: { dataset: {} } },
});
const detail = JSON.parse(
  readFileSync(new URL("../../api/contracts/fixtures/examples.json", import.meta.url), "utf8"),
).find((row: { name: string }) => row.name === "material-request-detail").response;
const text = (view: ReactTestRenderer) => JSON.stringify(view.toJSON());

test("quantidades preservam precisão decimal e não arredondam", () => {
  assert.equal(formatQuantity("999999999999999999.123456"), "999.999.999.999.999.999,123456");
  assert.equal(formatQuantity("10.000000"), "10");
  assert.equal(formatQuantity("0.000001"), "0,000001");
  assert.equal(quantityOrUnavailable(undefined), "Não informada");
  assert.equal(quantityOrUnavailable(null), "Não informada");
  assert.equal(quantityOrUnavailable("0.000000"), "0");
});

test("detalhe exige visão própria, mostra histórico e não inventa parcelas", async () => {
  const previous = globalThis.fetch;
  let request!: URL;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
    if (String(url).endsWith("/auth/me")) return Response.json(meFor("GESTOR_CADASTRO"));
    request = new URL(String(url), "http://localhost");
    return Response.json({
      ...detail,
      status: "EM_ATENDIMENTO",
      quantity: "10.000000",
      reserved_quantity: "6.000000",
      delivered_quantity: "0.000000",
      forwarded_quantity: "4.000000",
      pending_quantity: "0.000000",
      reservations: [
        {
          id: "reservation",
          status: "ATIVA",
          quantity: "6.000000",
          open_quantity: "6.000000",
          delivered_quantity: "0.000000",
          unit: "PC",
        },
      ],
      purchase_forwards: [
        {
          id: "forward",
          status: "ENCAMINHADO",
          quantity: "4.000000",
          material_code: "EXISTENTE",
          unit: "PC",
        },
      ],
    });
  };
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(
        React.createElement(
          AuthProvider,
          null,
          React.createElement(RequestTracking, { id: detail.id }),
        ),
      );
    });
    assert.equal(request.searchParams.get("mine"), "true");
    assert.deepEqual(
      view.root.findAllByType("dd").map((row) => row.children.join("")),
      ["10", "6", "0", "4", "0"],
    );
    assert.match(text(view), /Solicitação criada/);
    assert.equal(
      view.root.findAllByType("dd").filter((row) => row.children.includes("Não informada")).length,
      0,
    );
    assert.match(text(view), /Almoxarifado/);
    assert.match(text(view), /Parcelas do estoque/);
    assert.match(text(view), /Parcelas de compras/);
    assert.match(text(view), /EXISTENTE/);
    assert.match(text(view), /não confirma compra/);
    assert.match(text(view), /Aguardando entrega das quantidades reservadas/);
    assert.match(text(view), /Aguardando análise da demanda por Compras/);
    assert.doesNotMatch(text(view), /Definir o atendimento da quantidade ainda pendente/);
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = previous;
  }
});

test("paginação e filtro mantêm mine=true; sessão nova descarta resposta pendente", async () => {
  const previous = globalThis.fetch;
  const queries: URLSearchParams[] = [];
  let release!: (response: Response) => void;
  let auth!: ReturnType<typeof useAuth>;
  let session = meFor("GESTOR_CADASTRO");
  function Harness() {
    auth = useAuth();
    return React.createElement(RequestTracking);
  }
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
    if (String(url).endsWith("/auth/me")) return Response.json(session);
    const query = new URL(String(url), "http://localhost").searchParams;
    queries.push(query);
    if (query.has("cursor"))
      return new Promise<Response>((resolve) => {
        release = resolve;
      });
    return Response.json({
      items: query.has("status") ? [] : [{ ...detail, original_text: session.user.display_name }],
      next_cursor: query.has("status") ? null : "page-two",
    });
  };
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(React.createElement(AuthProvider, null, React.createElement(Harness)));
    });
    await act(async () => {
      view.root.findByType("select").props.onChange({ target: { value: "ENCERRADA" } });
    });
    assert.equal(queries.at(-1)?.get("status"), "ENCERRADA");
    assert.equal(queries.at(-1)?.has("cursor"), false);
    assert.match(text(view), /Nenhuma solicitação/);
    await act(async () => {
      view.root.findByType("select").props.onChange({ target: { value: "" } });
    });
    await act(async () => {
      view.root.findByType("button").props.onClick();
    });
    assert.equal(queries.at(-1)?.get("cursor"), "page-two");
    session = meFor("SOLICITANTE_OPERACAO");
    await act(async () => {
      await auth.refresh();
    });
    await act(async () => {
      release(
        Response.json({ items: [{ ...detail, protocol: "DADO-ANTIGO" }], next_cursor: null }),
      );
    });
    assert.doesNotMatch(text(view), /DADO-ANTIGO/);
    assert.equal(view.root.findByType("select").props.value, "");
    assert.ok(queries.every((query) => query.get("mine") === "true"));
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = previous;
  }
});

test("acesso direto recusado não mostra dados e permite tentar novamente", async () => {
  const previous = globalThis.fetch;
  let allowed = false;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
    if (String(url).endsWith("/auth/me")) return Response.json(meFor("SOLICITANTE_OPERACAO"));
    if (allowed) return Response.json(detail);
    return Response.json(
      {
        error: {
          code: "NOT_FOUND",
          message: "Solicitação não encontrada no seu escopo.",
          request_id: "test",
          details: {},
        },
      },
      { status: 404 },
    );
  };
  let view!: ReactTestRenderer;
  try {
    await act(async () => {
      view = create(
        React.createElement(
          AuthProvider,
          null,
          React.createElement(RequestTracking, { id: "other" }),
        ),
      );
    });
    assert.equal(view.root.findAllByProps({ role: "alert" }).length, 1);
    assert.doesNotMatch(text(view), /SM-00000001/);
    allowed = true;
    await act(async () => {
      view.root.findByType("button").props.onClick();
    });
    assert.match(text(view), /SM-00000001/);
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = previous;
  }
});
