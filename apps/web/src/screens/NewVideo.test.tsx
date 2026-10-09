import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { restoreSession } from "../api";
import { ANA, installFakeApi, json } from "../test/fakeApi";
import { NewVideo } from "./NewVideo";

const AVATAR = { id: "avatar-active", name: "Helena", status: "ativo", voice: "feminina" };
const SCENE = { id: "scene-active", name: "Estúdio", status: "ativo", background_color: "#CFE0D6", composition: { "9:16": { scale: .8, x: .5, y: 1 }, "16:9": { scale: .9, x: .4, y: 1.1 } } };

async function setup(limit: number | null = 50) {
  const api = installFakeApi({ signedIn: ANA });
  await restoreSession();
  api.on("GET", "/panel/avatars", () => json(200, [AVATAR, { ...AVATAR, id: "preparing", name: "Rafael", status: "preparando" }]));
  api.on("GET", "/panel/scenes", () => json(200, [SCENE]));
  api.on("GET", "/panel/generation-config", () => json(200, { max_script_chars: limit, max_audio_seconds: limit == null ? null : 5, chars_per_second: limit == null ? null : 10 }));
  render(<MemoryRouter><Routes><Route path="/" element={<NewVideo />} /><Route path="/videos/:id" element={<p>Job persistido</p>} /></Routes></MemoryRouter>);
  await screen.findByRole("radio", { name: /Helena/ });
  const user = userEvent.setup();
  await user.click(screen.getByRole("radio", { name: /Helena/ }));
  await user.click(screen.getByRole("radio", { name: /Estúdio/ }));
  return { api, user };
}

describe("Intenção de geração", () => {
  it("preserva texto literal e limita pela receita vigente antes do POST", async () => {
    const { api, user } = await setup(10);
    const field = screen.getByRole("textbox", { name: "Texto da fala" });
    await user.type(field, "Olá.\nTeste!");
    expect(screen.getByRole("button", { name: "Gerar vídeo" })).toBeDisabled();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(api.requests.filter((r) => r.method === "POST")).toEqual([]);
    fireEvent.change(field, { target: { value: "  Olá!\n" } });
    api.on("POST", "/panel/jobs", ({ body }) => {
      expect(body).toMatchObject({ script_text: "  Olá!\n", avatar_id: AVATAR.id, scene_id: SCENE.id });
      return json(202, { id: "job-one", status: "queued", status_url: "/panel/jobs/job-one" });
    });
    await user.click(screen.getByRole("button", { name: "Gerar vídeo" }));
    expect(await screen.findByText("Job persistido")).toBeInTheDocument();
  });

  it("não habilita receita ausente nem avatar em preparação", async () => {
    await setup(null);
    expect(screen.getByRole("radio", { name: /Rafael/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Gerar vídeo" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Olá" } });
    expect(screen.getByText("Estimativa indisponível")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gerar vídeo" })).toBeDisabled();
  });

  it("conserva a intenção após resposta perdida e bloqueia clique duplo", async () => {
    const { api, user } = await setup();
    await user.type(screen.getByRole("textbox"), "Olá!");
    let calls = 0;
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    api.on("POST", "/panel/jobs", async () => {
      calls++;
      if (calls === 1) { await pending; throw new TypeError("resposta perdida"); }
      return json(202, { id: "same-job", status: "queued", status_url: "/panel/jobs/same-job" });
    });
    const form = screen.getByRole("textbox").closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    await waitFor(() => expect(calls).toBe(1));
    release();
    await screen.findByRole("alert");
    const posts = () => api.requests.filter((r) => r.path === "/panel/jobs" && r.method === "POST");
    const key = posts()[0]!.headers["Idempotency-Key"];
    await user.click(screen.getByRole("button", { name: "Gerar vídeo" }));
    await screen.findByText("Job persistido");
    expect(calls).toBe(2);
    expect(posts()[1]!.headers["Idempotency-Key"]).toBe(key);
    expect(posts()[1]!.body).toEqual(posts()[0]!.body);
  });

  it("inicia outra intenção quando o usuário muda o pedido depois do erro", async () => {
    const { api, user } = await setup();
    api.on("POST", "/panel/jobs", () => { throw new TypeError("sem rede"); });
    await user.type(screen.getByRole("textbox"), "Primeira fala");
    await user.click(screen.getByRole("button", { name: "Gerar vídeo" }));
    await screen.findByRole("alert");
    await user.type(screen.getByRole("textbox"), " revisada");
    await user.click(screen.getByRole("button", { name: "Gerar vídeo" }));
    await screen.findByRole("alert");
    const posts = api.requests.filter((r) => r.path === "/panel/jobs" && r.method === "POST");
    expect(posts[1]!.headers["Idempotency-Key"]).not.toBe(posts[0]!.headers["Idempotency-Key"]);
    expect(posts[1]!.body).toMatchObject({ script_text: "Primeira fala revisada" });
  });
});
