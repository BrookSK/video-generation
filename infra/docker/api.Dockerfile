# Imagem da API. Build pela raiz do repositório:
#   docker build -f infra/docker/api.Dockerfile .
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b

COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências primeiro, para reaproveitar a camada quando só o código muda.
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/src ./src
COPY apps/api/migrations ./migrations
RUN uv sync --frozen --no-dev --no-editable

RUN useradd --no-log-init --uid 10001 --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && mkdir /data \
    && chown app:app /data

USER app

EXPOSE 8000

# Migra e sobe a API. O log de acesso fica desligado para não gravar query strings.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn --factory avatar_api.main:create_app --host 0.0.0.0 --port 8000 --no-access-log"]
