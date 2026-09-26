// Cliente da API do painel: fetch same-origin com o cookie de sessão e o token CSRF em memória.
// O CSRF nunca vai para storage do navegador; ao recarregar, GET /panel/auth/me emite outro.

export type SessionUser = {
  id: string;
  username: string;
  display_name: string | null;
};

export type Session = {
  csrf_token: string;
  expires_at: string;
  user: SessionUser;
};

type ErrorEnvelope = {
  error?: { code?: string; message?: string; field?: string };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;

  constructor(status: number, code: string, message: string, field: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

export const NETWORK_ERROR = "NETWORK_ERROR";

const LOGIN_PATH = "/panel/auth/login";
const SAFE_METHODS = new Set(["GET", "HEAD"]);

let csrfToken: string | null = null;
const unauthorizedListeners = new Set<() => void>();

/** Avisa quando uma rota responde 401: a sessão acabou e o painel volta para /entrar. */
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

async function toApiError(response: Response): Promise<ApiError> {
  let envelope: ErrorEnvelope = {};
  try {
    envelope = (await response.json()) as ErrorEnvelope;
  } catch {
    // Corpo fora do envelope (proxy, HTML de erro): fica a mensagem genérica.
  }
  const error = envelope.error ?? {};
  return new ApiError(
    response.status,
    error.code ?? "HTTP_" + response.status,
    error.message ?? "Não foi possível concluir a ação. Tente de novo.",
    error.field ?? null,
  );
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (!SAFE_METHODS.has(method) && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      ...(payload === undefined ? {} : { body: payload }),
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR, "Não foi possível falar com o servidor. Tente de novo em instantes.");
  }

  if (!response.ok) {
    const error = await toApiError(response);
    // Credencial errada no login também é 401, mas não encerra sessão nenhuma.
    if (response.status === 401 && path !== LOGIN_PATH) {
      csrfToken = null;
      unauthorizedListeners.forEach((listener) => listener());
    }
    throw error;
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function login(username: string, password: string): Promise<SessionUser> {
  const session = await request<Session>("POST", LOGIN_PATH, { username, password });
  csrfToken = session.csrf_token;
  return session.user;
}

/** Recupera a sessão do cookie ao abrir ou recarregar o painel; sem sessão devolve null. */
export async function restoreSession(): Promise<SessionUser | null> {
  try {
    const session = await request<Session>("GET", "/panel/auth/me");
    csrfToken = session.csrf_token;
    return session.user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

export async function logout(): Promise<void> {
  try {
    await request<void>("POST", "/panel/auth/logout");
  } finally {
    csrfToken = null;
  }
}
