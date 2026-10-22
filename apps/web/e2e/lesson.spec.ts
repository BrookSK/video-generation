import { execFileSync, spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const CONTROL = "http://127.0.0.1:8000/__test";
const BACKGROUND = [0x0b, 0x25, 0x45];
// Cores do dublê de render em e2e_server.py, por posição da cena.
const SCENE_RGB = [[0xdc, 0x28, 0x28], [0x28, 0xc8, 0x3c], [0x28, 0x3c, 0xdc]];
const SCENE_SECONDS = 3;
const TEXTS = ["Abertura do tema da aula.", "Agora de perto, o detalhe.", "Fechamento com o resumo."];
const SHOTS = ["Plano médio", "Close", "Plano médio"];

/** Cor média de um bloco 8x8 no quadro do instante indicado, lida com FFmpeg. */
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

/** Nível RMS em dB da faixa da trilha sintética (4 kHz) no trecho; a voz do dublê é 300 Hz. */
function bandLevel(video: string, start: number, seconds: number): number {
  const result = spawnSync("ffmpeg", [
    "-nostdin", "-hide_banner", "-ss", start.toFixed(3), "-t", seconds.toFixed(3), "-i", video,
    "-af", "highpass=f=2500,highpass=f=2500,highpass=f=2500,astats=measure_perchannel=none", "-f", "null", "-",
  ], { encoding: "utf8" });
  const value = /RMS level dB: (\S+)/.exec(result.stderr)?.[1];
  expect(value, result.stderr).toBeDefined();
  return value === "-inf" ? -Infinity : Number(value);
}

async function signIn(page: Page, request: APIRequestContext) {
  const credentials = await (await request.get(`${CONTROL}/config`)).json();
  await page.goto("/entrar");
  await page.getByLabel("E-mail").fill(credentials.username);
  await page.getByLabel("Senha", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "Novo vídeo", exact: true })).toBeVisible();
}

/** Faz o papel do gerador: reivindica as cenas na fila e conclui cada uma com o dublê. */
async function renderScenes(request: APIRequestContext, count: number): Promise<Record<string, string>> {
  // Jobs da mesma aula têm o mesmo created_at: a ordem de claim entre eles não é fixa.
  const shotByText: Record<string, string> = {};
  for (let i = 0; i < count; i++) {
    const claim = await request.post(`${CONTROL}/claim`);
    expect(claim.status()).toBe(200);
    const job = await claim.json();
    shotByText[job.payload.script_text] = job.payload.shot;
    expect((await request.post(`${CONTROL}/jobs/${job.id}/complete`)).status()).toBe(200);
  }
  return shotByText;
}

async function expectNoHorizontalScroll(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, `rolagem horizontal em ${path}`).toBeLessThanOrEqual(0);
}

test("@M002-01 aula 16:9 com identidade, três cenas e montagem real no supervisor CPU", async ({ page, request }, testInfo) => {
  test.setTimeout(180000);
  await signIn(page, request);

  // Sem identidade, a aula não sai.
  await page.getByRole("link", { name: "Nova aula", exact: true }).last().click();
  await expect(page.getByRole("button", { name: "Gerar aula" })).toBeDisabled();
  await page.getByRole("link", { name: "Abrir Identidade" }).click();

  const logo = Buffer.from(await (await request.get(`${CONTROL}/logo.png`)).body());
  await page.getByLabel("Logo").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: logo });
  await page.getByRole("textbox", { name: "Cor de fundo", exact: true }).fill("#0B2545");
  await page.getByRole("textbox", { name: "Cor de destaque", exact: true }).fill("#F2A541");
  await page.getByRole("button", { name: "Salvar identidade" }).click();
  await expect(page.getByText("Identidade salva. Ela vale para as aulas criadas a partir de agora.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Cor de fundo", exact: true })).toHaveValue("#0B2545");
  await expect(page.getByRole("img", { name: "Logo" })).toHaveJSProperty("naturalWidth", 300);

  await page.getByRole("link", { name: "Nova aula", exact: true }).last().click();
  await page.getByRole("radio", { name: /Helena/ }).check();
  await page.getByRole("radio", { name: /Fundo sálvia/ }).check();
  await page.getByRole("radiogroup", { name: "Formato" }).getByText("16:9", { exact: true }).click();
  await page.getByRole("button", { name: "Adicionar cena" }).click();
  for (const [index, text] of TEXTS.entries()) {
    await page.getByRole("textbox", { name: `Cena ${index + 1}`, exact: true }).fill(text);
    await page.getByRole("radiogroup", { name: `Plano da cena ${index + 1}` }).getByText(SHOTS[index]!, { exact: true }).click();
  }
  const created = page.waitForResponse((response) => response.url().endsWith("/panel/lessons") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Gerar aula" }).click({ clickCount: 2 });
  const lesson = await (await created).json();
  await expect(page.getByRole("heading", { name: "Gerando cenas", exact: true })).toBeVisible();
  const lessons = await (await page.request.get("/panel/lessons")).json();
  expect(lessons).toHaveLength(1);
  expect((await page.request.get(`/panel/lessons/${lesson.id}/download`)).status()).toBe(409);
  // As cenas da aula não entram no histórico de vídeos avulsos.
  const avulsos: { script_text: string }[] = await (await page.request.get("/panel/jobs")).json();
  expect(avulsos.filter((job) => TEXTS.includes(job.script_text))).toEqual([]);

  const shotByText = await renderScenes(request, TEXTS.length);
  expect(TEXTS.map((text) => shotByText[text])).toEqual(["medio", "close", "medio"]);

  // Montagem no supervisor CPU real: assembling e depois ready, com player e download.
  await expect(page.getByRole("link", { name: "Baixar MP4" })).toBeVisible({ timeout: 90000 });
  await expect(page.getByRole("heading", { level: 1, name: "Aula" })).toBeVisible();
  await expect(page.getByLabel("Aula gerada")).toHaveJSProperty("videoWidth", 1920);
  for (const index of [1, 2, 3]) {
    await expect(page.getByRole("listitem", { name: `Cena ${index}` }).getByText("Pronto", { exact: true })).toBeVisible();
  }

  const download = await page.request.get(`/panel/lessons/${lesson.id}/download`);
  expect(download.status()).toBe(200);
  expect(download.headers()["content-type"]).toBe("video/mp4");
  const video = testInfo.outputPath("aula.mp4");
  writeFileSync(video, await download.body());
  const probe = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json", video]).toString());
  const stream = probe.streams.find((s: { codec_type: string }) => s.codec_type === "video");
  expect([stream.width, stream.height]).toEqual([1920, 1080]);
  const expected = 3 + TEXTS.length * SCENE_SECONDS + 3;
  expect(Math.abs(Number(probe.format.duration) - expected)).toBeLessThanOrEqual((TEXTS.length + 1) / 25 + 0.05);

  expectNear(pixel(video, 1.5, 40, 40), BACKGROUND, "abertura");
  expectNear(pixel(video, 1.5, 956, 536), [255, 255, 255], "logo na abertura");
  for (const [index, rgb] of SCENE_RGB.entries()) {
    expectNear(pixel(video, 3 + index * SCENE_SECONDS + 1.5, 956, 536), rgb, `cena ${index + 1}`);
  }
  expectNear(pixel(video, expected - 1.5, 40, 40), BACKGROUND, "encerramento");

  // Telas de aula sem rolagem horizontal em 375 px.
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ["/identidade", "/aulas/nova", "/aulas", `/aulas/${lesson.id}`]) {
    await expectNoHorizontalScroll(page, path);
  }
});

// Cena 1 com tópicos e cena 2 com imagem; as duas com duas frases, uma por trecho de fala do dublê.
const MEDIA_SCENES = [
  { text: "Primeiro isole a área com fita. Depois chame o técnico responsável.", topics: ["  Isolar a área", "Chamar o técnico (NR-10)"] },
  { text: "Use capacete, luvas e óculos. Confira a liberação assinada!", topics: [] },
];
const MAGENTA = [255, 0, 255];
// Centro da área da imagem e do quadro do apresentador por formato (lesson_text.LAYOUTS).
const FRAME = {
  "16:9": { size: [1920, 1080], image: [662, 444], pip: [1586, 209] },
  "9:16": { size: [1080, 1920], image: [540, 518], pip: [870, 1256] },
} as const;

test("@M002-02 aulas 9:16 e 16:9 com legenda literal, tópicos, imagem e trilha com ducking", async ({ page, request }, testInfo) => {
  test.setTimeout(300000);
  await signIn(page, request);

  await page.getByRole("link", { name: "Identidade" }).click();
  const logo = Buffer.from(await (await request.get(`${CONTROL}/logo.png`)).body());
  await page.getByLabel("Logo").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: logo });
  await page.getByRole("textbox", { name: "Cor de fundo", exact: true }).fill("#0B2545");
  await page.getByRole("textbox", { name: "Cor de destaque", exact: true }).fill("#F2A541");
  await page.getByRole("button", { name: "Salvar identidade" }).click();
  await expect(page.getByText("Identidade salva. Ela vale para as aulas criadas a partir de agora.")).toBeVisible();
  const music = Buffer.from(await (await request.get(`${CONTROL}/music.wav`)).body());
  await page.getByLabel("Trilha de fundo", { exact: true }).setInputFiles({ name: "trilha.wav", mimeType: "audio/wav", buffer: music });
  await expect(page.getByText("Trilha salva. Ela vale para as aulas criadas a partir de agora.")).toBeVisible();
  await expect(page.getByLabel("Trilha de fundo atual")).toHaveAttribute("src", /\/panel\/brand-identity\/music\?v=/);
  const picture = Buffer.from(await (await request.get(`${CONTROL}/picture.png`)).body());

  for (const ratio of ["9:16", "16:9"] as const) {
    await page.getByRole("link", { name: "Nova aula", exact: true }).last().click();
    await page.getByRole("radio", { name: /Helena/ }).check();
    await page.getByRole("radio", { name: /Fundo sálvia/ }).check();
    await page.getByRole("radiogroup", { name: "Formato" }).getByText(ratio, { exact: true }).click();
    for (const [index, scene] of MEDIA_SCENES.entries()) {
      await page.getByRole("textbox", { name: `Cena ${index + 1}`, exact: true }).fill(scene.text);
      await page.getByRole("textbox", { name: `Tópicos da cena ${index + 1}` }).fill(scene.topics.join("\n"));
    }
    await page.getByLabel("Imagem da cena 2").setInputFiles({ name: "tela.png", mimeType: "image/png", buffer: picture });
    await expect(page.getByRole("img", { name: "Imagem da cena 2" })).toBeVisible();
    await page.getByRole("checkbox", { name: /Tocar a trilha de fundo/ }).check();
    const created = page.waitForResponse((response) => response.url().endsWith("/panel/lessons") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Gerar aula" }).click();
    const lesson = await (await created).json();
    await expect(page.getByRole("heading", { name: "Gerando cenas", exact: true })).toBeVisible();

    await renderScenes(request, MEDIA_SCENES.length);
    await expect(page.getByRole("link", { name: "Baixar MP4" })).toBeVisible({ timeout: 90000 });
    const download = await page.request.get(`/panel/lessons/${lesson.id}/download`);
    expect(download.status()).toBe(200);
    const video = testInfo.outputPath(`aula-${ratio.replace(":", "x")}.mp4`);
    writeFileSync(video, await download.body());
    const probe = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-show_streams", "-of", "json", video]).toString());
    const stream = probe.streams.find((s: { codec_type: string }) => s.codec_type === "video");
    expect([stream.width, stream.height]).toEqual([...FRAME[ratio].size]);

    // Legenda reconstruída dos trechos, tópicos e trilha, pelo manifesto da montagem.
    const manifest = await (await request.get(`${CONTROL}/lessons/${lesson.id}/manifest`)).json();
    expect(manifest.music_sha256).toMatch(/^[0-9a-f]{64}$/);
    for (const [index, scene] of MEDIA_SCENES.entries()) {
      const planned = manifest.scenes[index];
      expect(planned.subtitles.map((chunk: { text: string }) => chunk.text).join("")).toBe(scene.text);
      expect(planned.subtitle_timing).toBe("silence");
      expect(planned.topics).toEqual(scene.topics);
      expect(planned.image_sha256 !== null).toBe(index === 1);
    }

    // Cena 2 (de 6 a 9 s): imagem na área principal e apresentador no quadro menor.
    const [ix, iy] = FRAME[ratio].image;
    const [px, py] = FRAME[ratio].pip;
    expectNear(pixel(video, 7.5, ix, iy), MAGENTA, `imagem ${ratio}`);
    expectNear(pixel(video, 7.5, px, py), SCENE_RGB[1]!, `quadro do apresentador ${ratio}`);

    // Cena 1 (de 3 a 6 s): fala de 3 a 4 s, pausa de 4 a 5 s, fala de 5 a 6 s.
    const pause = bandLevel(video, 4.45, 0.5);
    const speech = [bandLevel(video, 3.3, 0.6), bandLevel(video, 5.3, 0.6)];
    expect(pause).toBeGreaterThan(-40);
    for (const level of speech) expect(level, `trilha na fala ${speech} x pausa ${pause}`).toBeLessThan(pause - 6);
  }

  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ["/identidade", "/aulas/nova"]) await expectNoHorizontalScroll(page, path);
});
