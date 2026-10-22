import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeAll, describe, expect, it } from "vitest";

import { App } from "../App";
import type { BrandIdentity } from "../lessons";
import { ANA, apiError, installFakeApi, json, type FakeApi } from "../test/fakeApi";

const PATH = "/panel/brand-identity";
const EMPTY: BrandIdentity = { logo_url: null, background_color: null, accent_color: null, updated_at: null, updated_by: null };
const SAVED: BrandIdentity = {
  logo_url: "/panel/brand-identity/logo?v=1",
  background_color: "#0B2545",
  accent_color: "#F2A541",
  updated_at: "2026-10-20T12:00:00Z",
  updated_by: "Ana Souza",
};

beforeAll(() => {
  URL.createObjectURL = () => "blob:logo";
  URL.revokeObjectURL = () => undefined;
});

async function setup(initial: BrandIdentity = EMPTY) {
  const api = installFakeApi({ signedIn: ANA });
  api.on("GET", PATH, () => json(200, initial));
  render(
    <MemoryRouter initialEntries={["/identidade"]}>
      <App />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: "Salvar identidade" });
  return { api, user: userEvent.setup({ applyAccept: false }) };
}

const puts = (api: FakeApi) => api.requests.filter((r) => r.method === "PUT" && r.path === PATH);
const logo = (name = "logo.png", type = "image/png") => new File(["x"], name, { type });

describe("Tela Identidade", () => {
  it("fica no grupo Aulas do menu e, sem cadastro, avisa e exige o logo", async () => {
    const { api, user } = await setup();

    const nav = screen.getByRole("navigation");
    expect(nav).toHaveTextContent("Aulas");
    expect(screen.getByRole("link", { name: "Identidade" })).toHaveAttribute("href", "/identidade");
    expect(screen.getByRole("link", { name: "Nova aula" })).toHaveAttribute("href", "/aulas/nova");
    expect(screen.getByText(/Nenhuma identidade cadastrada/)).toBeInTheDocument();
    expect(screen.getByText("Seu logo aqui")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Salvar identidade" }));

    expect(screen.getByLabelText("Logo")).toHaveAccessibleDescription(/Envie o logo em PNG ou JPEG\./);
    expect(screen.getByLabelText("Logo")).toHaveFocus();
    expect(puts(api)).toHaveLength(0);
  });

  it("envia logo e cores em multipart, trava o botão e mostra a identidade salva", async () => {
    const { api, user } = await setup();
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    api.on("PUT", PATH, async () => {
      await pending;
      return json(200, SAVED);
    });

    await user.upload(screen.getByLabelText("Logo"), logo());
    expect(screen.getByRole("img", { name: "Logo" })).toHaveAttribute("src", "blob:logo");
    const background = screen.getByRole("textbox", { name: "Cor de fundo" });
    await user.clear(background);
    await user.type(background, "#0b2545");
    fireEvent.change(screen.getByLabelText("Cor de destaque: seletor"), { target: { value: "#f2a541" } });
    expect(screen.getByRole("textbox", { name: "Cor de destaque" })).toHaveValue("#F2A541");

    await user.click(screen.getByRole("button", { name: "Salvar identidade" }));
    expect(screen.getByRole("button", { name: "Salvando…" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("button", { name: "Salvando…" }).closest("form")!);
    release();

    expect(await screen.findByText("Identidade salva. Ela vale para as aulas criadas a partir de agora.")).toBeInTheDocument();
    expect(puts(api)).toHaveLength(1);
    const body = puts(api)[0]!.body as FormData;
    expect(body.get("background_color")).toBe("#0B2545");
    expect(body.get("accent_color")).toBe("#F2A541");
    expect((body.get("logo") as File).name).toBe("logo.png");
    expect(screen.getByRole("img", { name: "Logo" })).toHaveAttribute("src", SAVED.logo_url);
    expect(screen.getByText(/Última mudança: Ana Souza/)).toBeInTheDocument();
    expect(screen.queryByText(/Nenhuma identidade cadastrada/)).not.toBeInTheDocument();
  });

  it("recusa SVG no navegador e mostra no campo do logo a recusa do servidor", async () => {
    const { api, user } = await setup(SAVED);
    api.on("PUT", PATH, () => apiError(422, "UNSUPPORTED_FILE_TYPE", "Envie o logo em PNG ou JPEG.", "logo"));
    expect(screen.getByRole("textbox", { name: "Cor de fundo" })).toHaveValue("#0B2545");

    await user.upload(screen.getByLabelText("Logo"), logo("logo.svg", "image/svg+xml"));
    expect(screen.getByLabelText("Logo")).toHaveAccessibleDescription(/Envie o logo em PNG ou JPEG\./);
    expect(screen.getByRole("img", { name: "Logo" })).toHaveAttribute("src", SAVED.logo_url);

    await user.upload(screen.getByLabelText("Logo"), logo("disfarcado.png"));
    await user.click(screen.getByRole("button", { name: "Salvar identidade" }));

    await waitFor(() => expect(screen.getByLabelText("Logo")).toHaveAccessibleDescription(/Envie o logo em PNG ou JPEG\./));
    expect(screen.getByLabelText("Logo")).toHaveFocus();
    expect(screen.getByRole("img", { name: "Logo" })).toHaveAttribute("src", SAVED.logo_url);
    expect(puts(api)).toHaveLength(1);
  });

  it("liga o erro 422 de cor ao campo certo e não envia cor fora do formato", async () => {
    const { api, user } = await setup(SAVED);
    api.on("PUT", PATH, () => apiError(422, "VALIDATION_ERROR", "Use uma cor no formato #RRGGBB.", "accent_color"));
    const background = screen.getByRole("textbox", { name: "Cor de fundo" });

    await user.clear(background);
    await user.type(background, "azul");
    await user.click(screen.getByRole("button", { name: "Salvar identidade" }));
    expect(background).toHaveAccessibleDescription("Use uma cor no formato #RRGGBB.");
    expect(background).toHaveFocus();
    expect(puts(api)).toHaveLength(0);

    await user.clear(background);
    await user.type(background, "#112233");
    await user.click(screen.getByRole("button", { name: "Salvar identidade" }));

    const accent = screen.getByRole("textbox", { name: "Cor de destaque" });
    await waitFor(() => expect(accent).toHaveAccessibleDescription("Use uma cor no formato #RRGGBB."));
    expect(background).not.toHaveAccessibleDescription();
    expect(puts(api)).toHaveLength(1);
    expect((puts(api)[0]!.body as FormData).get("logo")).toBeNull();
  });
});
