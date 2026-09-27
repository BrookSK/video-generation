import { describe, expect, it } from "vitest";

import { ApiError, request, restoreSession } from "./api";
import { ANA, apiError, installFakeApi, json, type FakeApi } from "./test/fakeApi";

const calls = (api: FakeApi, method: string, path: string) =>
  api.requests.filter((r) => r.method === method && r.path === path);

describe("CSRF girado por outra aba", () => {
  it("busca o token vigente uma vez e reenvia a mutação com o mesmo corpo", async () => {
    const api = installFakeApi({ signedIn: ANA });
    api.on("POST", "/panel/scenes", () => json(201, { id: "cena-1" }));
    await restoreSession();
    const oldToken = api.csrf;
    // Outra aba chamou GET /panel/auth/me: o token desta aba deixou de valer.
    api.csrf = "csrf-outra-aba";

    const body = new FormData();
    body.append("name", "Estúdio claro");
    await expect(request("POST", "/panel/scenes", body)).resolves.toEqual({ id: "cena-1" });

    const [first, retry, ...rest] = calls(api, "POST", "/panel/scenes");
    expect(rest).toHaveLength(0);
    expect(first?.headers["X-CSRF-Token"]).toBe(oldToken);
    expect(retry?.headers["X-CSRF-Token"]).toBe(api.csrf);
    expect(retry?.body).toBe(body);
    expect(calls(api, "GET", "/panel/auth/me")).toHaveLength(2);
  });

  it("desiste depois de um único reenvio, sem entrar em laço", async () => {
    const api = installFakeApi({ signedIn: ANA });
    api.on("DELETE", "/panel/scenes/cena-1", () =>
      apiError(403, "CSRF_INVALID", "Token CSRF ausente ou inválido."),
    );
    await restoreSession();

    const error = await request("DELETE", "/panel/scenes/cena-1").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(403);
    expect((error as ApiError).code).toBe("CSRF_INVALID");
    expect(calls(api, "DELETE", "/panel/scenes/cena-1")).toHaveLength(2);
    expect(calls(api, "GET", "/panel/auth/me")).toHaveLength(2);
  });

  it("não reenvia em 403 de outro motivo", async () => {
    const api = installFakeApi({ signedIn: ANA });
    api.on("POST", "/panel/users", () => apiError(403, "FORBIDDEN", "Sem permissão."));
    await restoreSession();

    await expect(request("POST", "/panel/users", { username: "x" })).rejects.toMatchObject({
      status: 403,
      code: "FORBIDDEN",
    });
    expect(calls(api, "POST", "/panel/users")).toHaveLength(1);
    expect(calls(api, "GET", "/panel/auth/me")).toHaveLength(1);
  });
});
