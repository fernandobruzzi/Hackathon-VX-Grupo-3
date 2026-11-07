import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { AuthProvider } from "../src/lib/auth";
import { OrdersPage } from "../src/features/orders/OrdersPage";
import { QueuePage } from "../src/features/sanitization/QueuePage";
import { ChatPage } from "../src/features/chat/ChatPage";
Object.assign(globalThis, {
  React,
  self: globalThis,
  IS_REACT_ACT_ENVIRONMENT: true,
  window: {
    location: { pathname: "/" },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    addEventListener() {},
    removeEventListener() {},
  },
  document: { documentElement: { dataset: {} } },
  localStorage: { getItem: () => "GESTOR_CADASTRO", setItem() {} },
});
for (const [name, Page] of [
  ["Pedidos de cadastro", OrdersPage],
  ["Fila de saneamento", QueuePage],
  ["Detalhes do chat", ChatPage],
] as const) {
  test(`${name}: teclado, ativação manual e painéis`, async () => {
    process.env.NEXT_PUBLIC_DATA_SOURCE = "mock";
    localStorage.getItem = () => (name === "Detalhes do chat" ? "DEV_TI" : "GESTOR_CADASTRO");
    let view!: ReactTestRenderer;
    const focused: string[] = [];
    try {
      await act(async () => {
        view = create(React.createElement(AuthProvider, null, React.createElement(Page)), {
          createNodeMock: (element: React.ReactElement<{ role?: string; id: string }>) =>
            element.props.role === "tab" ? { focus: () => focused.push(element.props.id) } : null,
        });
      });
      const tabs = () => view.root.findAllByProps({ role: "tab" });
      const list = view.root.findByProps({ role: "tablist" });
      assert.equal(list.props["aria-label"], name);
      const initial = tabs().findIndex((tab) => tab.props["aria-selected"]);
      const check = () => {
        assert.equal(tabs().filter((tab) => tab.props.tabIndex === 0).length, 1);
        for (const tab of tabs()) {
          const panel = view.root.findByProps({ id: tab.props["aria-controls"] });
          assert.equal(panel.props.role, "tabpanel");
          assert.equal(panel.props["aria-labelledby"], tab.props.id);
          assert.equal(panel.props.hidden, !tab.props["aria-selected"]);
        }
      };
      check();
      const key = async (index: number, key: string) => {
        await act(async () => tabs()[index].props.onKeyDown({ key, preventDefault() {} }));
      };
      await key(initial, "ArrowRight");
      const next = (initial + 1) % tabs().length;
      assert.equal(focused.at(-1), tabs()[next].props.id);
      assert.equal(tabs()[initial].props["aria-selected"], true);
      await key(next, "End");
      assert.equal(focused.at(-1), tabs().at(-1)!.props.id);
      await key(tabs().length - 1, "Home");
      assert.equal(focused.at(-1), tabs()[0].props.id);
      await key(0, "ArrowLeft");
      assert.equal(focused.at(-1), tabs().at(-1)!.props.id);
      // Enter/Espaço geram click nativo em button.
      await act(async () => tabs()[next].props.onClick());
      assert.equal(tabs()[next].props["aria-selected"], true);
      check();
      await act(async () =>
        list.props.onBlur({ currentTarget: { contains: () => false }, relatedTarget: null }),
      );
      assert.equal(tabs()[next].props.tabIndex, 0);
      check();
    } finally {
      await act(async () => view?.unmount());
      delete process.env.NEXT_PUBLIC_DATA_SOURCE;
    }
  });
}
