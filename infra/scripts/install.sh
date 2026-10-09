#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE="$ROOT/infra/compose/.env"
ROLE=
PROJECT=
PULL=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --role) ROLE="${2:?Falta papel}"; shift 2 ;;
    --env-file) ENV_FILE="${2:?Falta ambiente}"; shift 2 ;;
    --project-name) PROJECT="${2:?Falta projeto}"; shift 2 ;;
    --no-pull) PULL=0; shift ;;
    *) echo 'Uso: install.sh --role api|worker [--env-file arquivo] [--project-name nome] [--no-pull]' >&2; exit 2 ;;
  esac
done
case "$ROLE" in
  api) FILES=(docker-compose.yml docker-compose.cpu.yml docker-compose.api.yml docker-compose.release.yml); SERVICES=(postgres api caddy); PROJECT="${PROJECT:-avatar}" ;;
  worker) FILES=(docker-compose.worker.yml docker-compose.worker-release.yml); SERVICES=(worker); PROJECT="${PROJECT:-avatar-gpu}" ;;
  *) echo 'Informe --role api ou --role worker.' >&2; exit 2 ;;
esac
# Nenhum pull/up/volume antes desta validação. Nunca imprimir ambiente interpolado.
bash "$ROOT/infra/scripts/check-release.sh" --env-file "$ENV_FILE" --role "$ROLE"
COMPOSE=(docker compose --project-name "$PROJECT" --env-file "$ENV_FILE")
for file in "${FILES[@]}"; do COMPOSE+=(-f "$ROOT/infra/compose/$file"); done
if [ "$PULL" -eq 1 ]; then
  "${COMPOSE[@]}" pull "${SERVICES[@]}"
else
  # Não transformar imagem ausente em download/build implícito no modo offline.
  CONFIG="$("${COMPOSE[@]}" config --format json)"
  IMAGES="$(printf '%s' "$CONFIG" | python3 -c 'import json,sys; c=json.load(sys.stdin); print("\n".join(c["services"][name]["image"] for name in sys.argv[1:]))' "${SERVICES[@]}")"
  while IFS= read -r image; do
    docker image inspect "$image" >/dev/null 2>&1 || { echo 'Imagem imutável ausente no cache; faça pull autorizado antes da instalação.' >&2; exit 1; }
  done <<< "$IMAGES"
fi
"${COMPOSE[@]}" up -d --no-build --pull never --wait --wait-timeout 180 "${SERVICES[@]}"
if [ "$ROLE" = api ]; then
  "${COMPOSE[@]}" exec -T api python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5).status == 200; print('API pronta; migrações aplicadas pelo entrypoint.')"
  echo 'Crie o primeiro usuário com avatar-api users create --username, senha interativa, conforme INSTALACAO.md.'
  echo 'Receita só pode ser carregada após piloto real aprovado; sem ela a geração permanece indisponível.'
else
  echo 'Worker iniciado. Confirme heartbeat, pesos completos e job real; processo em execução não comprova GPU/inferência.'
fi
echo 'Instalação iniciada sem apagar volumes. HTTPS externo, túnel e homologação exigem verificação real separada.'
