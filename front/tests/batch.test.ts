import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { BatchPage } from "../src/features/batch/BatchPage";
import { meFor } from "../src/lib/permissions";

Object.assign(globalThis, {
  React,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: { location: { pathname: "/batch" } },
  document: { documentElement: { dataset: {} } },
});

for (const action of ["Iniciar job", "Reprocessar"]) {
  test(`${action}: falha de POST sobrevive ao GET e uma nova tentativa limpa só o erro da ação`, async () => {
    const previousFetch = globalThis.fetch;
    let failPost = true;
    let failGet = false;
    const jobs =
      action === "Reprocessar"
        ? [
            {
              id: "job-failed",
              status: "FAILED",
              job_type: "SANITIZE",
              requested_by: "gestor",
              progress: { processed: 0, total: 1 },
              counts: { proposals: 0 },
              started_at: null,
            },
          ]
        : [];
    globalThis.fetch = async (url, init) => {
      if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
      if (String(url).endsWith("/auth/me")) return Response.json(meFor("GESTOR_CADASTRO"));
      if (init?.method === "POST") {
        if (failPost)
          return Response.json(
            {
              error: {
                request_id: "test",
                details: {},
                code: "RUNNER_UNAVAILABLE",
                message: "Runner indisponível",
              },
            },
            { status: 503 },
          );
        return Response.json({});
      }
      if (failGet)
        return Response.json(
          {
            error: {
              request_id: "test",
              details: {},
              code: "QUERY_FAILED",
              message: "Consulta indisponível",
            },
          },
          { status: 503 },
        );
      return Response.json({ items: jobs, latest_dataset_id: "dataset" });
    };
    let view!: ReactTestRenderer;
    const click = async () => {
      await act(async () => {
        const button = view.root
          .findAllByType("button")
          .find((b) =>
            b.children.some((child) => typeof child === "string" && child.includes(action)),
          );
        assert.ok(button);
        await button.props.onClick();
      });
    };
    const alerts = () =>
      view.root
        .findAll((n) => n.props.role === "alert")
        .map((n) => n.props.children)
        .join(" ");
    try {
      await act(async () => {
        view = create(React.createElement(AuthProvider, null, React.createElement(BatchPage)));
      });
      await click();
      assert.match(alerts(), /Runner indisponível/);
      assert.match(alerts(), action === "Iniciar job" ? /iniciar/i : /reprocessar/i);
      failGet = true;
      await click();
      assert.match(alerts(), /Runner indisponível/);
      assert.match(alerts(), /Consulta indisponível/);
      failPost = false;
      await click();
      assert.doesNotMatch(alerts(), /Runner indisponível/);
      assert.match(alerts(), /Consulta indisponível/);
      failGet = false;
      await click();
      assert.equal(alerts(), "");
    } finally {
      await act(async () => view?.unmount());
      globalThis.fetch = previousFetch;
    }
  });
}
