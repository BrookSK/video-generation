#!/usr/bin/env bash
# Baixa os pesos de docs/models/MODEL_MANIFEST.json para MODELS_DIR, conferindo SHA-256 e
# tamanho de cada arquivo. Roda dentro da imagem avatar-worker:pilot, construída antes com
#   docker compose -f infra/compose/docker-compose.pilot.yml build
# Uso: MODELS_DIR=/srv/avatar/models bash infra/scripts/models-pull.sh
# Reexecutar é seguro: arquivo já presente com hash correto não é baixado de novo.
# Não usa token: os repositórios do manifesto são públicos e nenhuma variável do host
# entra no contêiner.
set -euo pipefail

IMAGE=avatar-worker:pilot
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

fail() {
    printf 'Erro: %s\n' "$1" >&2
    exit 1
}

[[ -n ${MODELS_DIR:-} ]] || fail "defina MODELS_DIR com o caminho absoluto dos pesos (ex.: /srv/avatar/models)"
[[ $MODELS_DIR == /* ]] || fail "MODELS_DIR precisa ser caminho absoluto (recebido: $MODELS_DIR)"
[[ -d $MODELS_DIR ]] || fail "MODELS_DIR não existe: crie com mkdir -p $MODELS_DIR"
[[ -w $MODELS_DIR ]] || fail "MODELS_DIR sem permissão de escrita para o usuário $(id -un)"
command -v docker >/dev/null 2>&1 || fail "comando docker não encontrado"
docker image inspect "$IMAGE" >/dev/null 2>&1 \
    || fail "imagem $IMAGE ausente; construa com docker compose -f infra/compose/docker-compose.pilot.yml build"

exec docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "$MODELS_DIR:/models" \
    --volume "$repo_root/docs/models:/app/docs/models:ro" \
    --entrypoint python \
    "$IMAGE" -m avatar_worker.manifest pull \
    --policy /app/docs/models/MODEL_MANIFEST.json --dest /models
