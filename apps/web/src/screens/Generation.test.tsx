import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { App } from "../App";
import type { VideoJob } from "../jobs";
import { ANA, apiError, installFakeApi, json } from "../test/fakeApi";

const BASE: VideoJob = {
  id: "video-123", status: "queued", status_url: "/panel/jobs/video-123", download_url: null,
  script_text: "Olá, equipe!", avatar_id: "avatar-active", scene_id: "scene-active", aspect_ratio: "9:16",
  avatar_name: "Helena", scene_name: "Estúdio", voice: "feminina", origin: "panel", requested_by: "Ana",
  stage: null, created_at: "2026-10-09T12:00:00Z", started_at: null, finished_at: null,
  file_exists: false, size_bytes: null, duration_seconds: null, error: null,
};
function setup(path = "/videos/video-123", initial: VideoJob = BASE) {
  const api = installFakeApi({ signedIn: ANA });
  let job = initial;
  api.on("GET", "/panel/jobs/video-123", () => json(200, job));
  api.on("GET", "/panel/jobs", () => json(200, [job]));
  api.on("GET", "/panel/worker-status", () => json(200, { last_heartbeat_at: new Date().toISOString() }));
  const view = render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  return { api, user: userEvent.setup(), view, update: (next: VideoJob) => { job = next; } };
}

const READY: VideoJob = { ...BASE, status: "ready", file_exists: true, download_url: "/panel/jobs/video-123/download", duration_seconds: 3.4, size_bytes: 1048576, finished_at: "2026-10-09T12:01:00Z" };

describe("Histórico e resultado", () => {
  it("observa fila, etapa e mídia apenas após conclusão persistida", async () => {
    const { update } = setup();
    await screen.findByRole("heading", { name: "Na fila" });
    expect(screen.getByRole("button", { name: "Download indisponível" })).toBeDisabled();
    update({ ...BASE, status: "processing", stage: "tts", started_at: new Date().toISOString() });
    await screen.findByRole("heading", { name: "Processando" }, { timeout: 5000 });
    const steps = screen.getByRole("list", { name: "Etapas da geração" });
    expect(within(steps).getByText("Voz")).toHaveAttribute("aria-current", "step");
    update(READY);
    expect(await screen.findByRole("link", { name: "Baixar MP4" }, { timeout: 5000 })).toHaveAttribute("href", READY.download_url);
    expect(screen.getByLabelText("Vídeo gerado")).toHaveAttribute("src", READY.download_url);
    expect(screen.getByText("3,4 s")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Etapas da geração" })).not.toBeInTheDocument();
  }, 12000);

  it("recarga consulta o servidor e não ressuscita sucesso sem arquivo", async () => {
    const { view, update } = setup("/videos/video-123", READY);
    await screen.findByRole("link", { name: "Baixar MP4" });
    update({ ...READY, file_exists: false, download_url: null, size_bytes: null, duration_seconds: null });
    view.unmount();
    render(<MemoryRouter initialEntries={["/videos/video-123"]}><App /></MemoryRouter>);
    await screen.findByRole("heading", { name: "Arquivo indisponível" });
    expect(screen.queryByRole("link", { name: "Baixar MP4" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Vídeo gerado")).not.toBeInTheDocument();
  });

  it("rede indisponível não se transforma em GPU offline nem apaga último estado", async () => {
    const { api } = setup("/historico");
    await screen.findByRole("link", { name: BASE.script_text });
    api.on("GET", "/panel/jobs", () => { throw new TypeError("rede"); });
    api.on("GET", "/panel/worker-status", () => { throw new TypeError("rede"); });
    await screen.findByText(/O estado da GPU é desconhecido/, {}, { timeout: 5000 });
    expect(screen.queryByText("Gerador sem resposta")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: BASE.script_text })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("último estado recebido");
  }, 8000);

  it.each([null, new Date(Date.now() - 121000).toISOString()])("ausência observada %s avisa sem bloquear a fila salva", async (heartbeat) => {
    const { api } = setup("/historico");
    api.on("GET", "/panel/worker-status", () => json(200, { last_heartbeat_at: heartbeat }));
    await screen.findByText("Gerador sem resposta", {}, { timeout: 5000 });
    expect(screen.getByRole("link", { name: BASE.script_text })).toBeInTheDocument();
    expect(screen.getByText("Posição 1")).toBeInTheDocument();
  }, 8000);

  it("falha mantém código e refazer copia dados, exigindo escolha de asset arquivado", async () => {
    const { api, user } = setup("/videos/video-123", { ...BASE, status: "failed", error: { code: "GPU_OOM", message: "Memória da GPU insuficiente." } });
    api.on("GET", "/panel/avatars", () => json(200, [{ id: "new-avatar", name: "Rafael", voice: "masculina", status: "ativo" }]));
    api.on("GET", "/panel/scenes", () => json(200, [{ id: BASE.scene_id, name: "Estúdio", status: "ativo", background_color: "#fff", composition: { "9:16": { scale: .8, x: .5, y: 1 }, "16:9": { scale: .9, x: .5, y: 1 } } }]));
    api.on("GET", "/panel/generation-config", () => json(200, { max_script_chars: 600, max_audio_seconds: 40, chars_per_second: 15 }));
    await screen.findByText("GPU_OOM");
    await user.click(screen.getByRole("link", { name: "Refazer com os mesmos dados" }));
    const field = await screen.findByRole("textbox", { name: "Texto da fala" });
    expect(field).toHaveValue(BASE.script_text);
    await screen.findByRole("radio", { name: /Rafael/ });
    expect(screen.getByRole("button", { name: "Gerar vídeo" })).toBeDisabled();
    expect(api.requests.filter((request) => request.method === "POST" && request.path === "/panel/jobs")).toEqual([]);
    await user.click(screen.getByRole("radio", { name: /Rafael/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Gerar vídeo" })).toBeEnabled());
  });

  it("job inexistente não apresenta player ou controle de reenvio", async () => {
    const { api } = setup();
    api.on("GET", "/panel/jobs/video-123", () => apiError(404, "NOT_FOUND", "Job não encontrado."));
    await screen.findByRole("alert");
    expect(screen.queryByLabelText("Vídeo gerado")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Refazer com os mesmos dados" })).not.toBeInTheDocument();
  });
});
