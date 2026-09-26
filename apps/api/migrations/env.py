import os

from alembic import context

from avatar_api.db import create_db_engine
from avatar_api.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Os testes passam uma conexão pronta; fora deles, o banco vem só de DATABASE_URL.
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não definida.")
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            _run(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Modo offline do Alembic não é suportado.")
run_migrations_online()
