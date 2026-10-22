import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

const CONTROL = "http://127.0.0.1:8000/__test";
const BACKGROUND = [0x0b, 0x25, 0x45];
// Cores do dublê de render em e2e_server.py, por posição da cena.
const SCENE_RGB = [[0xdc, 0x28, 0x28], [0x28, 0xc8, 0x3c], [0x28, 0x3c, 0xdc]];
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

async function expectNoHorizontalScroll(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, `rolagem horizontal em ${path}`).toBeLessThanOrEqual(0);
}

test("@M002-01 aula 16:9 com identidade, três cenas e montagem real no supervisor CPU", async ({ page, request }, testInfo) => {
  test.setTimeout(180000);
  const credentials = await (await request.get(`${CONTROL}/config`)).json();
  await page.goto("/entrar");
  await page.getByLabel("E-mail").fill(credentials.username);
  await page.getByLabel("Senha", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "Novo vídeo", exact: true })).toBeVisible();

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
    await page.getByRole("textbox", { name: `Cena ${index + 1}` }).fill(text);
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

  // Jobs da mesma aula têm o mesmo created_at: a ordem de claim entre eles não é fixa.
  const shotByText: Record<string, string> = {};
  for (let i = 0; i < TEXTS.length; i++) {
    const claim = await request.post(`${CONTROL}/claim`);
    expect(claim.status()).toBe(200);
    const job = await claim.json();
    shotByText[job.payload.script_text] = job.payload.shot;
    expect((await request.post(`${CONTROL}/jobs/${job.id}/complete`)).status()).toBe(200);
  }
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
  const expected = 3 + TEXTS.length * 2 + 3;
  expect(Math.abs(Number(probe.format.duration) - expected)).toBeLessThanOrEqual((TEXTS.length + 1) / 25 + 0.05);

  expectNear(pixel(video, 1.5, 40, 40), BACKGROUND, "abertura");
  expectNear(pixel(video, 1.5, 956, 536), [255, 255, 255], "logo na abertura");
  for (const [index, rgb] of SCENE_RGB.entries()) {
    expectNear(pixel(video, 3 + index * 2 + 1, 956, 536), rgb, `cena ${index + 1}`);
  }
  expectNear(pixel(video, expected - 1.5, 40, 40), BACKGROUND, "encerramento");

  // Telas de aula sem rolagem horizontal em 375 px.
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ["/identidade", "/aulas/nova", "/aulas", `/aulas/${lesson.id}`]) {
    await expectNoHorizontalScroll(page, path);
  }
});
