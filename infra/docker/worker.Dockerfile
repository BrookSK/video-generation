# Imagem do worker (piloto e, a partir da P03, serviço worker). Build pela raiz do repositório:
#   docker build -f infra/docker/worker.Dockerfile .
# Só roda em host linux x86_64 com GPU NVIDIA; os runtimes travam torch com CUDA.
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

# Fallback do flash_attn, usado só se a T13 provar que a wheel fixada no runtime de avatar
# não instala: um estágio "build-flash-attn" a partir de
#   nvidia/cuda:12.6.3-devel-ubuntu24.04@sha256:392c0df7b577ecae17a17f6ba7f2009c217bb4422f8431c053ae9af61a8c148a
# instala o uv e o Python 3.10 como abaixo, sincroniza runtimes/avatar sem flash-attn e compila
# uma vez flash-attn==2.7.4.post1 com "uv build --wheel" e MAX_JOBS limitado. A imagem final
# copia essa wheel do estágio e a instala no lugar da URL do manifesto, registrando o desvio.

FROM nvidia/cuda:12.6.3-base-ubuntu24.04@sha256:c87e78933f4c16e3272123bf2f75537306596d0fbaa395a29696a22786e5ee0e

# libgl1 e libglib2.0-0t64: exigidas pelo opencv-python do runtime de avatar.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg git libgl1 libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python

# Pythons gerenciados pelo uv: 3.12 para o worker e o TTS, 3.10 para o InfiniteTalk.
RUN uv python install 3.12.13 3.10.20

ENV UV_PYTHON_DOWNLOADS=never \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    U2NET_HOME=/models/birefnet-portrait \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PATH=/app/apps/worker/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app/apps/worker

# Cada runtime tem o próprio .venv em runtimes/<nome>/.venv, caminho padrão do piloto.
COPY apps/worker/runtimes/tts/pyproject.toml apps/worker/runtimes/tts/uv.lock ./runtimes/tts/
RUN uv sync --frozen --no-dev --directory runtimes/tts

COPY apps/worker/runtimes/avatar/pyproject.toml apps/worker/runtimes/avatar/uv.lock ./runtimes/avatar/
RUN uv sync --frozen --no-dev --directory runtimes/avatar

COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Código do InfiniteTalk na URL e no commit do manifesto, em /opt/infinitetalk (padrão do piloto).
COPY docs/models /app/docs/models
RUN set -- $(.venv/bin/python -c "import json; c = {c['id']: c for c in json.load(open('/app/docs/models/MODEL_MANIFEST.json'))['components']}['infinitetalk-code']; print(c['url'], c['revision'])") \
    && git init --quiet /opt/infinitetalk \
    && git -C /opt/infinitetalk fetch --quiet --depth 1 "$1" "$2" \
    && git -C /opt/infinitetalk checkout --quiet --detach FETCH_HEAD \
    && test "$(git -C /opt/infinitetalk rev-parse HEAD)" = "$2" \
    && rm -rf /opt/infinitetalk/.git

# Instalação editável: o piloto acha runtimes/ relativo a src/.
COPY apps/worker ./
RUN uv sync --frozen --no-dev

# Home própria para caches de bibliotecas; /models e /pilot vêm de volumes.
RUN useradd --no-log-init --uid 10001 --user-group --create-home --shell /usr/sbin/nologin app

USER app

WORKDIR /app
