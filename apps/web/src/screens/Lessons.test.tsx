import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { App } from "../App";
import type { BrandIdentity, Lesson, LessonScene } from "../lessons";
import { ANA, apiError, installFakeApi, json, type FakeApi } from "../test/fakeApi";

const AVATAR = { id: "avatar-active", name: "Helena", status: "ativo", voice: "feminina" };
const SCENE = { id: "scene-active", name: "Estúdio", status: "ativo", background_color: "#CFE0D6", composition: { "9:16": { scale: 0.8, x: 0.5, y: 1 }, "16:9": { scale: 0.9, x: 0.5, y: 1 } } };
const IDENTITY: BrandIdentity = { logo_url: "/panel/brand-identity/logo?v=1", background_color: "#0B2545", accent_color: "#F2A541", updated_at: "2026-10-20T12:00:00Z", updated_by: "Ana Souza" };
const NO_IDENTITY: BrandIdentity = { logo_url: null, background_color: null, accent_color: null, updated_at: null, updated_by: null };

const ID = "lesson-1";
const scene = (position: number, change: Partial<LessonScene> = {}): LessonScene => ({
  position, script_text: `Fala ${position}`, shot: position === 2 ? "close" : "medio", job_id: `job-${position}`, status: "queued", stage: null, error: null, ...change,
});
const QUEUED: Lesson = {
  id: ID, status: "queued", status_url: `/panel/lessons/${ID}`, download_url: null,
  avatar_id: AVATAR.id, scene_id: SCENE.id, avatar_name: "Helena", scene_name: "Estúdio", aspect_ratio: "16:9",
  background_color: "#0B2545", accent_color: "#F2A541", requested_by: "Ana Souza", created_at: "2026-10-21T12:00:00Z",
  finished_at: null, error: null, size_bytes: null, scenes: [scene(1, { status: "ready" }), scene(2, { status: "processing", stage: "render" }), scene(3)],
};
const READY: Lesson = {
  ...QUEUED, status: "ready", download_url: `/panel/lessons/${ID}/download`, finished_at: "2026-10-21T12:05:00Z", size_bytes: 3 * 1024 * 1024,
  scenes: [1, 2, 3].map((position) => scene(position, { status: "ready" })),
};

function setup(path: string, { identity = IDENTITY, lesson = QUEUED }: { identity?: BrandIdentity; lesson?: Lesson } = {}) {
  const api = installFakeApi({ signedIn: ANA });
  let current = lesson;
  api.on("GET", "/panel/avatars", () => json(200, [AVATAR]));
  api.on("GET", "/panel/scenes", () => json(200, [SCENE]));
  api.on("GET", "/panel/generation-config", () => json(200, { max_script_chars: 20, max_audio_seconds: 30, chars_per_second: 10 }));
  api.on("GET", "/panel/brand-identity", () => json(200, identity));
  api.on("GET", `/panel/lessons/${ID}`, () => json(200, current));
  api.on("GET", "/panel/lessons", () => json(200, [current]));
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
  return { api, user: userEvent.setup(), update: (next: Lesson) => { current = next; } };
}

const posts = (api: FakeApi) => api.requests.filter((r) => r.method === "POST" && r.path === "/panel/lessons");
const sceneText = (position: number) => screen.getByRole("textbox", { name: `Cena ${position}` });

async function openNewLesson(options: Parameters<typeof setup>[1] = {}) {
  const ctx = setup("/aulas/nova", options);
  await ctx.user.click(await screen.findByRole("radio", { name: /Helena/ }));
  await ctx.user.click(screen.getByRole("radio", { name: /Estúdio/ }));
  return ctx;
}

describe("Nova aula", () => {
  it("sem identidade, bloqueia Gerar e aponta para a tela Identidade", async () => {
    const { api, user } = await openNewLesson({ identity: NO_IDENTITY });
    await user.type(sceneText(1), "Primeira");
    await user.type(sceneText(2), "Segunda");

    expect(screen.getByRole("button", { name: "Gerar aula" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Cadastre o logo e as cores antes de gerar uma aula.");
    expect(screen.getByRole("link", { name: "Abrir Identidade" })).toHaveAttribute("href", "/identidade");
    fireEvent.submit(sceneText(1).closest("form")!);
    expect(posts(api)).toHaveLength(0);
  });

  it("envia cenas na ordem da tela com o plano de cada uma e a Idempotency-Key", async () => {
    const { api, user } = await openNewLesson();
    api.on("POST", "/panel/lessons", () => json(202, { id: ID, status: "queued", status_url: `/panel/lessons/${ID}`, download_url: null }));
    expect(screen.getByRole("button", { name: "Remover cena 1" })).toBeDisabled();

    await user.click(screen.getByRole("radio", { name: "16:9" }));
    await user.click(screen.getByRole("button", { name: "Adicionar cena" }));
    await user.click(screen.getByRole("button", { name: "Adicionar cena" }));
    await user.type(sceneText(1), "Abertura do tema");
    await user.type(sceneText(2), "Vai sair");
    await user.type(sceneText(3), "  Detalhe!\n");
    await user.type(sceneText(4), "Fechamento");
    expect(screen.getByText("16 / 20 caracteres")).toBeInTheDocument();
    await user.click(within(screen.getByRole("radiogroup", { name: "Plano da cena 3" })).getByRole("radio", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Remover cena 2" }));
    await user.click(screen.getByRole("button", { name: "Subir cena 3" }));
    expect(sceneText(2)).toHaveValue("Fechamento");
    expect(within(screen.getByRole("radiogroup", { name: "Plano da cena 3" })).getByRole("radio", { name: "Close" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Descer cena 2" }));

    await user.click(screen.getByRole("button", { name: "Gerar aula" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Aula" })).toBeInTheDocument();
    expect(posts(api)).toHaveLength(1);
    expect(posts(api)[0]!.headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(posts(api)[0]!.body).toEqual({
      avatar_id: AVATAR.id,
      scene_id: SCENE.id,
      aspect_ratio: "16:9",
      scenes: [
        { script_text: "Abertura do tema", shot: "medio" },
        { script_text: "  Detalhe!\n", shot: "close" },
        { script_text: "Fechamento", shot: "medio" },
      ],
    });
  });

  it("clique duplo cria uma aula só e o retry depois de resposta perdida reusa a chave", async () => {
    const { api, user } = await openNewLesson();
    await user.type(sceneText(1), "Uma");
    await user.type(sceneText(2), "Duas");
    let calls = 0;
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    api.on("POST", "/panel/lessons", async () => {
      calls++;
      if (calls === 1) {
        await pending;
        throw new TypeError("resposta perdida");
      }
      return json(202, { id: ID, status: "queued", status_url: `/panel/lessons/${ID}`, download_url: null });
    });
    const form = sceneText(1).closest("form")!;

    fireEvent.submit(form);
    fireEvent.submit(form);
    await waitFor(() => expect(calls).toBe(1));
    expect(screen.getByRole("button", { name: "Enviando…" })).toBeDisabled();
    release();
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Gerar aula" }));

    await screen.findByRole("heading", { level: 1, name: "Aula" });
    expect(calls).toBe(2);
    expect(posts(api)[1]!.headers["Idempotency-Key"]).toBe(posts(api)[0]!.headers["Idempotency-Key"]);
  });

  it("recusa cena vazia ou longa antes do envio e mostra no campo da cena o erro do servidor", async () => {
    const { api, user } = await openNewLesson();
    api.on("POST", "/panel/lessons", () => apiError(422, "SCRIPT_EMPTY", "Cena 2: o texto está vazio.", "scenes.1.script_text"));
    await user.type(sceneText(1), "Uma");

    await user.click(screen.getByRole("button", { name: "Gerar aula" }));
    expect(sceneText(2)).toHaveAccessibleDescription(/Cena 2: escreva o texto da fala\./);
    expect(sceneText(2)).toHaveFocus();
    await user.type(sceneText(2), "x".repeat(21));
    expect(sceneText(2)).toHaveAccessibleDescription(/Cena 2: o limite vigente é 20 caracteres\./);
    expect(screen.getByRole("button", { name: "Gerar aula" })).toBeDisabled();
    expect(posts(api)).toHaveLength(0);

    fireEvent.change(sceneText(2), { target: { value: "Duas" } });
    await user.click(screen.getByRole("button", { name: "Gerar aula" }));

    await waitFor(() => expect(sceneText(2)).toHaveAccessibleDescription(/Cena 2: o texto está vazio\./));
    expect(posts(api)).toHaveLength(1);
  });
});

describe("Aulas e aula", () => {
  it("lista as aulas com estado, cenas prontas e link para a aula", async () => {
    setup("/aulas");
    const link = await screen.findByRole("link", { name: "Fala 1" });
    expect(link).toHaveAttribute("href", `/aulas/${ID}`);
    expect(screen.getByText("3 cenas")).toBeInTheDocument();
    expect(screen.getByText("Gerando cenas")).toBeInTheDocument();
    expect(screen.getByText("1 de 3 cenas prontas")).toBeInTheDocument();
  });

  it("acompanha cenas, montagem e pronta com player e Baixar MP4", async () => {
    const { update } = setup(`/aulas/${ID}`);
    await screen.findByRole("heading", { level: 2, name: "Gerando cenas" });
    expect(within(screen.getByRole("listitem", { name: "Cena 1" })).getByText("Pronto")).toBeInTheDocument();
    const second = screen.getByRole("listitem", { name: "Cena 2" });
    expect(second).toHaveTextContent("Cena 2 · Close");
    expect(within(second).getByText("Processando")).toBeInTheDocument();
    expect(within(second).getByText("Animar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download indisponível" })).toBeDisabled();

    update({ ...READY, status: "assembling", download_url: null, finished_at: null, size_bytes: null });
    await screen.findByRole("heading", { level: 2, name: "Montando" }, { timeout: 5000 });
    expect(screen.queryByLabelText("Aula gerada")).not.toBeInTheDocument();

    update(READY);
    expect(await screen.findByRole("link", { name: "Baixar MP4" }, { timeout: 5000 })).toHaveAttribute("href", READY.download_url);
    expect(screen.getByLabelText("Aula gerada")).toHaveAttribute("src", READY.download_url);
    expect(screen.getByText("3 MB · MP4")).toBeInTheDocument();
  }, 12000);

  it("falha mostra o motivo da aula e da cena que falhou, sem player nem download", async () => {
    const failed: Lesson = {
      ...QUEUED,
      status: "failed",
      error: { code: "SCENE_FAILED", message: "A cena 2 falhou: A GPU não tem memória para esta geração." },
      scenes: [scene(1, { status: "ready" }), scene(2, { status: "failed", error: { code: "OUT_OF_MEMORY", message: "A GPU não tem memória para esta geração." } }), scene(3)],
    };
    setup(`/aulas/${ID}`, { lesson: failed });

    await screen.findByRole("heading", { level: 2, name: "Falha" });
    expect(screen.getByText("A cena 2 falhou: A GPU não tem memória para esta geração.")).toBeInTheDocument();
    expect(screen.getByText("SCENE_FAILED")).toBeInTheDocument();
    const second = screen.getByRole("listitem", { name: "Cena 2" });
    expect(second).toHaveTextContent("A GPU não tem memória para esta geração.");
    expect(within(second).getByText("OUT_OF_MEMORY")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Baixar MP4" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Aula gerada")).not.toBeInTheDocument();
  });
});
