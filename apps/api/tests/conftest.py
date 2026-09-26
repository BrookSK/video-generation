from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from avatar_api.config import Settings
from avatar_api.db import create_db_engine, get_engine
from avatar_api.devseed import DevCatalog, seed_dev_catalog
from avatar_api.main import create_app
from avatar_api.models import Base

API_DIR = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:18.6"


def alembic_config(connection) -> Config:
    config = Config(toml_file=str(API_DIR / "pyproject.toml"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    config.attributes["connection"] = connection
    return config


def migrate(database_url: str, revision: str = "head", downgrade: bool = False) -> None:
    engine = create_db_engine(database_url)
    try:
        with engine.begin() as connection:
            config = alembic_config(connection)
            if downgrade:
                command.downgrade(config, revision)
            else:
                command.upgrade(config, revision)
    finally:
        engine.dispose()


@pytest.fixture(scope="session", name="migrate")
def migrate_fixture():
    """Aplica ou desfaz migrações num banco qualquer: migrate(url, revision, downgrade)."""
    return migrate


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres: PostgresContainer) -> str:
    url = postgres.get_connection_url()
    migrate(url)
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = get_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def settings(database_url: str, tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return Settings(
        database_url=database_url,
        data_dir=data_dir,
        worker_token="token-do-worker-de-teste",
        app_env="test",
    )


@pytest.fixture
def seeded_catalog(session: Session, settings: Settings) -> DevCatalog:
    return seed_dev_catalog(session, settings.data_dir)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture(autouse=True)
def _truncate_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    # Só testes que tocam o banco pagam a limpeza; os demais nem sobem o contêiner.
    if "database_url" not in request.fixturenames:
        yield
        return
    engine = request.getfixturevalue("engine")
    yield
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
