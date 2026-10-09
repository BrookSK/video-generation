import asyncio
import logging
import tempfile
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from avatar_api import api_v1, internal_v1, jobs, panel
from avatar_api.config import Settings
from avatar_api.db import get_engine
from avatar_api.errors import register_error_handlers

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


def _sweep_once(database_url: str) -> jobs.SweepResult:
    with Session(get_engine(database_url)) as session:
        return jobs.sweep_expired_leases(session)


async def _sweep_forever(settings: Settings) -> None:
    """Varre os leases vencidos a cada SWEEP_INTERVAL_SECONDS numa thread, fora do laço de
    eventos; uma falha é registrada e a próxima rodada segue normalmente."""
    while True:
        await asyncio.sleep(settings.sweep_interval_seconds)
        try:
            result = await asyncio.to_thread(_sweep_once, settings.database_url)
        except Exception:
            logger.exception("falha na varredura de leases vencidos")
            continue
        if result.requeued or result.lost:
            logger.info(
                "varredura de leases: %d item(ns) de volta à fila, %d com %s",
                result.requeued,
                result.lost,
                jobs.WORKER_LOST,
            )


def _database_ready(database_url: str) -> bool:
    try:
        with get_engine(database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.warning("readyz: banco de dados indisponível")
        return False
    return True


def _storage_ready(settings: Settings) -> bool:
    try:
        # Cria e remove um arquivo temporário: prova que o volume aceita escrita.
        with tempfile.NamedTemporaryFile(dir=settings.data_dir, prefix=".readyz-"):
            pass
    except OSError:
        logger.warning("readyz: DATA_DIR sem escrita")
        return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweeper = asyncio.create_task(_sweep_forever(app.state.settings))
    try:
        yield
    finally:
        sweeper.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="avatar-api", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.settings = settings
    register_error_handlers(app)
    app.include_router(panel.router)
    app.include_router(api_v1.router)
    app.include_router(internal_v1.router)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        database = _database_ready(settings.database_url)
        storage = _storage_ready(settings)
        ready = database and storage
        body = {
            "status": "ok" if ready else "unavailable",
            "database": "ok" if database else "error",
            "storage": "ok" if storage else "error",
        }
        return JSONResponse(body, status_code=200 if ready else 503)

    # Só documentação offline: não expõe /openapi.json nem altera a autenticação.
    schema = app.openapi()
    schema["components"]["securitySchemes"] = {
        "ApiKeyBearer": {
            "type": "http",
            "scheme": "bearer",
            "description": "Chave criada no painel.",
        }
    }
    for path, operations in schema["paths"].items():
        if path.startswith("/api/v1/"):
            for operation in operations.values():
                operation["security"] = [{"ApiKeyBearer": []}]

    return app
