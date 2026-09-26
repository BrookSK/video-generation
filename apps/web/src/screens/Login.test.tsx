import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { request } from "../api";
import { App } from "../App";
import { ANA, installFakeApi, json } from "../test/fakeApi";

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

async function fillLogin(email: string, password: string) {
  const user = userEvent.setup();
  if (email) await user.type(screen.getByLabelText("E-mail"), email);
  if (password) await user.type(screen.getByLabelText("Senha"), password);
  return user;
}

const loginCalls = (api: ReturnType<typeof installFakeApi>) =>
  api.requests.filter((r) => r.path === "/panel/auth/login");

describe("Login e sessão do painel", () => {
  it("redireciona para /entrar quando não há sessão", async () => {
    const api = installFakeApi();
    renderApp("/avatares");

    expect(await screen.findByRole("heading", { name: "Entrar no Estúdio" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(api.requests.map((r) => `${r.method} ${r.path}`)).toEqual(["GET /panel/auth/me"]);
  });

  it("mostra o erro junto ao campo de senha com credencial errada", async () => {
    const api = installFakeApi();
    renderApp("/entrar");
    await screen.findByRole("heading", { name: "Entrar no Estúdio" });

    const user = await fillLogin(ANA.username, "senha-errada-000");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    const password = screen.getByLabelText("Senha");
    expect(await screen.findByText("E-mail ou senha incorretos. Confira e tente de novo.")).toBeInTheDocument();
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAccessibleDescription("E-mail ou senha incorretos. Confira e tente de novo.");
    expect(password).toHaveFocus();
    expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();
    expect(loginCalls(api)).toHaveLength(1);
    expect(loginCalls(api)[0]?.body).toEqual({ username: ANA.username, password: "senha-errada-000" });
  });

  it("confere e-mail e senha no cliente antes de chamar a API", async () => {
    const api = installFakeApi();
    renderApp("/entrar");
    await screen.findByRole("heading", { name: "Entrar no Estúdio" });

    const user = await fillLogin("ana", "");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(screen.getByLabelText("E-mail")).toHaveAccessibleDescription(
      "Confira o e-mail: falta algo como nome@empresa.com.br.",
    );
    expect(screen.getByLabelText("Senha")).toHaveAccessibleDescription("Informe a senha.");
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
    expect(loginCalls(api)).toHaveLength(0);
  });

  it("mostra e esconde a senha", async () => {
    installFakeApi();
    renderApp("/entrar");
    await screen.findByRole("heading", { name: "Entrar no Estúdio" });
    const user = userEvent.setup();

    const password = screen.getByLabelText("Senha");
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Mostrar senha" }));
    expect(password).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Esconder senha" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("entra com a credencial certa, desabilita o botão durante o envio e volta à página pedida", async () => {
    const api = installFakeApi();
    let release: () => void = () => {};
    api.on("POST", "/panel/auth/login", async () => {
      await new Promise<void>((resolve) => (release = resolve));
      api.signedIn = ANA;
      api.csrf = "csrf-login";
      const { password: _password, ...sessionUser } = ANA;
      return json(200, { csrf_token: "csrf-login", expires_at: "2026-10-03T12:00:00Z", user: sessionUser });
    });
    renderApp("/cenarios");
    await screen.findByRole("heading", { name: "Entrar no Estúdio" });

    const user = await fillLogin(ANA.username, ANA.password);
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    const busy = await screen.findByRole("button", { name: "Entrando…" });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(loginCalls(api)).toHaveLength(1);

    await act(async () => release());
    expect(await screen.findByRole("heading", { level: 1, name: "Cenários" })).toBeInTheDocument();
    const nav = screen.getByRole("complementary", { name: "Navegação principal" });
    expect(within(nav).getByRole("link", { name: "Cenários" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByText("Ana Souza")).toBeInTheDocument();
  });

  it("recupera a sessão ao recarregar e usa o CSRF novo nas mutações", async () => {
    const api = installFakeApi({ signedIn: ANA });
    renderApp("/acesso");

    expect(await screen.findByRole("heading", { level: 1, name: "Usuários e chaves" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Entrar no Estúdio" })).not.toBeInTheDocument();
    expect(loginCalls(api)).toHaveLength(0);
    const restoredCsrf = api.csrf;
    expect(restoredCsrf).not.toBeNull();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Sair" }));

    expect(await screen.findByRole("heading", { name: "Entrar no Estúdio" })).toBeInTheDocument();
    const logoutCall = api.requests.find((r) => r.path === "/panel/auth/logout");
    expect(logoutCall?.headers["X-CSRF-Token"]).toBe(restoredCsrf);
    expect(api.signedIn).toBeNull();
  });

  it("volta para /entrar quando uma rota responde 401 com a sessão expirada", async () => {
    const api = installFakeApi({ signedIn: ANA });
    api.on("GET", "/panel/users", () => json(200, []));
    renderApp("/avatares");
    await screen.findByRole("heading", { level: 1, name: "Avatares" });

    api.expireSession();
    await act(async () => {
      await request("GET", "/panel/users").catch(() => undefined);
    });

    expect(await screen.findByRole("heading", { name: "Entrar no Estúdio" })).toBeInTheDocument();
  });
});
