import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeAll, describe, expect, it } from "vitest";

import { App } from "../App";
import { ANA, apiError, installFakeApi, json, type FakeApi } from "../test/fakeApi";
import type { Avatar } from "./AvatarDialog";
import type { Scene } from "./Scenes";

const COMPOSITION = { "9:16": { scale: 0.8, x: 0.5, y: 1 }, "16:9": { scale: 0.9, x: 0.5, y: 1 } };
const base = { composition: COMPOSITION, created_at: "2026-09-20T12:00:00Z", archived_at: null };
const ESCRITORIO: Scene = { ...base, id: "5c5c5c5c-0000-4000-8000-000000000001", name: "Escritório claro", background_color: null, status: "ativo" };
const SALVIA: Scene = { ...base, id: "5c5c5c5c-0000-4000-8000-000000000002", name: "Parede sálvia", background_color: "#CFE0D6", status: "ativo" };
const LOJA: Scene = {
  ...base,
  id: "5c5c5c5c-0000-4000-8000-000000000003",
  name: "Loja antiga",
  background_color: null,
  status: "arquivado",
  archived_at: "2026-09-22T12:00:00Z",
};
const HELENA: Avatar = {
  id: "a1a1a1a1-0000-4000-8000-000000000001",
  name: "Helena",
  voice: "feminina",
  status: "ativo",
  prepare_error: null,
  authorized_at: "2026-09-20T12:00:00Z",
  created_at: "2026-09-20T12:00:00Z",
  archived_at: null,
};
const RAFAEL: Avatar = { ...HELENA, id: "a1a1a1a1-0000-4000-8000-000000000002", name: "Rafael", status: "preparando" };

const LIST = "/panel/scenes";
const LIST_ARCHIVED = "/panel/scenes?include_archived=true";
const MB = 1024 * 1024;

beforeAll(() => {
  URL.createObjectURL = () => "blob:fundo";
  URL.revokeObjectURL = () => undefined;
});

function setup({ scenes = [ESCRITORIO], avatars = [HELENA], path = "/cenarios" }: { scenes?: Scene[]; avatars?: Avatar[]; path?: string } = {}) {
  const api = installFakeApi({ signedIn: ANA });
  api.on("GET", LIST, () => json(200, scenes.filter((s) => s.status !== "arquivado")));
  api.on("GET", LIST_ARCHIVED, () => json(200, scenes));
  api.on("GET", "/panel/avatars", () => json(200, avatars));
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
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

async function openEditor(options: Parameters<typeof setup>[0] = {}) {
  const ctx = setup({ path: "/cenarios/novo", ...options });
  await screen.findByRole("heading", { level: 1, name: "Criar cenário" });
  return ctx;
}

const stage = () => screen.getByRole("region", { name: "Prévia do cenário" });
const slider = (name: string) => screen.getByRole("slider", { name });
const setSlider = (name: string, value: string) => fireEvent.change(slider(name), { target: { value } });
const output = (name: string) => slider(name).closest(".slider")!.querySelector("output")!;

describe("Tela de cenários", () => {
  it("lista cada cenário com as prévias 9:16 e 16:9, chip e tipo de fundo", async () => {
    setup({ scenes: [ESCRITORIO, SALVIA, LOJA] });

    const escritorio = await card("Escritório claro");
    expect(within(escritorio).getByText("Ativo")).toBeInTheDocument();
    expect(within(escritorio).getByText("Imagem")).toBeInTheDocument();
    expect(within(escritorio).getByRole("img", { name: "Prévia 9:16" })).toHaveAttribute(
      "src",
      `/panel/scenes/${ESCRITORIO.id}/files/preview-9x16`,
    );
    expect(within(escritorio).getByRole("img", { name: "Prévia 16:9" })).toHaveAttribute(
      "src",
      `/panel/scenes/${ESCRITORIO.id}/files/preview-16x9`,
    );
    expect(within(await card("Parede sálvia")).getByText("Cor sólida #CFE0D6")).toBeInTheDocument();
    expect(screen.getByText("2 ativos. Não há limite de cadastro.")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Loja antiga" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Criar cenário" })).toHaveAttribute("href", "/cenarios/novo");
  });

  it("filtro Mostrar arquivados pede include_archived e mostra o arquivado sem ações", async () => {
    const { api, user } = setup({ scenes: [ESCRITORIO, LOJA] });
    await card("Escritório claro");

    await user.click(screen.getByRole("checkbox", { name: "Mostrar arquivados" }));

    const loja = await card("Loja antiga");
    expect(within(loja).getByText("Arquivado")).toBeInTheDocument();
    expect(within(loja).queryByRole("button")).not.toBeInTheDocument();
    expect(within(await card("Escritório claro")).getByText("Ativo")).toBeInTheDocument();
    expect(calls(api, "GET", LIST_ARCHIVED)).toHaveLength(1);
  });

  it("arquiva só depois da confirmação embutida com a consequência", async () => {
    const { api, user } = setup({ scenes: [ESCRITORIO] });
    const archive = `/panel/scenes/${ESCRITORIO.id}/archive`;
    api.on("POST", archive, () => json(200, { ...ESCRITORIO, status: "arquivado", archived_at: "2026-09-26T12:00:00Z" }));
    const escritorio = await card("Escritório claro");

    await user.click(within(escritorio).getByRole("button", { name: "Arquivar Escritório claro" }));
    const confirm = within(escritorio).getByRole("group", { name: "Confirmação" });
    expect(confirm).toHaveTextContent("Vídeos já gerados continuam disponíveis. O cenário sai da lista de novos vídeos e da API.");
    await user.click(within(confirm).getByRole("button", { name: "Cancelar" }));
    expect(calls(api, "POST", archive)).toHaveLength(0);

    await user.click(within(escritorio).getByRole("button", { name: "Arquivar Escritório claro" }));
    await user.click(within(escritorio).getByRole("button", { name: "Arquivar" }));

    expect(await screen.findByText("Cenário Escritório claro arquivado.")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Escritório claro" })).not.toBeInTheDocument();
    expect(calls(api, "POST", archive)).toHaveLength(1);
  });
});

describe("Editor de cenário", () => {
  it("compõe o avatar de amostra com a geometria de compose_canvas e troca o visor de formato", async () => {
    const { user } = await openEditor({ avatars: [RAFAEL, HELENA] });

    const avatar = await within(stage()).findByRole("img", { name: "Avatar de amostra: Helena" });
    expect(avatar).toHaveAttribute("src", `/panel/avatars/${HELENA.id}/files/prepared`);
    expect(avatar).toHaveStyle({ height: "80%", left: "50%", bottom: "0%" });
    const frame = stage().querySelector(".frame")!;
    expect(frame).toHaveAttribute("data-format", "9:16");

    setSlider("Escala", "0.6");
    setSlider("Posição horizontal", "0.3");
    setSlider("Base", "1.1");
    expect(avatar).toHaveStyle({ height: "60%", left: "30%", bottom: "-10%" });
    expect(output("Escala")).toHaveTextContent("0,60");
    expect(output("Base")).toHaveTextContent("1,10");

    await user.click(screen.getByRole("radio", { name: "16:9" }));
    expect(frame).toHaveAttribute("data-format", "16:9");
    expect(frame).toHaveClass("h");
    expect(within(stage()).getByText("16:9")).toBeInTheDocument();
    expect(avatar).toHaveStyle({ height: "90%", left: "50%", bottom: "0%" });
  });

  it("usa a silhueta quando não há avatar ativo", async () => {
    await openEditor({ avatars: [RAFAEL] });
    await screen.findByText("Silhueta de amostra");
    expect(stage().querySelector(".comp-silhouette")).toHaveStyle({ height: "80%" });
    expect(within(stage()).queryByRole("img")).not.toBeInTheDocument();
  });

  it("ajusta 16:9 sem alterar 9:16 e salva cor sólida com os dois enquadramentos", async () => {
    const { api, user } = await openEditor();
    api.on("POST", LIST, () => json(201, { ...SALVIA, id: "5c5c5c5c-0000-4000-8000-000000000009", name: "Balcão" }));

    await user.type(screen.getByLabelText("Nome do cenário"), "  Balcão ");
    await user.click(screen.getByRole("radio", { name: "Cor sólida" }));
    fireEvent.change(screen.getByLabelText("Outra cor"), { target: { value: "#123abc" } });
    expect(stage().querySelector(".comp-bg")).toHaveStyle({ background: "#123ABC" });

    setSlider("Escala", "0.7");
    await user.click(screen.getByRole("radio", { name: "16:9" }));
    expect(slider("Escala")).toHaveValue("0.9");
    setSlider("Escala", "1.05");
    setSlider("Posição horizontal", "0.65");
    setSlider("Base", "1.15");
    await user.click(screen.getByRole("radio", { name: "9:16" }));
    expect(slider("Escala")).toHaveValue("0.7");
    expect(slider("Posição horizontal")).toHaveValue("0.5");
    expect(slider("Base")).toHaveValue("1");

    await user.click(screen.getByRole("button", { name: "Salvar cenário" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Cenários" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Cenário Balcão criado. Ele já aparece em Novo vídeo e na API.");
    const [sent] = calls(api, "POST", LIST);
    const body = sent!.body as FormData;
    expect(body.get("name")).toBe("Balcão");
    expect(body.get("background_color")).toBe("#123ABC");
    expect(body.get("file")).toBeNull();
    const composition = JSON.parse(body.get("composition") as string);
    expect(Object.keys(composition).sort()).toEqual(["16:9", "9:16"]);
    expect(composition).toEqual({
      "9:16": { scale: 0.7, x: 0.5, y: 1 },
      "16:9": { scale: 1.05, x: 0.65, y: 1.15 },
    });
    for (const framing of Object.values(composition) as Record<string, unknown>[]) {
      expect(Object.keys(framing).sort()).toEqual(["scale", "x", "y"]);
      expect(Object.values(framing).every((value) => typeof value === "number")).toBe(true);
    }
  });

  it("recusa SVG e imagem acima de 20 MB e salva a imagem de fundo aceita", async () => {
    const { api, user } = await openEditor();
    api.on("POST", LIST, () => json(201, { ...ESCRITORIO, id: "5c5c5c5c-0000-4000-8000-000000000010", name: "Vitrine" }));

    await user.type(screen.getByLabelText("Nome do cenário"), "Vitrine");
    await user.click(screen.getByRole("button", { name: "Salvar cenário" }));
    expect(screen.getByLabelText("Imagem de fundo")).toHaveAccessibleDescription(
      /Escolha a imagem de fundo ou mude para cor sólida\./,
    );
    expect(screen.getByLabelText("Imagem de fundo")).toHaveFocus();

    await user.upload(screen.getByLabelText("Imagem de fundo"), image("logo.png.svg", "image/svg+xml"));
    expect(screen.getByLabelText("Imagem de fundo")).toHaveAccessibleDescription(
      /Formato não aceito\. Envie JPEG, PNG ou WebP\. SVG, PDF e arquivos compactados são recusados\./,
    );
    await user.upload(screen.getByLabelText("Imagem de fundo"), image("vitrine.jpg", "image/jpeg", 21 * MB));
    expect(screen.getByLabelText("Imagem de fundo")).toHaveAccessibleDescription(/A imagem tem 21 MB e o limite é 20 MB\./);
    expect(calls(api, "POST", LIST)).toHaveLength(0);

    await user.upload(screen.getByLabelText("Imagem de fundo"), image("vitrine.png", "image/png"));
    expect(screen.getByRole("img", { name: "Prévia do fundo enviado" })).toHaveAttribute("src", "blob:fundo");
    expect(stage().querySelector(".comp-bg img")).toHaveAttribute("src", "blob:fundo");
    await user.click(screen.getByRole("button", { name: "Salvar cenário" }));

    await screen.findByRole("heading", { level: 1, name: "Cenários" });
    const body = calls(api, "POST", LIST)[0]!.body as FormData;
    expect((body.get("file") as File).name).toBe("vitrine.png");
    expect(body.get("background_color")).toBeNull();
    expect(Object.keys(JSON.parse(body.get("composition") as string)).sort()).toEqual(["16:9", "9:16"]);
  });

  it("bloqueia o envio sem nome e liga o erro de enquadramento do servidor ao campo", async () => {
    const { api, user } = await openEditor();
    api.on("POST", LIST, () =>
      apiError(422, "VALIDATION_ERROR", "Enquadramento 16:9: escala 1,3 fora da faixa de 0,3 a 1,2.", "composition"),
    );
    await user.click(screen.getByRole("radio", { name: "Cor sólida" }));

    await user.click(screen.getByRole("button", { name: "Salvar cenário" }));
    expect(screen.getByLabelText("Nome do cenário")).toHaveAccessibleDescription("Dê um nome ao cenário.");
    expect(screen.getByLabelText("Nome do cenário")).toHaveFocus();
    expect(calls(api, "POST", LIST)).toHaveLength(0);

    await user.type(screen.getByLabelText("Nome do cenário"), "Balcão");
    await user.click(screen.getByRole("button", { name: "Salvar cenário" }));

    const framing = await screen.findByRole("region", { name: "Enquadramento" });
    expect(framing).toHaveAccessibleDescription("Enquadramento 16:9: escala 1,3 fora da faixa de 0,3 a 1,2.");
    expect(within(framing).getByText("Enquadramento 16:9: escala 1,3 fora da faixa de 0,3 a 1,2.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Criar cenário" })).toBeInTheDocument();
    expect(calls(api, "POST", LIST)).toHaveLength(1);
  });
});
