#!/usr/bin/env bash
# Banco e /data são fotografados com a API parada; o worker nunca escreve nesses volumes.
set -euo pipefail
umask 077
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE="$ROOT/infra/compose/.env"
FILES=()
PROJECT=avatar
DESTINATION=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --env-file) ENV_FILE="${2:?Falta caminho de ambiente}"; shift 2 ;;
    --compose-file) FILES+=("${2:?Falta arquivo Compose}"); shift 2 ;;
    --project-name) PROJECT="${2:?Falta nome de projeto}"; shift 2 ;;
    --destination) DESTINATION="${2:?Falta destino novo}"; shift 2 ;;
    *) echo 'Uso: backup.sh --destination diretório-novo [--env-file arquivo] [--compose-file arquivo ...] [--project-name nome]' >&2; exit 2 ;;
  esac
done
[ -n "$DESTINATION" ] || { echo 'Informe --destination em disco com espaço suficiente.' >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo 'Ambiente privado não encontrado.' >&2; exit 1; }
if [ "${#FILES[@]}" -eq 0 ]; then
  for name in docker-compose.yml docker-compose.cpu.yml docker-compose.api.yml docker-compose.release.yml; do
    FILES+=("$ROOT/infra/compose/$name")
  done
fi
COMPOSE=(docker compose --project-name "$PROJECT" --env-file "$ENV_FILE")
for file in "${FILES[@]}"; do COMPOSE+=(-f "$file"); done
running() {
  local id
  id="$("${COMPOSE[@]}" ps -q "$1")"
  [ -n "$id" ] && [ "$(docker inspect --format '{{.State.Running}}' "$id")" = true ]
}
case "$PROJECT" in
  ''|*[!a-z0-9_-]*) echo 'Nome de projeto inválido para backup.' >&2; exit 2 ;;
esac
LOCK="/tmp/avatar-backup-$PROJECT.lock"
mkdir -m 700 -- "$LOCK" 2>/dev/null || { echo 'Backup já em execução ou lock pendente; confira o operador antes de continuar.' >&2; exit 1; }
trap 'rmdir -- "$LOCK"' EXIT
running postgres && running api || { echo 'Backup exige postgres e api em execução; não altera uma stack parada.' >&2; exit 1; }
# mkdir exclusivo impede sobrescrever backup existente, inclusive destino parcial.
mkdir -m 700 -- "$DESTINATION"
DESTINATION="$(CDPATH= cd -- "$DESTINATION" && pwd)"
QUIESCED=0
resume() {
  if [ "$QUIESCED" -eq 1 ]; then
    if ! "${COMPOSE[@]}" start --wait --wait-timeout 120 api >&2; then
      return 1
    fi
    QUIESCED=0
  fi
}
cleanup() {
  local status=$?
  trap - EXIT
  if ! resume; then
    echo 'ATENÇÃO: falha ao reativar API; execute start e confira saúde imediatamente.' >&2
    status=1
  fi
  if [ "$status" -ne 0 ]; then
    echo "Backup interrompido; não use arquivos sem COMPLETE: $DESTINATION" >&2
  fi
  rmdir -- "$LOCK" || status=1
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
QUIESCED=1
"${COMPOSE[@]}" stop --timeout 30 api >&2
"${COMPOSE[@]}" exec -T postgres pg_dump --username=avatar --dbname=avatar --format=custom > "$DESTINATION/database.dump.partial"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint tar api -C /data -cf - . > "$DESTINATION/data.tar.partial"
# Metadados não incluem .env, cookies, chaves nem configuração interpolada.
API_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$("${COMPOSE[@]}" ps -aq api)")"
PG_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$("${COMPOSE[@]}" ps -q postgres)")"
python3 - "$DESTINATION" "$PROJECT" "$API_IMAGE_ID" "$PG_IMAGE_ID" <<'PY'
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
hashes = {}
for name in ["database.dump", "data.tar"]:
    partial = path / (name + ".partial")
    with partial.open("rb") as source:
        hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
    partial.rename(path / name)
(path / "manifest.json").write_text(json.dumps({"created_at": datetime.now(UTC).isoformat(), "project": sys.argv[2], "runtime_image_ids": {"api": sys.argv[3], "postgres": sys.argv[4]}, "sha256": hashes, "consistency": "API stopped during database dump and data archive"}, indent=2) + "\n")
PY
resume
printf 'Backup consistente concluído; verifique manifest.json antes de restaurar.\n' > "$DESTINATION/COMPLETE"
echo "Backup concluído: $DESTINATION"
