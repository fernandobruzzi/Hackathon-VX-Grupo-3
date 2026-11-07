import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestInstance, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { meFor } from "../src/lib/permissions";
import { BatchPage } from "../src/features/batch/BatchPage";

Object.assign(globalThis, {
  React,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: { location: { pathname: "/batch" } },
  document: { documentElement: { dataset: {} } },
});
const textOf = (node: ReactTestInstance): string =>
  node.children.map((child) => (typeof child === "string" ? child : textOf(child))).join("");
const job = (id: string, status = "FAILED") => ({
  id,
  status,
  job_type: "SANITIZE",
  requested_by: "gestor",
  progress: { processed: 0, total: 100 },
  counts: { proposals: 0, merges: 0, ncm: 0, enrichment: 0 },
  started_at: null,
  heartbeat_at: null,
});
type Job = ReturnType<typeof job>;
const history = (tenant: string) =>
  Array.from({ length: 125 }, (_, index) => job(`${tenant}-${124 - index}`));
function page(items: Job[], cursor: string | null, active: Job | null = null) {
  const offset = cursor ? Number(cursor.slice(5)) : 0;
  return {
    items: items.slice(offset, offset + 20),
    next_cursor: offset + 20 < items.length ? `page:${offset + 20}` : null,
    latest_dataset_id: "dataset",
    active_job: active,
  };
}
const button = (view: ReactTestRenderer, label: string) =>
  view.root.findAllByType("button").find((node) => textOf(node).includes(label));
const rows = (view: ReactTestRenderer) =>
  view.root.findAllByType("tbody").flatMap((body) => body.findAllByType("tr"));
async function click(view: ReactTestRenderer, label: string) {
  const target = button(view, label);
  assert.ok(target, label);
  assert.equal(target.props.disabled, false);
  await act(async () => {
    await target.props.onClick();
  });
}

for (const failMore of [false, true]) {
  test(`histórico percorre 125 jobs, retoma o mais antigo e acompanha fora do filtro (falha de página: ${failMore})`, async () => {
    const original = globalThis.fetch;
    const items = history("a");
    let active: Job | null = null;
    let shouldFail = failMore;
    const queries: URL[] = [];
    const commands: string[] = [];
    globalThis.fetch = async (url, init) => {
      if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
      if (String(url).endsWith("/auth/me")) return Response.json(meFor("GESTOR_CADASTRO"));
      if (init?.method === "POST") {
        commands.push(String(url));
        active = job("a-0", "QUEUED");
        items[124] = active;
        return Response.json(active);
      }
      const query = new URL(String(url), "http://localhost");
      queries.push(query);
      if (shouldFail && query.searchParams.get("cursor") === "page:20") {
        shouldFail = false;
        return Response.json(
          {
            error: {
              code: "UNAVAILABLE",
              message: "Histórico indisponível",
              request_id: "history",
              details: {},
            },
          },
          { status: 503 },
        );
      }
      const status = query.searchParams.get("status");
      return Response.json(
        page(
          items.filter((item) => !status || item.status === status),
          query.searchParams.get("cursor"),
          active,
        ),
      );
    };
    let view!: ReactTestRenderer;
    try {
      await act(async () => {
        view = create(React.createElement(AuthProvider, null, React.createElement(BatchPage)));
      });
      assert.equal(rows(view).length, 20);
      await click(view, "Carregar mais jobs");
      if (failMore) {
        assert.equal(rows(view).length, 20);
        assert.match(
          view.root
            .findAll((node) => node.props.role === "alert")
            .map(textOf)
            .join(""),
          /Histórico indisponível/,
        );
        await click(view, "Carregar mais jobs");
      }
      assert.equal(rows(view).length, 40);
      while (button(view, "Carregar mais jobs")) await click(view, "Carregar mais jobs");
      assert.equal(rows(view).length, 125);
      assert.equal(new Set(rows(view).map((row) => textOf(row.findAllByType("td")[0]))).size, 125);
      const old = rows(view).at(-1)!;
      assert.match(textOf(old), /a-0/);
      await act(async () => {
        await old.findAllByType("button")[0].props.onClick();
      });
      assert.equal(commands.length, 1);
      assert.match(commands[0], /a-0\/resume$/);
      const filter = view.root.findAllByType("select").find((node) => node.props.value === "")!;
      await act(async () => {
        filter.props.onChange({ target: { value: "FAILED" } });
      });
      assert.equal(rows(view).length, 20);
      assert.equal(queries.at(-1)!.searchParams.get("status"), "FAILED");
      assert.equal(queries.at(-1)!.searchParams.get("cursor"), null);
      assert.ok(view.root.findAllByType("span").some((node) => textOf(node) === "Na fila · a-0"));
      assert.ok(rows(view).every((row) => !textOf(row).includes("a-0")));
      active = { ...job("a-0", "RUNNING"), progress: { processed: 75, total: 100 } };
      await click(view, "Atualizar histórico");
      assert.ok(view.root.findAllByType("span").some((node) => textOf(node) === "Rodando · a-0"));
      assert.ok(view.root.findAllByType("p").some((node) => textOf(node) === "75%"));
      active = null;
      if (failMore) {
        shouldFail = true;
        await click(view, "Carregar mais jobs");
        assert.equal(rows(view).length, 20);
        assert.ok(view.root.findAll((node) => node.props.role === "alert").length);
      } else {
        await click(view, "Atualizar histórico");
      }
      assert.ok(
        view.root.findAllByType("p").some((node) => textOf(node) === "Nenhum job em andamento."),
      );
      assert.equal(commands.length, 1);
    } finally {
      await act(async () => view?.unmount());
      globalThis.fetch = original;
    }
  });
}

test("troca de sessão reinicia páginas e descarta resposta antiga com dados e job ativo de outra empresa", async () => {
  const original = globalThis.fetch;
  let tenant = "a";
  let auth!: ReturnType<typeof useAuth>;
  let release!: (response: Response) => void;
  const requests: URL[] = [];
  function Probe() {
    auth = useAuth();
    return null;
  }
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/auth/config")) return Response.json({ mode: "local" });
    if (String(url).includes("/auth/")) return Response.json(meFor("GESTOR_CADASTRO"));
    const query = new URL(String(url), "http://localhost");
    requests.push(query);
    if (tenant === "a" && query.searchParams.has("cursor"))
      return new Promise<Response>((resolve) => {
        release = resolve;
      });
    return Response.json(page(history(tenant), query.searchParams.get("cursor")));
  };
  let view!: ReactTestRenderer;
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
    await act(async () => {
      void button(view, "Carregar mais jobs")!.props.onClick();
    });
    assert.ok(release);
    tenant = "b";
    await act(async () => {
      assert.equal(await auth.signIn("GESTOR_CADASTRO"), true);
    });
    assert.equal(rows(view).length, 20);
    assert.equal(requests.at(-1)!.searchParams.get("cursor"), null);
    await act(async () => {
      release(Response.json(page(history("a"), "page:20", job("a-0", "RUNNING"))));
    });
    assert.ok(rows(view).every((row) => textOf(row).includes("b-")));
    assert.equal(
      view.root.findAllByType("span").some((node) => textOf(node).includes("a-0")),
      false,
    );
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = original;
  }
});
