import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { ANA, apiError, installFakeApi, json, type FakeApi } from "../test/fakeApi";
import type { Avatar } from "./AvatarDialog";

const base = {
  prepare_error: null,
  authorized_at: "2026-09-20T12:00:00Z",
  created_at: "2026-09-20T12:00:00Z",
  archived_at: null,
};
const HELENA: Avatar = { ...base, id: "a1a1a1a1-0000-4000-8000-000000000001", name: "Helena", voice: "feminina", status: "ativo" };
const RAFAEL: Avatar = { ...base, id: "a1a1a1a1-0000-4000-8000-000000000002", name: "Rafael", voice: "masculina", status: "preparando" };
const JOANA: Avatar = {
  ...base,
  id: "a1a1a1a1-0000-4000-8000-000000000003",
  name: "Joana",
  voice: "feminina",
  status: "falha",
  prepare_error: "Não encontramos uma pessoa nesta imagem. Envie uma foto de frente, com rosto e ombros visíveis.",
};
const PEDRO: Avatar = {
  ...base,
  id: "a1a1a1a1-0000-4000-8000-000000000004",
  name: "Pedro",
  voice: "masculina",
  status: "arquivado",
  archived_at: "2026-09-22T12:00:00Z",
};

const LIST = "/panel/avatars";
const LIST_ARCHIVED = "/panel/avatars?include_archived=true";
const MB = 1024 * 1024;

// O jsdom não implementa <dialog> modal nem URL de objeto; o teste imita o navegador.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  URL.createObjectURL = () => "blob:previa";
  URL.revokeObjectURL = () => undefined;
});

afterEach(() => {
  vi.useRealTimers();
});

function setup(avatars: Avatar[] = [HELENA]) {
  const api = installFakeApi({ signedIn: ANA });
  api.on("GET", LIST, () => json(200, avatars.filter((a) => a.status !== "arquivado")));
  api.on("GET", LIST_ARCHIVED, () => json(200, avatars));
  render(
    <MemoryRouter initialEntries={["/avatares"]}>
      <App />
    </MemoryRouter>,
  );
  // applyAccept desligado: o teste escolhe SVG e ZIP como a pessoa faria por "Todos os arquivos".
  return { api, user: userEvent.setup({ applyAccept: false }) };
}

const calls = (api: FakeApi, method: string, path: string) =>
  api.requests.filter((r) => r.method === method && r.path === path);

const card = (name: string) => screen.findByRole("article", { name });

function image(name: string, type: string, size = 1024): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("heading", { level: 1, name: "Avatares" });
  await user.click(screen.getByRole("button", { name: "Cadastrar avatar" }));
  return screen.getByRole("dialog", { name: "Cadastrar avatar" });
}

describe("Tela de avatares", () => {
  it("mostra os quatro estados com texto no chip, prévia 9:16 e ações de cada estado", async () => {
    const { user } = setup([HELENA, RAFAEL, JOANA, PEDRO]);

    const helena = await card("Helena");
    expect(within(helena).getByText("Ativo")).toBeInTheDocument();
    expect(within(helena).getByText("Voz feminina")).toBeInTheDocument();
    expect(helena.querySelector("img")).toHaveAttribute("src", `/panel/avatars/${HELENA.id}/files/preview-9x16`);
    expect(within(helena).getByRole("button", { name: "Arquivar Helena" })).toBeEnabled();

    const rafael = await card("Rafael");
    expect(within(rafael).getByText("Preparando")).toBeInTheDocument();
    expect(within(rafael).getByText("Recortando o fundo")).toBeInTheDocument();
    expect(within(rafael).getByRole("button", { name: "Arquivar Rafael" })).toBeDisabled();

    const joana = await card("Joana");
    expect(within(joana).getByText("Falha")).toBeInTheDocument();
    expect(within(joana).getByText(JOANA.prepare_error!)).toBeInTheDocument();
    expect(within(joana).queryByRole("button", { name: /Arquivar/ })).not.toBeInTheDocument();
    await user.click(within(joana).getByRole("button", { name: "Enviar outra imagem" }));
    expect(screen.getByRole("dialog", { name: "Cadastrar avatar" })).toBeInTheDocument();

    expect(screen.queryByRole("article", { name: "Pedro" })).not.toBeInTheDocument();
  });

  it("filtro Mostrar arquivados pede include_archived e mostra o chip Arquivado sem ações", async () => {
    const { api, user } = setup([HELENA, PEDRO]);
    await card("Helena");

    await user.click(screen.getByRole("checkbox", { name: "Mostrar arquivados" }));

    const pedro = await card("Pedro");
    expect(within(pedro).getByText("Arquivado")).toBeInTheDocument();
    expect(within(pedro).queryByRole("button")).not.toBeInTheDocument();
    expect(calls(api, "GET", LIST_ARCHIVED)).toHaveLength(1);
  });

  it("arquiva só depois da confirmação embutida com a consequência", async () => {
    const { api, user } = setup([HELENA]);
    api.on("POST", `/panel/avatars/${HELENA.id}/archive`, () =>
      json(200, { ...HELENA, status: "arquivado", archived_at: "2026-09-26T12:00:00Z" }),
    );
    const helena = await card("Helena");

    await user.click(within(helena).getByRole("button", { name: "Arquivar Helena" }));
    const confirm = within(helena).getByRole("group", { name: "Confirmação" });
    expect(confirm).toHaveTextContent("Vídeos já gerados continuam disponíveis. O avatar sai da lista de novos vídeos e da API.");
    await user.click(within(confirm).getByRole("button", { name: "Cancelar" }));
    expect(calls(api, "POST", `/panel/avatars/${HELENA.id}/archive`)).toHaveLength(0);

    await user.click(within(helena).getByRole("button", { name: "Arquivar Helena" }));
    await user.click(within(helena).getByRole("button", { name: "Arquivar" }));

    expect(await screen.findByText("Avatar Helena arquivado.")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Helena" })).not.toBeInTheDocument();
    expect(calls(api, "POST", `/panel/avatars/${HELENA.id}/archive`)).toHaveLength(1);
  });

  it("atualiza a cada 3 s só enquanto houver avatar em preparação", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = installFakeApi({ signedIn: ANA });
    let current: Avatar = RAFAEL;
    api.on("GET", LIST, () => json(200, [current]));
    render(
      <MemoryRouter initialEntries={["/avatares"]}>
        <App />
      </MemoryRouter>,
    );
    await card("Rafael");
    expect(calls(api, "GET", LIST)).toHaveLength(1);

    current = { ...RAFAEL, status: "ativo" };
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(within(await card("Rafael")).getByText("Ativo")).toBeInTheDocument();
    expect(calls(api, "GET", LIST)).toHaveLength(2);

    await act(() => vi.advanceTimersByTimeAsync(9000));
    expect(calls(api, "GET", LIST)).toHaveLength(2);
  });
});

describe("Diálogo Cadastrar avatar", () => {
  it("recusa SVG e arquivo de 21 MB com o motivo junto ao campo, sem chamar a API", async () => {
    const { api, user } = setup();
    const dialog = await openDialog(user);
    const input = within(dialog).getByLabelText("Imagem");

    await user.upload(input, image("logo.png.svg", "image/svg+xml"));
    expect(within(dialog).getByLabelText("Imagem")).toHaveAttribute("aria-invalid", "true");
    expect(within(dialog).getByLabelText("Imagem")).toHaveAccessibleDescription(
      /Formato não aceito\. Envie JPEG, PNG ou WebP\. SVG, PDF e arquivos compactados são recusados\./,
    );

    await user.upload(within(dialog).getByLabelText("Imagem"), image("foto-grande.jpg", "image/jpeg", 21 * MB));
    expect(within(dialog).getByLabelText("Imagem")).toHaveAccessibleDescription(
      /A imagem tem 21 MB e o limite é 20 MB\. Envie um arquivo menor\./,
    );

    await user.type(within(dialog).getByLabelText("Nome do avatar"), "Marina");
    await user.click(within(dialog).getByRole("radio", { name: "Feminina" }));
    await user.click(within(dialog).getByRole("checkbox", { name: /Confirmo que temos autorização/ }));
    await user.click(within(dialog).getByRole("button", { name: "Cadastrar avatar" }));

    expect(within(dialog).getByLabelText("Imagem")).toHaveAccessibleDescription(/Envie a foto do avatar\./);
    expect(calls(api, "POST", "/panel/avatars")).toHaveLength(0);
  });

  it("aceita imagem por arrastar e mostra a prévia", async () => {
    const { user } = setup();
    const dialog = await openDialog(user);
    const drop = within(dialog).getByText("Arraste a foto ou clique para escolher").closest("label")!;

    fireEvent.drop(drop, { dataTransfer: { files: [image("marina.webp", "image/webp")] } });

    expect(within(dialog).getByRole("img", { name: "Prévia da imagem enviada" })).toHaveAttribute("src", "blob:previa");
    expect(within(dialog).getByText("marina.webp")).toBeInTheDocument();
    expect(within(dialog).getByText("Imagem aceita. O recorte acontece depois de salvar.")).toBeInTheDocument();
  });

  it("bloqueia o envio sem voz ou sem autorização, com a voz sem valor inicial", async () => {
    const { api, user } = setup();
    const dialog = await openDialog(user);
    const voices = within(dialog).getByRole("radiogroup", { name: "Voz" });
    expect(within(voices).getByRole("radio", { name: "Feminina" })).not.toBeChecked();
    expect(within(voices).getByRole("radio", { name: "Masculina" })).not.toBeChecked();

    await user.upload(within(dialog).getByLabelText("Imagem"), image("marina.png", "image/png"));
    await user.type(within(dialog).getByLabelText("Nome do avatar"), "Marina");
    await user.click(within(dialog).getByRole("button", { name: "Cadastrar avatar" }));

    expect(voices).toHaveAccessibleDescription("Escolha a voz do avatar.");
    expect(within(voices).getByRole("radio", { name: "Feminina" })).toHaveFocus();
    const authorization = within(dialog).getByRole("checkbox", { name: /Confirmo que temos autorização/ });
    expect(authorization).toHaveAccessibleDescription("Confirme a autorização de uso da imagem para continuar.");
    expect(calls(api, "POST", "/panel/avatars")).toHaveLength(0);

    await user.click(within(voices).getByRole("radio", { name: "Masculina" }));
    await user.click(within(dialog).getByRole("button", { name: "Cadastrar avatar" }));
    expect(authorization).toHaveFocus();
    expect(calls(api, "POST", "/panel/avatars")).toHaveLength(0);
  });

  it("envia multipart com a voz escolhida e mostra o novo avatar em preparação", async () => {
    const { api, user } = setup();
    api.on("POST", "/panel/avatars", () =>
      json(201, { ...base, id: "a1a1a1a1-0000-4000-8000-000000000009", name: "Marina", voice: "masculina", status: "preparando" }),
    );
    const dialog = await openDialog(user);

    await user.upload(within(dialog).getByLabelText("Imagem"), image("marina.png", "image/png"));
    await user.type(within(dialog).getByLabelText("Nome do avatar"), "  Marina ");
    await user.click(within(dialog).getByRole("radio", { name: "Masculina" }));
    await user.click(within(dialog).getByRole("checkbox", { name: /Confirmo que temos autorização/ }));
    await user.click(within(dialog).getByRole("button", { name: "Cadastrar avatar" }));

    const marina = await card("Marina");
    expect(within(marina).getByText("Preparando")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Avatar Marina enviado. O recorte do fundo leva alguns segundos.");

    const [sent] = calls(api, "POST", "/panel/avatars");
    const body = sent!.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("name")).toBe("Marina");
    expect(body.get("voice")).toBe("masculina");
    expect(body.get("authorization_confirmed")).toBe("true");
    expect((body.get("file") as File).name).toBe("marina.png");
    expect(sent!.headers["Content-Type"]).toBeUndefined();
  });

  it("liga o 422 do servidor ao campo indicado por field", async () => {
    const { api, user } = setup();
    api.on("POST", "/panel/avatars", () =>
      apiError(422, "IMAGE_TOO_LARGE", "A imagem passa do limite de 40 megapixels.", "file"),
    );
    const dialog = await openDialog(user);

    await user.upload(within(dialog).getByLabelText("Imagem"), image("panorama.jpg", "image/jpeg"));
    await user.type(within(dialog).getByLabelText("Nome do avatar"), "Marina");
    await user.click(within(dialog).getByRole("radio", { name: "Feminina" }));
    await user.click(within(dialog).getByRole("checkbox", { name: /Confirmo que temos autorização/ }));
    await user.click(within(dialog).getByRole("button", { name: "Cadastrar avatar" }));

    expect(await within(dialog).findByText("A imagem passa do limite de 40 megapixels.")).toBeInTheDocument();
    const input = within(dialog).getByLabelText("Imagem");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/A imagem passa do limite de 40 megapixels\./);
    expect(input).toHaveFocus();
    expect(calls(api, "POST", "/panel/avatars")).toHaveLength(1);
  });
});
