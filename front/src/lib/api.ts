import type { components, paths } from "../types/api.generated";

type Method = "get" | "post";
type PublicPath = Extract<keyof paths, `/api/v1/${string}`>;
type Operation<P extends keyof paths, M extends Method> = M extends keyof paths[P]
  ? NonNullable<paths[P][M]>
  : never;
type Json<T> = T extends { content: { "application/json": infer Value } } ? Value : undefined;
type ResponseBody<O> = O extends { responses: infer Responses }
  ? Json<Responses[Extract<keyof Responses, 200 | 202 | 204>]>
  : never;
type Parameters<O, K extends "path" | "query"> = O extends { parameters: infer Params }
  ? K extends keyof Params
    ? NonNullable<Params[K]>
    : never
  : never;
type Options<O> = {
  signal?: AbortSignal;
  idempotencyKey?: string;
} & (O extends { requestBody: infer Body } ? { body: Json<Body> } : { body?: never }) &
  ([Parameters<O, "path">] extends [never]
    ? { params?: never }
    : { params: Parameters<O, "path"> }) & { query?: Parameters<O, "query"> };

export class StaleSessionError extends Error {
  constructor() {
    super("A sessão mudou durante a requisição.");
    this.name = "StaleSessionError";
  }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly error: components["schemas"]["ApiError"]["error"],
  ) {
    super(error.message);
    this.name = "ApiError";
  }
}

function isErrorEnvelope(value: unknown): value is components["schemas"]["ApiError"] {
  if (!value || typeof value !== "object" || !("error" in value)) return false;
  const error = value.error;
  return (
    !!error &&
    typeof error === "object" &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string" &&
    "request_id" in error &&
    typeof error.request_id === "string" &&
    "details" in error &&
    !!error.details &&
    typeof error.details === "object" &&
    !Array.isArray(error.details)
  );
}

export function createApiClient({
  getCsrfToken,
  fetch: transport = globalThis.fetch,
  onUnauthorized,
  getSessionRevision,
}: {
  getCsrfToken: () => string | null;
  fetch?: typeof globalThis.fetch;
  onUnauthorized?: () => void;
  getSessionRevision?: () => number;
}) {
  return {
    async request<
      P extends PublicPath,
      M extends { [K in Method]: Operation<P, K> extends never ? never : K }[Method],
    >(
      method: M,
      path: P,
      ...args: {} extends Options<Operation<P, M>>
        ? [options?: Options<Operation<P, M>>]
        : [options: Options<Operation<P, M>>]
    ): Promise<ResponseBody<Operation<P, M>>> {
      const revision = getSessionRevision?.();
      const options = args[0];
      let url: string = path;
      for (const [name, value] of Object.entries(options?.params ?? {})) {
        url = url.replace(`{${name}}`, encodeURIComponent(String(value)));
      }
      if (url.includes("{")) throw new Error("Parâmetro de rota ausente.");
      const query = new URLSearchParams();
      for (const [name, value] of Object.entries(options?.query ?? {})) {
        if (value !== undefined && value !== null) query.set(name, String(value));
      }
      if (query.size) url += `?${query}`;

      const headers = new Headers({ Accept: "application/json" });
      if (method === "post") {
        headers.set("Content-Type", "application/json");
        headers.set("Idempotency-Key", options?.idempotencyKey ?? crypto.randomUUID());
        if (path !== "/api/v1/auth/sso-callback" && path !== "/api/v1/auth/local-session") {
          const token = getCsrfToken();
          if (!token)
            throw new Error("Sessão sem token CSRF. Consulte /auth/me antes de escrever.");
          headers.set("X-CSRF-Token", token);
        }
      }

      const response = await transport(url, {
        method: method.toUpperCase(),
        credentials: "include",
        headers,
        body: options?.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options?.signal,
      });
      const text = await response.text();
      let data: unknown;
      try {
        data = text ? JSON.parse(text) : undefined;
      } catch {
        // Respostas de proxy podem não seguir o contrato JSON.
      }
      // Uma resposta da sessão anterior não pode alterar dados nem revogar a sessão atual.
      if (
        path !== "/api/v1/auth/config" &&
        getSessionRevision &&
        revision !== getSessionRevision()
      ) {
        throw new StaleSessionError();
      }
      if (!response.ok) {
        if (response.status === 401) onUnauthorized?.();
        throw new ApiError(
          response.status,
          isErrorEnvelope(data)
            ? data.error
            : {
                code: "HTTP_ERROR",
                message: "Não foi possível concluir a solicitação.",
                request_id: response.headers.get("X-Request-ID") ?? "",
                details: {},
              },
        );
      }
      if (response.status !== 204 && data === undefined) {
        throw new ApiError(response.status, {
          code: "INVALID_RESPONSE",
          message: "A API retornou uma resposta inválida.",
          request_id: response.headers.get("X-Request-ID") ?? "",
          details: {},
        });
      }
      return data as ResponseBody<Operation<P, M>>;
    },
  };
}
