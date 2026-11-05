import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, createApiClient } from "../src/lib/api";

const id = "66666666-6666-4666-8666-666666666666";
const decision = {
  expected_version: 1,
  review_area: "TECHNICAL" as const,
  decision: "APPROVE" as const,
  reason: "Identidade conferida.",
};

function setup(response = new Response("{}"), csrf: string | null = "csrf-current") {
  const calls: { url: string; init: RequestInit }[] = [];
  const api = createApiClient({
    getCsrfToken: () => csrf,
    fetch: async (url, init) => {
      calls.push({ url: String(url), init: init! });
      return response.clone();
    },
  });
  return { api, calls };
}

test("leitura envia cookie e codifica filtros sem cabeçalhos de escrita", async () => {
  const { api, calls } = setup();
  await api.request("get", "/api/v1/materials", { query: { q: "válvula & filtro", limit: 20 } });
  assert.equal(calls[0].url, "/api/v1/materials?q=v%C3%A1lvula+%26+filtro&limit=20");
  assert.equal(calls[0].init.credentials, "include");
  const headers = new Headers(calls[0].init.headers);
  assert.equal(headers.has("X-CSRF-Token"), false);
  assert.equal(headers.has("Idempotency-Key"), false);
});

test("escrita envia JSON, CSRF atual e chave estável para repetição explícita", async () => {
  const { api, calls } = setup();
  for (let attempt = 0; attempt < 2; attempt++) {
    await api.request("post", "/api/v1/sanitization/{id}/decide", {
      params: { id },
      body: decision,
      idempotencyKey: id,
    });
  }
  for (const call of calls) {
    assert.equal(call.url, `/api/v1/sanitization/${id}/decide`);
    assert.equal(call.init.credentials, "include");
    assert.deepEqual(JSON.parse(call.init.body as string), decision);
    const headers = new Headers(call.init.headers);
    assert.equal(headers.get("X-CSRF-Token"), "csrf-current");
    assert.equal(headers.get("Idempotency-Key"), id);
    assert.equal(headers.get("Content-Type"), "application/json");
  }
});

test("cada nova escrita gera um UUID e consulta o CSRF novamente", async () => {
  const calls: Headers[] = [];
  let token = "first";
  const api = createApiClient({
    getCsrfToken: () => token,
    fetch: async (_url, init) => {
      calls.push(new Headers(init?.headers));
      return new Response("{}");
    },
  });
  await api.request("post", "/api/v1/auth/demo/switch", {
    body: { session_handle: "demo-session" },
  });
  token = "second";
  await api.request("post", "/api/v1/auth/demo/switch", {
    body: { session_handle: "demo-session" },
  });
  assert.equal(calls[0].get("X-CSRF-Token"), "first");
  assert.equal(calls[1].get("X-CSRF-Token"), "second");
  const key = calls[0].get("Idempotency-Key");
  assert.match(key!, /^[0-9a-f-]{36}$/);
  assert.notEqual(key, calls[1].get("Idempotency-Key"));
});

test("escrita sem CSRF falha antes do transporte; callback de login é público", async () => {
  const { api, calls } = setup(new Response("{}"), null);
  await assert.rejects(
    api.request("post", "/api/v1/auth/demo/switch", {
      body: { session_handle: "demo-session" },
    }),
    /CSRF/,
  );
  assert.equal(calls.length, 0);
  await api.request("post", "/api/v1/auth/sso-callback", {
    body: { code: "code", state: "state" },
  });
  assert.equal(new Headers(calls[0].init.headers).has("X-CSRF-Token"), false);
});

for (const status of [401, 403, 404, 409, 422, 429, 503]) {
  test(`preserva erro padronizado HTTP ${status} sem repetir escrita`, async () => {
    const error = {
      code: "VERSION_CONFLICT",
      message: "Atualize a proposta.",
      request_id: "req-001",
      details: { current_version: 2 },
    };
    const { api, calls } = setup(new Response(JSON.stringify({ error }), { status }));
    await assert.rejects(
      api.request("post", "/api/v1/sanitization/{id}/decide", { params: { id }, body: decision }),
      (value: unknown) => {
        assert.ok(value instanceof ApiError);
        assert.equal(value.status, status);
        assert.deepEqual(value.error, error);
        return true;
      },
    );
    assert.equal(calls.length, 1);
  });
}

test("erro de proxy não expõe HTML; resposta inválida é identificada", async () => {
  const { api } = setup(
    new Response("<html>proxy</html>", { status: 503, headers: { "X-Request-ID": "proxy-1" } }),
  );
  await assert.rejects(api.request("get", "/api/v1/auth/me"), (value: unknown) => {
    assert.ok(value instanceof ApiError);
    assert.equal(value.error.code, "HTTP_ERROR");
    assert.equal(value.error.request_id, "proxy-1");
    assert.ok(!value.message.includes("<html>"));
    return true;
  });
  await assert.rejects(
    setup(new Response("bad-json")).api.request("get", "/api/v1/auth/me"),
    (value: unknown) => value instanceof ApiError && value.error.code === "INVALID_RESPONSE",
  );
  await assert.rejects(
    setup(new Response("")).api.request("get", "/api/v1/auth/me"),
    (value: unknown) => value instanceof ApiError && value.error.code === "INVALID_RESPONSE",
  );
});

test("cancelamento e falha de rede propagam sem reenvio", async () => {
  const controller = new AbortController();
  let calls = 0;
  const failure = new TypeError("Network unavailable");
  const api = createApiClient({
    getCsrfToken: () => "csrf",
    fetch: async (_url, init) => {
      calls++;
      assert.equal(init?.signal, controller.signal);
      throw failure;
    },
  });
  await assert.rejects(
    api.request("get", "/api/v1/auth/me", { signal: controller.signal }),
    (value: unknown) => value === failure,
  );
  assert.equal(calls, 1);
});

// Verificações compiladas pelo typecheck, sem executar operações inválidas.
function checkRequestTypes(api: ReturnType<typeof createApiClient>) {
  // @ts-expect-error rota interna não pertence ao cliente de navegador
  void api.request("post", "/internal/v1/chat/run");
  // @ts-expect-error rota desconhecida
  void api.request("get", "/api/v1/unknown");
  // @ts-expect-error método não previsto para a rota
  void api.request("post", "/api/v1/auth/me");
  // @ts-expect-error corpo obrigatório
  void api.request("post", "/api/v1/chat/message");
  // @ts-expect-error parâmetro de rota obrigatório
  void api.request("get", "/api/v1/sanitization/{id}");
  // @ts-expect-error filtro fora do enum
  void api.request("get", "/api/v1/dashboard/metrics", { query: { view: "secret" } });
  void api.request("get", "/api/v1/auth/me").then((me) => {
    const token: string = me.csrf_token;
    return token;
  });
}
void checkRequestTypes;
