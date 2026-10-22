import { defineConfig } from "@playwright/test";

// Jornada @M002-03 no Compose de produção local; exige Docker. Comando:
//   npm --prefix apps/web run e2e:prod
export default defineConfig({
  testDir: "./e2e/prod",
  timeout: 300000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  globalSetup: "./e2e/prod/stack.ts",
  use: { baseURL: "http://127.0.0.1:18088", viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure" },
});
