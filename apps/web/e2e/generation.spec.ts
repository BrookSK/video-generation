import { expect, test } from "@playwright/test";

const CONTROL = "http://127.0.0.1:8000/__test";

test("@P05 painel persiste pedidos e baixa mídia autenticada nos dois formatos", async ({ page, request }) => {
  const credentials = await (await request.get(`${CONTROL}/config`)).json();
  await page.goto("/entrar");
  await page.getByLabel("E-mail").fill(credentials.username);
  await page.getByLabel("Senha", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "Novo vídeo", exact: true })).toBeVisible();

  for (const [format, avatar] of [["9:16", "Helena"], ["16:9", "Rafael"]]) {
    await page.getByRole("textbox", { name: "Texto da fala" }).fill(`Fala literal ${format}.`);
    await page.getByRole("radio", { name: new RegExp(avatar!) }).check();
    await page.getByRole("radio", { name: /Fundo sálvia/ }).check();
    await page.getByRole("radiogroup", { name: "Formato" }).getByText(format!, { exact: true }).click();
    await expect(page.getByRole("radio", { name: format!, exact: true })).toBeChecked();
    const created = page.waitForResponse((response) => response.url().endsWith("/panel/jobs") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Gerar vídeo" }).click({ clickCount: 2 });
    const job = await (await created).json();
    await expect(page.getByRole("heading", { name: "Na fila", exact: true })).toBeVisible();
    await expect(page.getByText("Gerador sem resposta", { exact: true })).toBeVisible({ timeout: 10000 });
    const downloadPath = `/panel/jobs/${job.id}/download`;
    expect((await page.request.get(downloadPath)).status()).toBe(409);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Na fila", exact: true })).toBeVisible();
    const claim = await request.post(`${CONTROL}/claim`);
    expect(claim.status()).toBe(200);
    expect((await claim.json()).id).toBe(job.id);
    await expect(page.getByRole("heading", { name: "Processando", exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("list", { name: "Etapas da geração" }).getByText("Voz")).toHaveAttribute("aria-current", "step");
    expect((await request.post(`${CONTROL}/jobs/${job.id}/complete`)).status()).toBe(200);
    await expect(page.getByRole("link", { name: "Baixar MP4" })).toBeVisible({ timeout: 10000 });
    await expect(page.getByLabel("Vídeo gerado")).toHaveJSProperty("videoWidth", format === "9:16" ? 1080 : 1920);
    const download = await page.request.get(downloadPath);
    expect(download.status()).toBe(200);
    expect(download.headers()["content-type"]).toBe("video/mp4");
    const partial = await page.request.get(downloadPath, { headers: { Range: "bytes=0-23" } });
    expect(partial.status()).toBe(206);
    expect((await partial.body()).toString()).toContain("ftyp");
    expect((await request.get(`http://localhost:5173${downloadPath}`)).status()).toBe(401);
    const history = await (await page.request.get("/panel/jobs")).json();
    expect(history.filter((entry: { script_text: string }) => entry.script_text === `Fala literal ${format}.`)).toHaveLength(1);
    await page.getByRole("link", { name: "Histórico", exact: true }).last().click();
    await expect(page.getByRole("link", { name: `Fala literal ${format}.` })).toBeVisible();
    expect((await request.post(`${CONTROL}/presence`)).status()).toBe(200);
    await page.getByRole("link", { name: "Novo vídeo", exact: true }).last().click();
    await expect(page.getByRole("textbox", { name: "Texto da fala" })).toBeVisible();
  }

  await page.getByRole("textbox", { name: "Texto da fala" }).fill("Falha controlada.");
  await page.getByRole("radio", { name: /Helena/ }).check();
  await page.getByRole("radio", { name: /Fundo sálvia/ }).check();
  const created = page.waitForResponse((response) => response.url().endsWith("/panel/jobs") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Gerar vídeo" }).click();
  const failedJob = await (await created).json();
  expect((await request.post(`${CONTROL}/claim`)).status()).toBe(200);
  expect((await request.post(`${CONTROL}/jobs/${failedJob.id}/fail`)).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Falha", exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("RENDER_FAILED", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Refazer com os mesmos dados" }).click();
  await expect(page.getByRole("textbox", { name: "Texto da fala" })).toHaveValue("Falha controlada.");
  const history = await (await page.request.get("/panel/jobs")).json();
  expect(history.filter((entry: { script_text: string }) => entry.script_text === "Falha controlada.")).toHaveLength(1);
});
