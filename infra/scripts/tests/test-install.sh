#!/usr/bin/env bash
# Imagens reais em cache; entradas inválidas nunca devem criar recursos Docker.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
TEMP="$(mktemp -d)"
PROJECT="avatar-install-test-$(date +%s)-$$"
API_IMAGE="$(docker image inspect avatar-api:p06-local --format '{{index .RepoDigests 0}}')"
PANEL_IMAGE="$(docker image inspect avatar-panel:p06-local --format '{{index .RepoDigests 0}}')"
cleanup() {
  docker compose --project-name "$PROJECT" --env-file "$TEMP/.env" -f "$TEMP/infra/compose/docker-compose.yml" -f "$TEMP/infra/compose/docker-compose.cpu.yml" -f "$TEMP/infra/compose/docker-compose.api.yml" -f "$TEMP/infra/compose/docker-compose.release.yml" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$TEMP"
}
trap cleanup EXIT
mkdir -p "$TEMP/infra/compose" "$TEMP/infra/scripts" "$TEMP/docs/operacao" "$TEMP/docs/api" "$TEMP/docs/homologacao"
cp "$ROOT/infra/compose/"*.yml "$ROOT/infra/compose/.env.example" "$ROOT/infra/compose/Caddyfile" "$TEMP/infra/compose/"
cp "$ROOT/infra/scripts/install.sh" "$ROOT/infra/scripts/check-release.sh" "$TEMP/infra/scripts/"
for file in docs/operacao/INSTALACAO.md docs/operacao/USO.md docs/operacao/OPERACAO.md docs/api/GUIA.md docs/api/openapi.json docs/homologacao/MATRIZ.md docs/homologacao/PROCEDIMENTO.md docs/homologacao/FORA_DO_ESCOPO.md; do
  printf 'Documento isolado para testar presença.\n' > "$TEMP/$file"
done
# Mesmo se um bug ultrapassar preflight, não ocupar portas do operador.
python3 - "$TEMP/infra/compose/docker-compose.release.yml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
s = s.replace('  api:\n', '  api:\n    ports: !override []\n', 1)
s = s.replace('    ports: !override\n      - "80:80"\n      - "443:443"', '    ports: !override []')
p.write_text(s + '\n')
PY
write_env() {
  cat > "$TEMP/.env" <<EOF
POSTGRES_PASSWORD=isolated-install-password-123456789
WORKER_TOKEN=isolated-install-worker-token-123456789
APP_ENV=production
SITE_ADDRESS=isolated.example.test
API_IMAGE=$API_IMAGE
PANEL_IMAGE=$PANEL_IMAGE
EOF
  chmod 600 "$TEMP/.env"
}
untouched() {
  [ -z "$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT")" ]
  [ -z "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT")" ]
  [ -z "$(docker network ls -q --filter "label=com.docker.compose.project=$PROJECT")" ]
}
reject() {
  if bash "$TEMP/infra/scripts/install.sh" --role api --env-file "$TEMP/.env" --project-name "$PROJECT" --no-pull > "$TEMP/output" 2>&1; then
    echo "FAIL: $1 iniciou instalação" >&2; exit 1
  fi
  untouched
  echo "PASS: $1 recusado sem containers, volumes ou redes."
}
write_env
bash "$TEMP/infra/scripts/check-release.sh" --role api --env-file "$TEMP/.env"
untouched
printf 'POSTGRES_PASSWORD=fraca\n' >> "$TEMP/.env"
reject senha-fraca
write_env
printf 'WORKER_TOKEN=fraco\n' >> "$TEMP/.env"
reject token-fraco
write_env
printf 'APP_ENV=development\n' >> "$TEMP/.env"
reject modo-development
write_env
printf 'SITE_ADDRESS=http://isolated.example.test\n' >> "$TEMP/.env"
reject HTTP-sem-TLS
write_env
chmod 644 "$TEMP/.env"
reject ambiente-publico
