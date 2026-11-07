import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider, useAuth } from "../src/lib/auth";
import { meFor } from "../src/lib/permissions";
import { QueuePage } from "../src/features/sanitization/QueuePage";
import { ProposalReview } from "../src/features/sanitization/ProposalReview";
import { proposals } from "../src/mocks/queue";
Object.assign(globalThis, { React, IS_REACT_ACT_ENVIRONMENT: true, self: globalThis });
test("retorno preserva páginas, filtro e posição; decisão e troca de sessão atualizam a fila", async () => {
  process.env.NEXT_PUBLIC_DATA_SOURCE = "api";
  const previousFetch = globalThis.fetch;
  let currentMe = meFor("GESTOR_CADASTRO");
  let first = {
    ...proposals[0],
    id: "first",
    title: "Primeira",
    proposal_type: "MERGE" as const,
  };
  const second = { ...first, id: "second", title: "Segunda" };
  let third = { ...first, id: "third", title: "Terceira" };
  let reads = 0;
  let discover = false;
  let showHistory = false;
  let tailExists = false;
  const tail = { ...first, id: "tail", title: "Proposta nova no final" };
  const discovered = { ...first, id: "new", title: "Nova proposta" };
  let delayed = false;
  let release!: (response: Response) => void;
  let delayedSignal: AbortSignal | undefined;
  const positions: string[] = [];
  Object.assign(globalThis, {
    window: {
      location: { pathname: "/saneamento/" },
      scrollY: 640,
      scrollTo(_x: number, y: number) {
        positions.push(`scroll-${y}`);
      },
      addEventListener() {},
      removeEventListener() {},
    },
    document: {
      documentElement: { dataset: {} },
      getElementById: (id: string) =>
        third.status === "REJECTED" ? null : { scrollIntoView: () => positions.push(id) },
    },
    requestAnimationFrame: (callback: () => void) => {
      callback();
      return 1;
    },
    cancelAnimationFrame() {},
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    fetch: async (url: string, options: RequestInit) => {
      if (url.includes("/auth/config")) return Response.json({ mode: "local" });
      if (url.includes("/auth/local-session")) {
        currentMe = meFor("AUDITOR_FISCAL");
        return Response.json(currentMe);
      }
      if (url.includes("/auth/logout")) return Response.json({});
      if (url.includes("/auth/me")) return Response.json(currentMe);
      if (url.includes("/queue")) {
        reads++;
        if (delayed && url.includes("cursor=page2")) {
          delayedSignal = options.signal ?? undefined;
          return new Promise<Response>((resolve) => {
            release = resolve;
          });
        }
        if (url.includes("cursor=page3"))
          return Response.json({ items: [tail], next_cursor: null });
        if (url.includes("status=DECIDED"))
          return Response.json({
            items: showHistory ? [{ ...third, id: "history", title: "Nova decisão externa" }] : [],
            next_cursor: null,
          });
        return Response.json(
          url.includes("cursor=page2")
            ? {
                items: [second, third].filter((item) => item.status === "PENDING"),
                next_cursor: tailExists ? "page3" : null,
              }
            : { items: discover ? [discovered, first] : [first, second], next_cursor: "page2" },
        );
      }
      if (url.includes("/decide")) {
        third = {
          ...third,
          status: "REJECTED",
          technical_review_status: "REJECTED",
          version: 2,
          allowed_actions: [],
        };
        return Response.json({ ...third, proposal_id: third.id, audit_event_id: "audit" });
      }
      if (delayed) {
        delayedSignal = options.signal ?? undefined;
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }
      return Response.json(
        url.endsWith("/new")
          ? discovered
          : url.endsWith("/third")
            ? third
            : url.endsWith("/second")
              ? second
              : first,
      );
    },
  });
  let auth!: ReturnType<typeof useAuth>;
  function Controls() {
    auth = useAuth();
    return null;
  }
  function Gate({ children }: { children: React.ReactNode }) {
    const { ready, me, sessionBusy } = useAuth();
    return ready && me && !sessionBusy ? children : null;
  }
  let view!: ReactTestRenderer;
  const render = async (screen: React.ReactNode) => {
    await act(async () => {
      const element = React.createElement(
        AuthProvider,
        null,
        React.createElement(Controls),
        React.createElement(Gate, null, screen),
      );
      if (view) view.update(element);
      else view = create(element);
    });
  };
  const titles = () =>
    view.root
      .findAllByType("a")
      .filter((a) => a.props.className === "font-semibold hover:text-verde")
      .map((a) => a.children.join(""));
  try {
    await render(React.createElement(QueuePage));
    await act(async () =>
      view.root
        .findAllByProps({ role: "tab" })
        .find((tab) => tab.children.includes("Fiscal"))!
        .props.onClick(),
    );
    await act(async () =>
      view.root.findByType("select").props.onChange({ target: { value: "MERGE" } }),
    );
    await act(async () =>
      view.root
        .findAllByType("button")
        .find((b) => b.children.includes("Carregar mais propostas"))!
        .props.onClick(),
    );
    assert.deepEqual(titles(), ["Primeira", "Segunda", "Terceira"]);
    const pageReads = reads;
    const link = view.root.findAllByType("a").find((a) => a.children.includes("Terceira"))!;
    await act(async () => link.props.onClick?.({}));
    // Voltar do navegador remonta a mesma rota, sem exigir o link da revisão.
    await render(React.createElement("p", null, "revisão"));
    discover = true;
    tailExists = true;
    first = { ...first, title: "Primeira atualizada por outra pessoa", version: 2 };
    await render(React.createElement(QueuePage));
    assert.deepEqual(titles(), [
      "Nova proposta",
      "Primeira atualizada por outra pessoa",
      "Segunda",
      "Terceira",
    ]);
    assert.ok(positions.includes("proposal-third"));
    await act(async () =>
      view.root
        .findAllByType("button")
        .find((b) => b.children.includes("Carregar mais propostas"))!
        .props.onClick(),
    );
    assert.ok(
      titles().includes("Proposta nova no final"),
      "fila antes esgotada volta a permitir paginação",
    );
    await render(React.createElement(ProposalReview, { proposal: third }));
    assert.match(view.root.findAllByType("a")[0].props.href, /^\/saneamento\/?$/);
    await act(async () =>
      view.root
        .findAllByType("input")
        .find((i) => i.props.placeholder)
        ?.props.onChange({ target: { value: "Revisado" } }),
    );
    await act(async () =>
      view.root
        .findAllByType("button")
        .find((b) => b.children.includes(" Rejeitar"))!
        .props.onClick(),
    );
    await render(React.createElement(QueuePage));
    assert.equal(view.root.findByType("select").props.value, "MERGE");
    assert.deepEqual(titles(), [
      "Nova proposta",
      "Primeira atualizada por outra pessoa",
      "Segunda",
      "Proposta nova no final",
    ]);
    assert.ok(positions.includes("scroll-640"));
    assert.equal(
      view.root.findAllByProps({ role: "tab" }).find((tab) => tab.children.includes("Fiscal"))!
        .props["aria-selected"],
      true,
    );
    assert.ok(reads > pageReads, "revalida páginas sem exigir paginação manual");
    await render(React.createElement("p", null, "revisão"));
    delayed = true;
    await render(React.createElement(QueuePage));
    assert.ok(release, "revalidação iniciou");
    const canceled = release;
    const canceledSignal = delayedSignal;
    await render(React.createElement("p", null, "outra revisão antes da atualização terminar"));
    delayed = false;
    await render(React.createElement(QueuePage));
    await act(async () => canceled(Response.json({ ...first, title: "Resposta cancelada" })));
    assert.equal(canceledSignal?.aborted, true);
    assert.equal(view.root.findByType("select").props.value, "MERGE");
    assert.deepEqual(titles(), [
      "Nova proposta",
      "Primeira atualizada por outra pessoa",
      "Segunda",
      "Proposta nova no final",
    ]);
    await render(React.createElement("p", null, "revisão"));
    delayed = true;
    await render(React.createElement(QueuePage));
    await act(async () => auth.switchPersona("AUDITOR_FISCAL"));
    assert.equal(view.root.findByType("select").props.value, "ALL");
    assert.equal(delayedSignal?.aborted, true);
    await act(async () => release(Response.json({ ...first, title: "Privado da sessão antiga" })));
    assert.ok(!titles().includes("Privado da sessão antiga"));
    assert.ok(reads > pageReads, "nova sessão carrega sua própria fila");
    await act(async () => {
      await auth.signOut();
    });
    delayed = false;
    await act(async () => {
      await auth.signIn("AUDITOR_FISCAL");
    });
    assert.equal(view.root.findByType("select").props.value, "ALL");
    await act(async () =>
      view.root
        .findAllByProps({ role: "tab" })
        .find((tab) => tab.children.includes("Decididas"))!
        .props.onClick(),
    );
    assert.deepEqual(titles(), []);
    await render(React.createElement("p", null, "fora da fila vazia"));
    showHistory = true;
    await render(React.createElement(QueuePage));
    assert.deepEqual(titles(), ["Nova decisão externa"]);
    await act(async () => {
      await auth.signOut();
    });
    assert.equal(auth.me, null);
  } finally {
    await act(async () => view?.unmount());
    globalThis.fetch = previousFetch;
  }
});
