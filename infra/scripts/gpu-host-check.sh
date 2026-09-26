#!/usr/bin/env bash
# Confere se o servidor GPU está pronto para o worker: Ubuntu 24.04, driver NVIDIA,
# Docker, Compose, NVIDIA Container Toolkit e a GPU visível dentro de um contêiner.
# Uso, a partir de um clone do repositório: bash infra/scripts/gpu-host-check.sh
# Para no primeiro item que falhar, com código diferente de zero.
set -euo pipefail

MIN_DRIVER=560.28.03
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
dockerfile="$repo_root/infra/docker/worker.Dockerfile"

ok() { printf 'ok     %-24s %s\n' "$1" "$2"; }
fail() {
    printf 'FALHA  %-24s %s\n' "$1" "$2" >&2
    exit 1
}
need() { command -v "$1" >/dev/null 2>&1 || fail "$2" "comando $1 não encontrado"; }

[[ -r /etc/os-release ]] || fail "Sistema" "/etc/os-release ausente; o servidor precisa de Ubuntu 24.04"
# shellcheck source=/dev/null
os=$(. /etc/os-release && printf '%s %s' "${ID:-?}" "${VERSION_ID:-?}")
[[ $os == "ubuntu 24.04" ]] || fail "Sistema" "encontrado '$os'; o servidor precisa de Ubuntu 24.04"
ok "Sistema" "Ubuntu 24.04"

need nvidia-smi "Driver NVIDIA"
if ! out=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>&1); then
    fail "Driver NVIDIA" "nvidia-smi falhou no host: $out"
fi
driver=${out%%$'\n'*}
[[ $driver =~ ^[0-9]+(\.[0-9]+)+$ ]] || fail "Driver NVIDIA" "versão ilegível: '$driver'"
if ! printf '%s\n%s\n' "$MIN_DRIVER" "$driver" | sort -V -C; then
    fail "Driver NVIDIA" "versão $driver abaixo da mínima $MIN_DRIVER exigida pelo CUDA 12.6"
fi
ok "Driver NVIDIA" "$driver (mínimo $MIN_DRIVER)"

need docker "Docker"
if ! docker_version=$(docker version --format '{{.Server.Version}}' 2>&1); then
    fail "Docker" "o daemon não respondeu (parado ou usuário sem acesso ao socket): $docker_version"
fi
ok "Docker" "$docker_version"

if ! compose_version=$(docker compose version --short 2>&1); then
    fail "Docker Compose" "plugin docker compose ausente: $compose_version"
fi
ok "Docker Compose" "$compose_version"

need nvidia-ctk "NVIDIA Container Toolkit"
if ! toolkit_version=$(nvidia-ctk --version 2>&1); then
    fail "NVIDIA Container Toolkit" "nvidia-ctk falhou: $toolkit_version"
fi
ok "NVIDIA Container Toolkit" "${toolkit_version%%$'\n'*}"

if ! runtimes=$(docker info --format '{{json .Runtimes}}' 2>&1); then
    fail "Runtime nvidia" "docker info falhou: $runtimes"
fi
if [[ $runtimes != *'"nvidia"'* ]]; then
    fail "Runtime nvidia" "ausente no Docker; rode sudo nvidia-ctk runtime configure --runtime=docker e sudo systemctl restart docker"
fi
ok "Runtime nvidia" "configurado no Docker"

image=$(sed -n 's/^FROM \(nvidia\/cuda:[^ ]*\).*/\1/p' "$dockerfile")
[[ -n $image ]] || fail "GPU no contêiner" "imagem CUDA base não encontrada em $dockerfile"
if ! gpu=$(docker run --rm --quiet --gpus all --entrypoint nvidia-smi "$image" \
    --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1); then
    fail "GPU no contêiner" "docker run --gpus all falhou com $image: $gpu"
fi
ok "GPU no contêiner" "$gpu"

printf '\nResumo: servidor GPU pronto (Ubuntu 24.04, driver %s, Docker %s, Compose %s).\n' \
    "$driver" "$docker_version" "$compose_version"
printf 'GPU vista pelo contêiner (nome, VRAM total, driver): %s\n' "$gpu"
