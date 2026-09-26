import asyncio
import logging
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
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

    return app
