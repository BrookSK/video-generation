#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE="$ROOT/infra/compose/.env"
ROLE=all
while [ "$#" -gt 0 ]; do
  case "$1" in
    --env-file) ENV_FILE="${2:?Falta caminho de ambiente}"; shift 2 ;;
    --role) ROLE="${2:?Falta papel api ou worker}"; shift 2 ;;
    *) echo "Uso: bash infra/scripts/check-release.sh [--env-file arquivo] [--role api|worker|all]" >&2; exit 2 ;;
  esac
done
python3 - "$ROOT" "$ENV_FILE" "$ROLE" <<'PY'
import json
import os
from pathlib import Path
import re
import subprocess
import sys

root, env_path, role = Path(sys.argv[1]), Path(sys.argv[2]).resolve(), sys.argv[3]

def fail(message):
    print(f"Release bloqueado: {message}", file=sys.stderr)
    raise SystemExit(1)

if role not in {"all", "api", "worker"}:
    fail("papel precisa ser api, worker ou all")
compose_dir = root / "infra/compose"
example = compose_dir / ".env.example"
variables = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", example.read_text(), re.MULTILINE))
referenced = set()
for path in compose_dir.glob("docker-compose*.yml"):
    referenced.update(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", path.read_text()))
missing = sorted(referenced - variables)
if missing:
    fail("variáveis ausentes no .env.example: " + ", ".join(missing))
for name in ["docs/operacao/INSTALACAO.md", "docs/operacao/USO.md", "docs/operacao/OPERACAO.md", "docs/api/GUIA.md", "docs/api/openapi.json", "docs/homologacao/MATRIZ.md", "docs/homologacao/PROCEDIMENTO.md", "docs/homologacao/FORA_DO_ESCOPO.md"]:
    path = root / name
    if not path.is_file() or not path.stat().st_size:
        fail("documento obrigatório ausente ou vazio: " + name)
if not env_path.is_file():
    fail("ambiente privado não encontrado; copie .env.example e preencha valores reais")
if env_path.stat().st_mode & 0o077:
    fail("ambiente precisa de permissões 600 ou mais restritas")
# O arquivo informado é a fonte; variáveis herdadas do terminal não podem sobrescrevê-lo.
environment = {key: value for key, value in os.environ.items() if key not in referenced}
digest = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
roles = ["api", "worker"] if role == "all" else [role]
for selected in roles:
    names = ["docker-compose.yml", "docker-compose.cpu.yml", "docker-compose.api.yml", "docker-compose.release.yml"] if selected == "api" else ["docker-compose.worker.yml", "docker-compose.worker-release.yml"]
    command = ["docker", "compose", "--env-file", str(env_path)]
    for name in names:
        command += ["-f", str(compose_dir / name)]
    try:
        result = subprocess.run(command + ["config", "--format", "json"], env=environment, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        fail("Docker Compose indisponível ou excedeu prazo de validação")
    if result.returncode:
        # Não imprimir stderr: interpolação pode incluir valores privados.
        fail(f"Compose {selected} inválido; confira variáveis obrigatórias e versão com suporte a !reset/!override")
    try:
        config = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail("Compose não retornou configuração JSON válida")
    services = config["services"]
    active = ["postgres", "api", "caddy"] if selected == "api" else ["worker"]
    for name in active:
        service = services[name]
        image = service.get("image", "")
        image_name = image.split("@", 1)[0]
        if not digest.fullmatch(image) or image_name.rsplit(":", 1)[-1].lower() == "latest":
            fail(f"{selected}/{name}: imagem precisa de digest sha256 e não pode usar latest")
        if service.get("build"):
            fail(f"{selected}/{name}: build não permitido na configuração de release")
    token = services["api" if selected == "api" else "worker"].get("environment", {}).get("WORKER_TOKEN", "")
    if len(token) < 32:
        fail("WORKER_TOKEN precisa ter pelo menos 32 caracteres")
    if selected == "api":
        api_env = services["api"].get("environment", {})
        password = services["postgres"].get("environment", {}).get("POSTGRES_PASSWORD", "")
        if len(password) < 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", password):
            fail("POSTGRES_PASSWORD precisa de 32 caracteres seguros para a URL")
        if api_env.get("APP_ENV") != "production":
            fail("APP_ENV precisa ser production no release")
        address = services["caddy"].get("environment", {}).get("SITE_ADDRESS", "")
        if not re.fullmatch(r"(?:https://)?[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", address) or "." not in address:
            fail("SITE_ADDRESS precisa de domínio HTTPS, sem :80 ou http://")
    else:
        model_mounts = [mount for mount in services["worker"].get("volumes", []) if mount.get("target") == "/models"]
        if len(model_mounts) != 1 or not model_mounts[0].get("read_only"):
            fail("worker precisa de /models montado somente leitura")
    print(f"Release {selected}: Compose e referências imutáveis válidos; documentos e ambiente conferidos.")
print("Validação de configuração apenas: não comprova imagem disponível, GPU, piloto nem aceite do cliente.")
PY
