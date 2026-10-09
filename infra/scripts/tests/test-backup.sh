#!/usr/bin/env bash
# Stack descartável, API real e PostgreSQL real. Nunca aponta ao projeto avatar.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"
TEMP="$(mktemp -d)"
PROJECT="avatar-backup-test-$(date +%s)-$$"
IMAGE="${BACKUP_TEST_API_IMAGE:-avatar-api:p06-local}"
docker image inspect "$IMAGE" >/dev/null
COMPOSE=(docker compose --project-name "$PROJECT" --env-file "$TEMP/.env" -f "$TEMP/compose.yml")
RESTORE_VOLUME="$PROJECT-restore"
cleanup() {
  "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  docker volume rm "$RESTORE_VOLUME" >/dev/null 2>&1 || true
  rmdir "/tmp/avatar-backup-$PROJECT.lock" >/dev/null 2>&1 || true
  rm -rf "$TEMP"
}
trap cleanup EXIT
cat > "$TEMP/.env" <<EOF
TEST_API_IMAGE=$IMAGE
EOF
chmod 600 "$TEMP/.env"
cat > "$TEMP/compose.yml" <<'YML'
services:
  postgres:
    image: postgres:18.6@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722
    environment:
      POSTGRES_USER: avatar
      POSTGRES_DB: avatar
      POSTGRES_PASSWORD: isolated-backup-password-123456789
    volumes: [pgdata:/var/lib/postgresql]
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U avatar -d avatar']
      interval: 1s
      timeout: 5s
      retries: 60
  api:
    image: ${TEST_API_IMAGE}
    environment:
      DATABASE_URL: postgresql://avatar:isolated-backup-password-123456789@postgres:5432/avatar
      WORKER_TOKEN: isolated-backup-worker-token-123456789
      APP_ENV: test
      DATA_DIR: /data
    volumes: [appdata:/data]
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3)"]
      interval: 1s
      timeout: 5s
      retries: 60
volumes:
  pgdata:
  appdata:
YML
"${COMPOSE[@]}" up -d --wait --wait-timeout 120
"${COMPOSE[@]}" exec -T postgres psql -U avatar -d avatar -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE backup_probe (id integer PRIMARY KEY, spoken_text text NOT NULL);
INSERT INTO backup_probe VALUES (1, 'Fala literal preservada: R$ 12,50.');
SQL
printf 'arquivo persistido\ncom segunda linha\n' > "$TEMP/expected.txt"
"${COMPOSE[@]}" exec -T api sh -c 'cat > /data/backup-probe.txt' < "$TEMP/expected.txt"
ARGS=(--env-file "$TEMP/.env" --compose-file "$TEMP/compose.yml" --project-name "$PROJECT")
TEST_API_IMAGE=invalid-environment-image:must-not-run \
  bash "$ROOT/infra/scripts/backup.sh" "${ARGS[@]}" --destination "$TEMP/snapshot"
[ -f "$TEMP/snapshot/COMPLETE" ]
python3 - "$TEMP/snapshot" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
p = Path(sys.argv[1])
for name, expected in json.loads((p / 'manifest.json').read_text())['sha256'].items():
    with (p / name).open('rb') as source:
        assert hashlib.file_digest(source, 'sha256').hexdigest() == expected
PY
"${COMPOSE[@]}" exec -T postgres createdb -U avatar restored
"${COMPOSE[@]}" exec -T postgres pg_restore --exit-on-error --no-owner -U avatar -d restored < "$TEMP/snapshot/database.dump"
ACTUAL="$("${COMPOSE[@]}" exec -T postgres psql -U avatar -d restored -Atc 'SELECT spoken_text FROM backup_probe WHERE id=1')"
[ "$ACTUAL" = 'Fala literal preservada: R$ 12,50.' ]
docker volume create "$RESTORE_VOLUME" >/dev/null
docker run --rm -i --user 0 --volume "$RESTORE_VOLUME:/data" --entrypoint tar "$IMAGE" -C /data -xf - < "$TEMP/snapshot/data.tar"
docker run --rm --volume "$RESTORE_VOLUME:/data" --entrypoint cat "$IMAGE" /data/backup-probe.txt > "$TEMP/restored.txt"
cmp "$TEMP/expected.txt" "$TEMP/restored.txt"
echo 'PASS: dump restaurado preservou linha exata e arquivo restaurado preservou todos os bytes.'
# Falha real de leitura no tar: o usuário não-root da API não lê o arquivo.
"${COMPOSE[@]}" exec -T api chmod 000 /data/backup-probe.txt
if bash "$ROOT/infra/scripts/backup.sh" "${ARGS[@]}" --destination "$TEMP/failed"; then
  echo 'FAIL: arquivo ilegível não interrompeu backup' >&2; exit 1
fi
[ ! -e "$TEMP/failed/COMPLETE" ]
API_ID="$("${COMPOSE[@]}" ps -q api)"
[ "$(docker inspect --format '{{.State.Running}}' "$API_ID")" = true ]
"${COMPOSE[@]}" exec -T api python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/readyz').status == 200"
"${COMPOSE[@]}" exec -T api chmod 644 /data/backup-probe.txt
echo 'PASS: falha real rejeitou snapshot parcial e API voltou saudável.'
if bash "$ROOT/infra/scripts/backup.sh" "${ARGS[@]}" --destination "$TEMP/snapshot"; then
  echo 'FAIL: backup existente foi sobrescrito' >&2; exit 1
fi
[ "$(docker inspect --format '{{.State.Running}}' "$API_ID")" = true ]
echo 'PASS: destino existente recusado sem parar API.'
mkdir -m 700 "/tmp/avatar-backup-$PROJECT.lock"
if bash "$ROOT/infra/scripts/backup.sh" "${ARGS[@]}" --destination "$TEMP/concurrent"; then
  echo 'FAIL: lock de backup foi ignorado' >&2; exit 1
fi
[ ! -e "$TEMP/concurrent" ]
[ "$(docker inspect --format '{{.State.Running}}' "$API_ID")" = true ]
rmdir "/tmp/avatar-backup-$PROJECT.lock"
echo 'PASS: backup concorrente recusado sem criar snapshot nem parar API.'
