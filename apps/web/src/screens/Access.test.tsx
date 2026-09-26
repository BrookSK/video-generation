import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeAll, describe, expect, it } from "vitest";

import { App } from "../App";
import { ANA, apiError, installFakeApi, json, type FakeApi } from "../test/fakeApi";

const LUCAS = {
  id: "2b1f0c6e-7d11-4b8e-9d5f-1c0a3e9b7a22",
  username: "lucas@empresa.com.br",
  display_name: "Lucas N.",
  created_at: "2026-09-10T12:00:00Z",
  disabled_at: null,
};
const BRUNO_REMOVED = {
  id: "5d3e2a10-4c6b-4f7a-8e21-9b0c1d2e3f44",
  username: "bruno@empresa.com.br",
  display_name: "Bruno Lima",
  created_at: "2026-09-11T12:00:00Z",
  disabled_at: "2026-09-20T12:00:00Z",
};
const CRM_KEY = {
  id: "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  prefix: "avk_3f9a2c1b",
  description: "CRM de vendas",
  created_by_user_id: ANA.id,
  created_by_username: ANA.username,
  created_at: "2026-09-19T12:00:00Z",
  revoked_at: null,
  last_used_at: "2026-09-25T12:00:00Z",
};
const OLD_KEY = {
  ...CRM_KEY,
  id: "1f2e3d4c-5b6a-4978-8a1b-2c3d4e5f6a7b",
  prefix: "avk_91be07aa",
  description: "Teste de integração",
  revoked_at: "2026-09-22T12:00:00Z",
  last_used_at: null,
};
const FULL_KEY = "avk_bab0c299b855dc2c44b9a19bf8d7c01dc416b3b54e79b8a1Zx";

const anaRow = {
  id: ANA.id,
  username: ANA.username,
  display_name: ANA.display_name,
  created_at: "2026-09-01T12:00:00Z",
  disabled_at: null,
};

// O jsdom não implementa <dialog> modal; o teste imita showModal e close do navegador.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});

function setup() {
  const api = installFakeApi({ signedIn: ANA });
  api.on("GET", "/panel/users", () => json(200, [anaRow, LUCAS, BRUNO_REMOVED]));
  api.on("GET", "/panel/api-keys", () => json(200, [CRM_KEY, OLD_KEY]));
  render(
    <MemoryRouter initialEntries={["/acesso"]}>
      <App />
    </MemoryRouter>,
  );
  return { api, user: userEvent.setup() };
}

const calls = (api: FakeApi, method: string, path: string) =>
  api.requests.filter((r) => r.method === method && r.path === path);

const peopleList = () => screen.getByRole("list", { name: "Pessoas com acesso" });
const keysList = () => screen.getByRole("list", { name: "Chaves de API" });

async function itemOf(list: () => HTMLElement, text: string) {
  await screen.findByRole("heading", { level: 1, name: "Usuários e chaves" });
  const found = await within(list()).findByText(text);
  return found.closest("li") as HTMLElement;
}

describe("Tela de pessoas e chaves", () => {
  it("lista pessoas com acesso e marca quem está logado, sem Remover na própria linha", async () => {
    setup();

    const ana = await itemOf(peopleList, "Ana Souza");
    expect(within(ana).getByText("Você")).toBeInTheDocument();
    expect(within(ana).getByText("AS")).toBeInTheDocument();
    expect(within(ana).queryByRole("button", { name: /Remover/ })).not.toBeInTheDocument();

    const lucas = await itemOf(peopleList, "Lucas N.");
    expect(within(lucas).getByText("lucas@empresa.com.br")).toBeInTheDocument();
    expect(within(lucas).getByRole("button", { name: "Remover Lucas N." })).toBeInTheDocument();
    expect(within(peopleList()).queryByText("Bruno Lima")).not.toBeInTheDocument();
  });

  it("confere nome, e-mail e senha curta no cliente antes de adicionar", async () => {
    const { api, user } = setup();
    await itemOf(peopleList, "Ana Souza");

    await user.click(screen.getByRole("button", { name: "Adicionar pessoa" }));
    const dialog = screen.getByRole("dialog", { name: "Adicionar pessoa" });
    await user.type(within(dialog).getByLabelText("E-mail"), "carla");
    await user.type(within(dialog).getByLabelText("Senha inicial"), "curta123");
    await user.click(within(dialog).getByRole("button", { name: "Adicionar pessoa" }));

    expect(within(dialog).getByLabelText("Nome")).toHaveAccessibleDescription("Informe o nome.");
    expect(within(dialog).getByLabelText("Nome")).toHaveFocus();
    expect(within(dialog).getByLabelText("E-mail")).toHaveAccessibleDescription(
      "Informe um e-mail válido, como nome@empresa.com.br.",
    );
    const password = within(dialog).getByLabelText("Senha inicial");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAccessibleDescription(/A senha inicial precisa de pelo menos 12 caracteres\./);
    expect(calls(api, "POST", "/panel/users")).toHaveLength(0);
  });

  it("adiciona a pessoa e liga o erro do servidor ao campo pelo field", async () => {
    const { api, user } = setup();
    let attempts = 0;
    api.on("POST", "/panel/users", ({ body }) => {
      attempts += 1;
      if (attempts === 1) {
        return apiError(422, "VALIDATION_ERROR", "Já existe um usuário com o nome carla@empresa.com.br.", "username");
      }
      const { username, display_name } = body as { username: string; display_name: string };
      return json(201, { id: "c0ffee00-0000-4000-8000-000000000001", username, display_name, created_at: "2026-09-26T12:00:00Z", disabled_at: null });
    });
    await itemOf(peopleList, "Ana Souza");

    await user.click(screen.getByRole("button", { name: "Adicionar pessoa" }));
    const dialog = screen.getByRole("dialog", { name: "Adicionar pessoa" });
    await user.type(within(dialog).getByLabelText("Nome"), "Carla Dias");
    await user.type(within(dialog).getByLabelText("E-mail"), "carla@empresa.com.br");
    await user.type(within(dialog).getByLabelText("Senha inicial"), "senha-inicial-forte");
    await user.click(within(dialog).getByRole("button", { name: "Adicionar pessoa" }));

    const email = within(dialog).getByLabelText("E-mail");
    expect(await within(dialog).findByText("Já existe um usuário com o nome carla@empresa.com.br.")).toBeInTheDocument();
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveFocus();

    await user.click(within(dialog).getByRole("button", { name: "Adicionar pessoa" }));

    const carla = await itemOf(peopleList, "Carla Dias");
    expect(within(carla).getByRole("button", { name: "Remover Carla Dias" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const posts = calls(api, "POST", "/panel/users");
    expect(posts).toHaveLength(2);
    expect(posts[1]?.body).toEqual({
      username: "carla@empresa.com.br",
      display_name: "Carla Dias",
      password: "senha-inicial-forte",
    });
    expect(posts[1]?.headers["X-CSRF-Token"]).toBe(api.csrf);
  });

  it("remove o acesso só depois da confirmação embutida no item", async () => {
    const { api, user } = setup();
    api.on("POST", `/panel/users/${LUCAS.id}/disable`, () =>
      json(200, { ...LUCAS, disabled_at: "2026-09-26T12:00:00Z" }),
    );
    const lucas = await itemOf(peopleList, "Lucas N.");

    await user.click(within(lucas).getByRole("button", { name: "Remover Lucas N." }));
    const confirmation = within(lucas).getByRole("group", { name: "Confirmação" });
    expect(confirmation).toHaveTextContent("Vídeos pedidos por ela continuam no histórico.");
    expect(within(confirmation).getByRole("button", { name: "Remover acesso" })).toHaveFocus();

    await user.click(within(confirmation).getByRole("button", { name: "Cancelar" }));
    expect(within(lucas).queryByRole("group", { name: "Confirmação" })).not.toBeInTheDocument();
    expect(calls(api, "POST", `/panel/users/${LUCAS.id}/disable`)).toHaveLength(0);

    await user.click(within(lucas).getByRole("button", { name: "Remover Lucas N." }));
    await user.click(within(lucas).getByRole("button", { name: "Remover acesso" }));

    await waitFor(() => expect(within(peopleList()).queryByText("Lucas N.")).not.toBeInTheDocument());
    expect(within(peopleList()).getByText("Ana Souza")).toBeInTheDocument();
    expect(calls(api, "POST", `/panel/users/${LUCAS.id}/disable`)).toHaveLength(1);
  });

  it("mostra a chave completa uma única vez, copia e some ao fechar, ficando só o prefixo", async () => {
    const { api, user } = setup();
    api.on("POST", "/panel/api-keys", ({ body }) =>
      json(201, {
        ...CRM_KEY,
        id: "7e6d5c4b-3a29-4180-9f7e-6d5c4b3a2918",
        prefix: FULL_KEY.slice(0, 12),
        description: (body as { description: string }).description,
        created_at: "2026-09-26T12:00:00Z",
        last_used_at: null,
        key: FULL_KEY,
      }),
    );
    await itemOf(keysList, "CRM de vendas");
    expect(document.body).not.toHaveTextContent(FULL_KEY);

    await user.click(screen.getByRole("button", { name: "Criar chave" }));
    const form = screen.getByRole("dialog", { name: "Criar chave de API" });
    await user.click(within(form).getByRole("button", { name: "Criar chave" }));
    expect(within(form).getByLabelText("Nome da chave")).toHaveAccessibleDescription(
      "Dê um nome à chave para saber qual sistema a usa.",
    );
    expect(calls(api, "POST", "/panel/api-keys")).toHaveLength(0);

    await user.type(within(form).getByLabelText("Nome da chave"), "Site institucional");
    await user.click(within(form).getByRole("button", { name: "Criar chave" }));

    const created = await screen.findByRole("dialog", { name: "Chave criada" });
    expect(calls(api, "POST", "/panel/api-keys")[0]?.body).toEqual({ description: "Site institucional" });
    expect(within(created).getByText(FULL_KEY)).toBeInTheDocument();
    expect(created).toHaveTextContent("Por segurança, ela não aparece de novo.");

    await user.click(within(created).getByRole("button", { name: "Copiar" }));
    expect(await navigator.clipboard.readText()).toBe(FULL_KEY);
    expect(within(created).getByRole("button", { name: "Copiada" })).toBeInTheDocument();

    await user.click(within(created).getByRole("button", { name: "Já guardei a chave" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(FULL_KEY);
    const site = await itemOf(keysList, "Site institucional");
    expect(within(site).getByText(`${FULL_KEY.slice(0, 12)}…`)).toBeInTheDocument();
    expect(within(site).getByText("Ativa")).toBeInTheDocument();
  });

  it("revoga a chave com confirmação e mantém a revogada na lista", async () => {
    const { api, user } = setup();
    api.on("POST", `/panel/api-keys/${CRM_KEY.id}/revoke`, () =>
      json(200, { ...CRM_KEY, revoked_at: "2026-09-26T12:00:00Z" }),
    );
    const crm = await itemOf(keysList, "CRM de vendas");
    expect(within(crm).getByText("avk_3f9a2c1b…")).toBeInTheDocument();
    expect(within(crm).getByText(/por ana@empresa\.com\.br/)).toBeInTheDocument();

    const old = await itemOf(keysList, "Teste de integração");
    expect(within(old).getByText("Revogada")).toBeInTheDocument();
    expect(within(old).queryByRole("button", { name: /Revogar/ })).not.toBeInTheDocument();

    await user.click(within(crm).getByRole("button", { name: "Revogar CRM de vendas" }));
    const confirmation = within(crm).getByRole("group", { name: "Confirmação" });
    expect(confirmation).toHaveTextContent("Não dá para desfazer.");
    expect(calls(api, "POST", `/panel/api-keys/${CRM_KEY.id}/revoke`)).toHaveLength(0);

    await user.click(within(confirmation).getByRole("button", { name: "Revogar chave" }));

    expect(await within(crm).findByText("Revogada")).toBeInTheDocument();
    expect(within(crm).queryByText("Ativa")).not.toBeInTheDocument();
    expect(within(crm).queryByRole("button", { name: /Revogar/ })).not.toBeInTheDocument();
    expect(calls(api, "POST", `/panel/api-keys/${CRM_KEY.id}/revoke`)).toHaveLength(1);
  });

  it("mostra o exemplo de POST /api/v1/jobs com o prefixo de uma chave ativa", async () => {
    setup();
    await itemOf(keysList, "CRM de vendas");

    const example = screen.getByLabelText("Exemplo de chamada da API");
    expect(example).toHaveTextContent("POST /api/v1/jobs");
    expect(example).toHaveTextContent("Authorization: Bearer avk_3f9a2c1b…");
    expect(example).toHaveTextContent('"aspect_ratio": "9:16"');
  });
});
