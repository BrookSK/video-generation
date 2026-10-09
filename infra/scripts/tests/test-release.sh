#!/usr/bin/env bash
# Configuração sintética: não baixa imagem nem aprova RC/cliente.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
mkdir -p "$TEMP/infra/compose" "$TEMP/infra/scripts" "$TEMP/docs/operacao" "$TEMP/docs/api" "$TEMP/docs/homologacao"
cp "$ROOT/infra/compose/"*.yml "$ROOT/infra/compose/.env.example" "$ROOT/infra/compose/Caddyfile" "$TEMP/infra/compose/"
cp "$ROOT/infra/scripts/check-release.sh" "$TEMP/infra/scripts/"
for file in docs/operacao/INSTALACAO.md docs/operacao/USO.md docs/operacao/OPERACAO.md docs/api/GUIA.md docs/api/openapi.json docs/homologacao/MATRIZ.md docs/homologacao/PROCEDIMENTO.md docs/homologacao/FORA_DO_ESCOPO.md; do
  printf 'Documento isolado para testar presença.\n' > "$TEMP/$file"
done
ENV_FILE="$TEMP/infra/compose/.env"
DIGEST=5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722
write_env() {
  cat > "$ENV_FILE" <<EOF
POSTGRES_PASSWORD=isolated-postgres-password-123456789
WORKER_TOKEN=isolated-worker-token-123456789012345
APP_ENV=production
SITE_ADDRESS=isolated.example.test
API_IMAGE=fixture-api@sha256:$DIGEST
PANEL_IMAGE=fixture-panel@sha256:$DIGEST
WORKER_IMAGE=fixture-worker@sha256:$DIGEST
MODELS_DIR=/srv/avatar/models
EOF
  chmod 600 "$ENV_FILE"
}
reject() {
  local label="$1" expected="$2"
  if bash "$TEMP/infra/scripts/check-release.sh" --env-file "$ENV_FILE" > "$TEMP/output" 2>&1; then
    echo "FAIL: $label foi aceito" >&2; exit 1
  fi
  if ! /usr/bin/grep -Fq "$expected" "$TEMP/output"; then
    cat "$TEMP/output" >&2; echo "FAIL: $label teve diagnóstico inesperado" >&2; exit 1
  fi
  echo "PASS: $label recusado"
}
write_env
bash "$TEMP/infra/scripts/check-release.sh" --env-file "$ENV_FILE"
printf 'API_IMAGE=fixture-api:latest@sha256:%s\n' "$DIGEST" >> "$ENV_FILE"
reject latest 'não pode usar latest'
write_env
printf 'WORKER_IMAGE=fixture-worker:release\n' >> "$ENV_FILE"
reject imagem-sem-digest 'precisa de digest sha256'
write_env
printf 'WORKER_TOKEN=curto\n' >> "$ENV_FILE"
reject token-curto 'pelo menos 32'
write_env
printf 'SITE_ADDRESS=:80\n' >> "$ENV_FILE"
reject HTTP-publico 'domínio HTTPS'
write_env
chmod 644 "$ENV_FILE"
reject ambiente-legivel 'permissões 600'
write_env
printf '\n# variável acidental ${UNLISTED_RELEASE_SETTING:-}\n' >> "$TEMP/infra/compose/docker-compose.yml"
reject variavel-sem-exemplo 'UNLISTED_RELEASE_SETTING'
cp "$ROOT/infra/compose/docker-compose.yml" "$TEMP/infra/compose/docker-compose.yml"
rm "$TEMP/docs/homologacao/MATRIZ.md"
reject documento-ausente 'MATRIZ.md'
echo 'PASS: guard real exercitado; nenhuma imagem fixture foi executada.'
