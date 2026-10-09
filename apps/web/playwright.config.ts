import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "../../.bianchini/.runtime/playwright",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: { baseURL: "http://localhost:5173", viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure" },
  webServer: [
    { command: "uv run --directory ../api python tests/e2e_server.py", url: "http://127.0.0.1:8000/readyz", timeout: 120000, reuseExistingServer: false },
    { command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort", url: "http://localhost:5173", timeout: 30000, reuseExistingServer: false },
  ],
});
