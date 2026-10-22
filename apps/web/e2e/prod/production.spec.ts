import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

import { API_URL } from "./stack";

// Dublê só nas fronteiras de TTS e render: o teste faz o papel do worker GPU pela API interna.
// Recorte do avatar e montagem da aula rodam no supervisor CPU real da imagem de produção.
const WORKER = { Authorization: `Bearer ${process.env.M002_03_WORKER_TOKEN}` };
const SCENE_SECONDS = 3;
const SCENE_RGB = [[0xdc, 0x28, 0x28], [0x28, 0xc8, 0x3c], [0x28, 0x3c, 0xdc], [0xe0, 0xc0, 0x20]];
const SCENES = [
  { text: "Primeiro isole a área com fita. Depois chame o técnico responsável.", shot: "Plano médio", topics: ["Isolar a área", "Chamar o técnico"] },
  { text: "Esta é a tela de liberação. Confira a assinatura antes de começar.", shot: "Close", topics: [] },
  { text: "Use capacete, luvas e óculos. Botina com biqueira também!", shot: "Plano médio", topics: ["Capacete", "Luvas", "Óculos"] },
  { text: "Ao terminar, recolha a fita. Avise a equipe que a área está livre.", shot: "Close", topics: [] },
];
const AVULSO = "Vídeo avulso da prova de produção.";

const hex = (rgb: number[]) => "0x" + rgb.map((value) => value.toString(16).padStart(2, "0")).join("");

function ffmpeg(args: string[]) {
  execFileSync("ffmpeg", ["-nostdin", "-v", "error", "-y", ...args]);
}

/** Mídia sintética; a voz da cena é um tom de 300 Hz com pausa de 1 a 2 s. */
function sceneVideo(path: string, rgb: number[], size: string, seconds: number) {
  ffmpeg([
    "-f", "lavfi", "-i", `color=c=${hex(rgb)}:s=${size}:r=25`, "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
    "-t", String(seconds), "-af", "volume='if(between(t,1,2),0,1)':eval=frame",
    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", path,
  ]);
  return readFileSync(path);
}

/** PNG com fundo transparente e a cor só onde a condição vale (drawbox não grava alfa). */
const opaque = (color: string, width: number, height: number, where: string) =>
  `color=c=${color}:s=${width}x${height},format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='255*${where}'`;

function picture(path: string, filter: string) {
  ffmpeg(["-f", "lavfi", "-i", filter, "-frames:v", "1", path]);
  return readFileSync(path);
}

function probe(video: string) {
  const data = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json", video]).toString());
  const of = (type: string) => data.streams.find((s: { codec_type: string }) => s.codec_type === type);
  return { video: of("video"), audio: of("audio"), duration: Number(data.format.duration) };
}

/** Perfil de saída do painel: H.264 yuv420p a 25 FPS, AAC e faststart (moov antes de mdat). */
function expectOutputProfile(video: string, size: [number, number], seconds: number, tolerance: number) {
  const { video: stream, audio, duration } = probe(video);
  expect([stream.codec_name, stream.pix_fmt, stream.r_frame_rate]).toEqual(["h264", "yuv420p", "25/1"]);
  expect([stream.width, stream.height]).toEqual(size);
  expect(audio?.codec_name, "faixa de áudio").toBe("aac");
  expect(Math.abs(duration - seconds), `duração ${duration}`).toBeLessThanOrEqual(tolerance);
  const bytes = readFileSync(video);
  expect(bytes.indexOf("moov")).toBeLessThan(bytes.indexOf("mdat"));
}

function pixel(video: string, seconds: number, x: number, y: number): number[] {
  const raw = execFileSync("ffmpeg", [
    "-nostdin", "-v", "error", "-ss", seconds.toFixed(3), "-i", video, "-frames:v", "1",
    "-vf", `crop=8:8:${x}:${y},scale=1:1`, "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
  ]);
  return [...raw.subarray(0, 3)];
}

function expectNear(actual: number[], expected: number[], label: string) {
  for (const [i, value] of actual.entries()) expect(Math.abs(value - expected[i]!), `${label}: ${actual} != ${expected}`).toBeLessThanOrEqual(18);
}

/** Reivindica um job de vídeo, como o worker GPU, e o conclui com a mídia do dublê. */
async function renderNext(request: APIRequestContext, testInfo: TestInfo, media: (payload: { script_text: string; aspect_ratio: string }) => { rgb: number[]; seconds: number }) {
  let claimed: { id: string; attempt_id: string; lease_generation: number; payload: { script_text: string; aspect_ratio: string } } | undefined;
  await expect(async () => {
    const response = await request.post(`${API_URL}/internal/v1/claim`, { headers: WORKER, data: { worker_id: "e2e-gpu-dubla", kinds: ["video"] } });
    expect(response.status()).toBe(200);
    claimed = await response.json();
  }).toPass({ timeout: 30000 });
  const job = claimed!;
  const ref = { attempt_id: job.attempt_id, lease_generation: job.lease_generation };
  expect((await request.post(`${API_URL}/internal/v1/jobs/${job.id}/heartbeat`, { headers: WORKER, data: { ...ref, stage: "tts" } })).ok()).toBe(true);
  const { rgb, seconds } = media(job.payload);
  const size = job.payload.aspect_ratio === "9:16" ? "1080x1920" : "1920x1080";
  const files: [string, Buffer][] = [
    ["manifest.json", Buffer.from(JSON.stringify({ audio_seconds: seconds, test_only: true }))],
    ["final.mp4", sceneVideo(testInfo.outputPath(`job-${job.id}.mp4`), rgb, size, seconds)],
  ];
  let resultId = "";
  for (const [name, buffer] of files) {
    const upload = await request.put(`${API_URL}/internal/v1/jobs/${job.id}/attempts/${job.attempt_id}/files/${name}`, {
      headers: WORKER,
      multipart: { lease_generation: String(job.lease_generation), sha256: createHash("sha256").update(buffer).digest("hex"), file: { name, mimeType: "application/octet-stream", buffer } },
    });
    expect(upload.status(), await upload.text()).toBe(201);
    resultId = (await upload.json()).id;
  }
  const complete = await request.post(`${API_URL}/internal/v1/jobs/${job.id}/complete`, { headers: WORKER, data: { ...ref, result_file_id: resultId } });
  expect(complete.status(), await complete.text()).toBe(200);
}

async function download(page: Page, path: string, file: string) {
  const response = await page.request.get(path);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toBe("video/mp4");
  writeFileSync(file, await response.body());
}

test("@M002-03 aula completa e vídeo avulso no Compose de produção local", async ({ page, request }, testInfo) => {
  await page.goto("/entrar");
  await page.getByLabel("E-mail").fill(process.env.M002_03_USERNAME!);
  await page.getByLabel("Senha", { exact: true }).fill(process.env.M002_03_PASSWORD!);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "Novo vídeo", exact: true })).toBeVisible();

  // Catálogo pela API do painel, atrás do Caddy: avatar com alfa (recorte no supervisor CPU) e cenário de cor.
  const { csrf_token: csrf } = await (await page.request.get("/panel/auth/me")).json();
  const avatarPng = picture(testInfo.outputPath("avatar.png"), opaque("0xF0C8A0", 600, 900, "between(X,150,449)*between(Y,120,899)"));
  const avatar = await page.request.post("/panel/avatars", {
    headers: { "X-CSRF-Token": csrf },
    multipart: { name: "Helena (prova)", voice: "feminina", authorization_confirmed: "true", file: { name: "avatar.png", mimeType: "image/png", buffer: avatarPng } },
  });
  expect(avatar.status(), await avatar.text()).toBe(201);
  const avatarId = (await avatar.json()).id;
  await expect(async () => expect((await (await page.request.get(`/panel/avatars/${avatarId}`)).json()).status).toBe("ativo")).toPass({ timeout: 120000 });
  const scene = await page.request.post("/panel/scenes", {
    headers: { "X-CSRF-Token": csrf },
    multipart: { name: "Fundo sálvia (prova)", background_color: "#CFE0D6", composition: JSON.stringify({ "9:16": { scale: 0.8, x: 0.5, y: 1 }, "16:9": { scale: 0.9, x: 0.5, y: 1 } }) },
  });
  expect(scene.status(), await scene.text()).toBe(201);

  // Identidade e trilha pelo painel.
  await page.getByRole("link", { name: "Identidade" }).click();
  const logo = picture(testInfo.outputPath("logo.png"), opaque("white", 300, 120, "between(X,20,279)*between(Y,20,99)"));
  await page.getByLabel("Logo").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: logo });
  await page.getByRole("textbox", { name: "Cor de fundo", exact: true }).fill("#0B2545");
  await page.getByRole("textbox", { name: "Cor de destaque", exact: true }).fill("#F2A541");
  await page.getByRole("button", { name: "Salvar identidade" }).click();
  await expect(page.getByText("Identidade salva. Ela vale para as aulas criadas a partir de agora.")).toBeVisible();
  ffmpeg(["-f", "lavfi", "-i", "sine=frequency=4000:sample_rate=44100:duration=2", "-ac", "2", testInfo.outputPath("trilha.wav")]);
  await page.getByLabel("Trilha de fundo", { exact: true }).setInputFiles({ name: "trilha.wav", mimeType: "audio/wav", buffer: readFileSync(testInfo.outputPath("trilha.wav")) });
  await expect(page.getByText("Trilha salva. Ela vale para as aulas criadas a partir de agora.")).toBeVisible();

  // Aula 16:9 de quatro cenas: troca de plano, tópicos, uma imagem e trilha.
  await page.getByRole("link", { name: "Nova aula", exact: true }).last().click();
  await page.getByRole("radio", { name: /Helena \(prova\)/ }).check();
  await page.getByRole("radio", { name: /Fundo sálvia \(prova\)/ }).check();
  await page.getByRole("radiogroup", { name: "Formato" }).getByText("16:9", { exact: true }).click();
  await page.getByRole("button", { name: "Adicionar cena" }).click();
  await page.getByRole("button", { name: "Adicionar cena" }).click();
  for (const [index, item] of SCENES.entries()) {
    await page.getByRole("textbox", { name: `Cena ${index + 1}`, exact: true }).fill(item.text);
    await page.getByRole("radiogroup", { name: `Plano da cena ${index + 1}` }).getByText(item.shot, { exact: true }).click();
    await page.getByRole("textbox", { name: `Tópicos da cena ${index + 1}` }).fill(item.topics.join("\n"));
  }
  const image = picture(testInfo.outputPath("tela.png"), "color=c=0xFF00FF:s=800x600");
  await page.getByLabel("Imagem da cena 2").setInputFiles({ name: "tela.png", mimeType: "image/png", buffer: image });
  await expect(page.getByRole("img", { name: "Imagem da cena 2" })).toBeVisible();
  await page.getByRole("checkbox", { name: /Tocar a trilha de fundo/ }).check();
  const created = page.waitForResponse((response) => response.url().endsWith("/panel/lessons") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Gerar aula" }).click();
  const lesson = await (await created).json();
  await expect(page.getByRole("heading", { name: "Gerando cenas", exact: true })).toBeVisible();

  const texts = SCENES.map((item) => item.text);
  for (let i = 0; i < SCENES.length; i++) {
    await renderNext(request, testInfo, ({ script_text }) => ({ rgb: SCENE_RGB[texts.indexOf(script_text)]!, seconds: SCENE_SECONDS }));
  }
  await expect(page.getByRole("link", { name: "Baixar MP4" })).toBeVisible({ timeout: 120000 });
  const lessonVideo = testInfo.outputPath("aula-16x9.mp4");
  await download(page, `/panel/lessons/${lesson.id}/download`, lessonVideo);
  expectOutputProfile(lessonVideo, [1920, 1080], 3 + SCENES.length * SCENE_SECONDS + 3, (SCENES.length + 1) / 25 + 0.05);
  for (const index of [0, 2, 3]) expectNear(pixel(lessonVideo, 3 + index * SCENE_SECONDS + 1.5, 956, 536), SCENE_RGB[index]!, `cena ${index + 1}`);
  expectNear(pixel(lessonVideo, 3 + SCENE_SECONDS + 1.5, 662, 444), [255, 0, 255], "imagem da cena 2");
  expectNear(pixel(lessonVideo, 3 + SCENE_SECONDS + 1.5, 1586, 209), SCENE_RGB[1]!, "apresentador no quadro menor");

  // Vídeo avulso 9:16 pelo mesmo painel.
  await page.getByRole("link", { name: "Novo vídeo", exact: true }).last().click();
  await page.getByRole("textbox", { name: "Texto da fala" }).fill(AVULSO);
  await page.getByRole("radio", { name: /Helena \(prova\)/ }).check();
  await page.getByRole("radio", { name: /Fundo sálvia \(prova\)/ }).check();
  await expect(page.getByRole("radio", { name: "9:16", exact: true })).toBeChecked();
  const job = page.waitForResponse((response) => response.url().endsWith("/panel/jobs") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Gerar vídeo" }).click();
  const avulso = await (await job).json();
  await renderNext(request, testInfo, ({ script_text }) => {
    expect(script_text).toBe(AVULSO);
    return { rgb: [0xcf, 0xe0, 0xd6], seconds: 2 };
  });
  await expect(page.getByRole("link", { name: "Baixar MP4" })).toBeVisible({ timeout: 30000 });
  const avulsoVideo = testInfo.outputPath("avulso-9x16.mp4");
  await download(page, `/panel/jobs/${avulso.id}/download`, avulsoVideo);
  expectOutputProfile(avulsoVideo, [1080, 1920], 2, 0.1);
});
