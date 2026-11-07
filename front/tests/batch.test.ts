import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { BatchPage } from "../src/features/batch/BatchPage";
import { meFor } from "../src/lib/permissions";

Object.assign(globalThis, {
  React,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: { location: { pathname: "/batch" } },
  document: { documentElement: { dataset: {} } },
});

for (const [action, code, message] of [
  ["Iniciar job", "RUNNER_UNAVAILABLE", "Runner indisponível"],
  ["Reprocessar", "RUNNER_UNAVAILABLE", "Runner indisponível"],
  [
    "Iniciar job",
    "MULTIPLE_DATASETS_NOT_SUPPORTED",
    "O batch suporta exatamente um dataset por empresa no MVP. Múltiplas importações não são suportadas.",
  ],
  [
    "Reprocessar",
    "MULTIPLE_DATASETS_NOT_SUPPORTED",
    "O batch suporta exatamente um dataset por empresa no MVP. Múltiplas importações não são suportadas.",
  ],
]) {
  test(`${action} (${code}): falha de POST sobrevive ao GET e uma nova tentativa limpa só o erro da ação`, async () => {
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
                code,
                message,
              },
            },
            { status: code === "MULTIPLE_DATASETS_NOT_SUPPORTED" ? 422 : 503 },
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
      return Response.json({
        items: jobs,
        latest_dataset_id: "dataset",
        active_job: jobs.find((job) => ["QUEUED", "RUNNING"].includes(job.status)) ?? null,
      });
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
      assert.match(alerts(), new RegExp(message));
      assert.match(alerts(), action === "Iniciar job" ? /iniciar/i : /reprocessar/i);
      failGet = true;
      await click();
      assert.match(alerts(), new RegExp(message));
      assert.match(alerts(), /Consulta indisponível/);
      failPost = false;
      await click();
      assert.doesNotMatch(alerts(), new RegExp(message));
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

test("trocar a sessão descarta o comando sem resposta e uma nova operação recebe outra chave", async () => {
  const previousFetch = globalThis.fetch;
  const keys: string[] = [];
  let auth!: ReturnType<typeof useAuth>;
  function Probe() {
    auth = useAuth();
    return null;
  }
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
    if (String(url).endsWith("/auth/me") || String(url).endsWith("/auth/local-session")) {
      return Response.json(meFor("GESTOR_CADASTRO"));
    }
    if (init?.method === "POST") {
      keys.push(new Headers(init.headers).get("Idempotency-Key")!);
      throw new TypeError("Resposta perdida");
    }
    return Response.json({ items: [], latest_dataset_id: "dataset", active_job: null });
  };
  let view!: ReactTestRenderer;
  const buttons = (label: string) =>
    view.root
      .findAllByType("button")
      .filter((b) =>
        b.children.some((child) => typeof child === "string" && child.includes(label)),
      );
  try {
    await act(async () => {
      view = create(
        React.createElement(
          AuthProvider,
          null,
          React.createElement(Probe),
          React.createElement(BatchPage),
        ),
      );
    });
    await act(async () => buttons("Iniciar job")[0].props.onClick());
    assert.equal(buttons("Tentar novamente").length, 1);
    await act(async () => {
      assert.equal(await auth.signIn("GESTOR_CADASTRO"), true);
    });
    assert.equal(buttons("Tentar novamente").length, 0);
    await act(async () => buttons("Iniciar job")[0].props.onClick());
    assert.equal(keys.length, 2);
    assert.notEqual(keys[1], keys[0]);
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = previousFetch;
  }
});

for (const action of ["Iniciar job", "Reprocessar"]) {
  test(`${action}: repetir após resposta perdida conserva chave, corpo e recurso`, async () => {
    const previousFetch = globalThis.fetch;
    const calls: { url: string; key: string | null; body: BodyInit | null | undefined }[] = [];
    let dataset = "dataset-original";
    const job = {
      id: "job-original",
      status: "FAILED",
      job_type: "SANITIZE",
      requested_by: "gestor",
      progress: { processed: 0, total: 1 },
      counts: { proposals: 0 },
      started_at: null,
    };
    let jobs = action === "Reprocessar" ? [job] : [];
    globalThis.fetch = async (url, init) => {
      if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
      if (String(url).endsWith("/auth/me")) return Response.json(meFor("GESTOR_CADASTRO"));
      if (init?.method === "POST") {
        calls.push({
          url: String(url),
          key: new Headers(init.headers).get("Idempotency-Key"),
          body: init.body,
        });
        if (calls.length === 1) {
          dataset = "dataset-new";
          // O servidor aceitou, mas a resposta não chegou. A listagem já mostra o job ativo.
          jobs = [{ ...job, status: "QUEUED" }];
          throw new TypeError("Resposta perdida");
        }
        jobs = [];
        return Response.json({ ...job, status: "SUCCEEDED" });
      }
      return Response.json({
        items: jobs,
        latest_dataset_id: dataset,
        active_job: jobs.find((job) => ["QUEUED", "RUNNING"].includes(job.status)) ?? null,
      });
    };
    let view!: ReactTestRenderer;
    const click = async (label: string) =>
      act(async () => {
        const button = view.root
          .findAllByType("button")
          .find((b) =>
            b.children.some((child) => typeof child === "string" && child.includes(label)),
          );
        assert.ok(button);
        assert.equal(button.props.disabled, false);
        await button.props.onClick();
      });
    try {
      await act(async () => {
        view = create(React.createElement(AuthProvider, null, React.createElement(BatchPage)));
      });
      await click(action);
      assert.equal(calls.length, 1);
      assert.ok(view.root.findAll((n) => n.props.role === "alert").length);
      await click("Tentar novamente");
      assert.equal(calls.length, 2);
      assert.deepEqual(calls[1], calls[0]);
      assert.match(calls[0].key!, /^[0-9a-f-]{36}$/);
      if (action === "Iniciar job") {
        assert.equal(JSON.parse(String(calls[1].body)).dataset_id, "dataset-original");
        await click("Iniciar job");
        assert.notEqual(calls[2].key, calls[1].key);
        assert.equal(JSON.parse(String(calls[2].body)).dataset_id, "dataset-new");
      } else {
        assert.match(calls[1].url, /job-original\/resume$/);
        assert.equal(calls[1].body, "{}");
      }
    } finally {
      await act(async () => view?.unmount());
      globalThis.fetch = previousFetch;
    }
  });
}
