// API do painel falsa para os testes: vi.fn no lugar de fetch, com as rotas /panel em memória.
// Segue o contrato da API real: cookie de sessão implícito, CSRF novo a cada login e a cada
// GET /panel/auth/me, X-CSRF-Token exigido em mutações e erros no envelope {error: {...}}.
import { vi, type Mock } from "vitest";

import type { SessionUser } from "../api";

export type FakeUser = SessionUser & { password: string };

export type RecordedRequest = {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
};

type Handler = (request: RecordedRequest) => Response | Promise<Response>;

export type FakeApi = {
  fetch: Mock<typeof fetch>;
  requests: RecordedRequest[];
  users: FakeUser[];
  /** Token CSRF vigente da sessão aberta; null quando não há sessão. */
  csrf: string | null;
  signedIn: FakeUser | null;
  /** Troca ou acrescenta o tratamento de uma rota. */
  on: (method: string, path: string, handler: Handler) => void;
  /** Encerra a sessão no servidor, como expiração ou remoção de acesso. */
  expireSession: () => void;
};

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function apiError(status: number, code: string, message: string, field?: string): Response {
  return json(status, { error: { code, message, ...(field ? { field } : {}), request_id: "req-test" } });
}

export const ANA: FakeUser = {
  id: "7c1a5a3e-0b8f-4f43-9d0e-3f1f7e0c2a11",
  username: "ana@empresa.com.br",
  display_name: "Ana Souza",
  password: "senha-correta-123",
};

let tokenCounter = 0;
const newToken = () => `csrf-${++tokenCounter}`;

export function installFakeApi(options: { users?: FakeUser[]; signedIn?: FakeUser | null } = {}): FakeApi {
  const routes = new Map<string, Handler>();

  const api: FakeApi = {
    fetch: vi.fn<typeof fetch>(),
    requests: [],
    users: options.users ?? [ANA],
    csrf: options.signedIn ? newToken() : null,
    signedIn: options.signedIn ?? null,
    on: (method, path, handler) => routes.set(`${method} ${path}`, handler),
    expireSession: () => {
      api.signedIn = null;
      api.csrf = null;
    },
  };

  const session = (user: FakeUser) => {
    api.csrf = newToken();
    const { password: _password, ...sessionUser } = user;
    return json(200, {
      csrf_token: api.csrf,
      expires_at: "2026-10-03T12:00:00Z",
      user: sessionUser,
    });
  };

  api.on("POST", "/panel/auth/login", ({ body }) => {
    const { username, password } = body as { username: string; password: string };
    const user = api.users.find((u) => u.username === username && u.password === password);
    if (!user) return apiError(401, "INVALID_CREDENTIALS", "Usuário ou senha inválidos.");
    api.signedIn = user;
    return session(user);
  });
  api.on("GET", "/panel/auth/me", () => session(api.signedIn!));
  api.on("POST", "/panel/auth/logout", () => {
    api.expireSession();
    return new Response(null, { status: 204 });
  });

  api.fetch.mockImplementation(async (input, init = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    const path = String(input);
    const headers = { ...(init.headers as Record<string, string> | undefined) };
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    const recorded = { method, path, headers, body };
    api.requests.push(recorded);

    const handler = routes.get(`${method} ${path}`);
    if (!handler) return apiError(404, "NOT_FOUND", "Recurso não encontrado.");
    if (path !== "/panel/auth/login") {
      if (!api.signedIn) {
        return apiError(401, "UNAUTHORIZED", "Sessão ausente ou expirada. Entre novamente.");
      }
      if (method !== "GET" && headers["X-CSRF-Token"] !== api.csrf) {
        return apiError(403, "CSRF_INVALID", "Token CSRF ausente ou inválido.");
      }
    }
    return handler(recorded);
  });

  vi.stubGlobal("fetch", api.fetch);
  return api;
}
