from collections.abc import Iterator
from functools import cache

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

CONNECT_TIMEOUT_SECONDS = 3


def _psycopg_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def create_db_engine(database_url: str) -> Engine:
    return create_engine(
        _psycopg_url(database_url),
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS, "options": "-c timezone=UTC"},
    )


@cache
def get_engine(database_url: str) -> Engine:
    return create_db_engine(database_url)


@cache
def _session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(get_engine(database_url), expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """Dependência FastAPI: uma sessão por requisição, sempre fechada no fim."""
    with _session_factory(request.app.state.settings.database_url)() as session:
        yield session
