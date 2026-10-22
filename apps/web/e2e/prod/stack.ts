// Sobe o Compose de produção local (docker-compose.yml + docker-compose.cpu.yml) para a jornada
// @M002-03: API, PostgreSQL, painel no Caddy e supervisor CPU, construídos pelos Dockerfiles de
// produção. Segredos aleatórios num .env temporário; tudo sai com o projeto e os volumes no fim.
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

export const PANEL_URL = "http://127.0.0.1:18088";
export const API_URL = "http://127.0.0.1:18000";

const ROOT = resolve(import.meta.dirname, "../../../..");
const PROJECT = "avatar-m002-03";
const FILES = [join(ROOT, "infra/compose/docker-compose.yml"), join(ROOT, "infra/compose/docker-compose.cpu.yml"), join(import.meta.dirname, "docker-compose.e2e.yml")];
const USERNAME = "e2e@local.test";
// Receita só de teste: a inferência é dublê; a calibração real continua pendente na GPU.
const RECIPE = { status: "frozen", name: "e2e-m002-03-dubla", test_only: true, limits: { max_script_chars: 600, max_audio_seconds: 40, chars_per_second: 15 } };

export default function globalSetup() {
  const dir = mkdtempSync(join(tmpdir(), "avatar-m002-03-"));
  const envFile = join(dir, ".env");
  const secret = () => randomBytes(24).toString("hex");
  const password = secret();
  const token = secret();
  const env = [`POSTGRES_PASSWORD=${secret()}`, `WORKER_TOKEN=${token}`, "APP_ENV=production", "PANEL_PORT=18088", "E2E_API_PORT=18000", `MODELS_DIR=${join(ROOT, "models")}`];
  writeFileSync(envFile, env.join("\n") + "\n", { mode: 0o600 });
  const compose = (args: string[], input?: string) => {
    const command = ["compose", "-p", PROJECT, "--env-file", envFile, ...FILES.flatMap((file) => ["-f", file]), ...args];
    execFileSync("docker", command, { input, stdio: [input === undefined ? "ignore" : "pipe", "inherit", "inherit"] });
  };
  const teardown = () => {
    compose(["down", "--volumes", "--remove-orphans"]);
    rmSync(dir, { recursive: true, force: true });
  };
  try {
    compose(["up", "--detach", "--build", "--wait", "--wait-timeout", "300"]);
    compose(["exec", "-T", "api", "avatar-api", "users", "create", "--username", USERNAME, "--password-stdin"], `${password}\n`);
    compose(["exec", "-T", "api", "avatar-api", "recipes", "load"], JSON.stringify(RECIPE));
  } catch (error) {
    teardown();
    throw error;
  }
  process.env.M002_03_USERNAME = USERNAME;
  process.env.M002_03_PASSWORD = password;
  process.env.M002_03_WORKER_TOKEN = token;
  return teardown;
}
