import hashlib
import uuid
from collections.abc import Iterator

import psycopg.errors
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.config import Settings
from avatar_api.db import CONNECT_TIMEOUT_SECONDS, create_db_engine, get_session
from avatar_api.main import create_app
from avatar_api.models import (
    ApiKey,
    Avatar,
    Base,
    RenderRecipe,
    Scene,
    StoredFile,
    User,
    VideoJob,
)

TEN_TABLES = {
    "users",
    "sessions",
    "api_keys",
    "stored_files",
    "render_recipes",
    "avatars",
    "scenes",
    "video_jobs",
    "job_attempts",
    "asset_prepare_tasks",
}


# --- fábricas mínimas de linhas -------------------------------------------------------


def add_user(session: Session, username: str | None = None) -> User:
    user = User(username=username or f"user-{uuid.uuid4().hex[:8]}", password_hash="x")
    session.add(user)
    session.flush()
    return user


def add_api_key(session: Session, user: User) -> ApiKey:
    key = ApiKey(
        prefix=f"avk_{uuid.uuid4().hex[:8]}",
        key_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        description="teste",
        created_by_user_id=user.id,
    )
    session.add(key)
    session.flush()
    return key


def add_file(session: Session, name: str = "arquivo.png") -> StoredFile:
    stored = StoredFile(
        relative_path=f"testes/{uuid.uuid4()}/{name}",
        name=name,
        size_bytes=3,
        sha256=hashlib.sha256(b"abc").hexdigest(),
        content_type="image/png",
    )
    session.add(stored)
    session.flush()
    return stored


def add_recipe(session: Session, is_current: bool = True) -> RenderRecipe:
    recipe = RenderRecipe(
        name=f"receita-{uuid.uuid4().hex[:8]}",
        max_script_chars=600,
        spec={"dev": True},
        is_current=is_current,
    )
    session.add(recipe)
    session.flush()
    return recipe


def add_avatar(session: Session) -> Avatar:
    source = add_file(session)
    avatar = Avatar(
        name="Avatar",
        voice="feminina",
        source_file_id=source.id,
        prepared_file_id=source.id,
        prepare_status="ativo",
    )
    session.add(avatar)
    session.flush()
    return avatar


def add_scene(session: Session) -> Scene:
    scene = Scene(
        name="Cenário",
        background_color="#101010",
        composition={"9:16": {}, "16:9": {}},
    )
    session.add(scene)
    session.flush()
    return scene


@pytest.fixture
def catalog(session: Session) -> dict:
    user = add_user(session)
    return {
        "user": user,
        "api_key": add_api_key(session, user),
        "recipe": add_recipe(session),
        "avatar": add_avatar(session),
        "scene": add_scene(session),
    }


def new_job(catalog: dict, **overrides) -> VideoJob:
    avatar: Avatar = catalog["avatar"]
    values = {
        "origin": "api",
        "api_key_id": catalog["api_key"].id,
        "script_text": "Olá, mundo.",
        "avatar_id": avatar.id,
        "avatar_file_id": avatar.prepared_file_id,
        "scene_id": catalog["scene"].id,
        "voice": avatar.voice,
        "aspect_ratio": "9:16",
        "recipe_id": catalog["recipe"].id,
    }
    values.update(overrides)
    return VideoJob(**values)


def assert_violation(session: Session, error_type: type, constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc_info:
        session.flush()
    session.rollback()
    assert isinstance(exc_info.value.orig, error_type)
    assert exc_info.value.orig.diag.constraint_name == constraint


# --- migração ---------------------------------------------------------------------------


@pytest.fixture
def empty_database_url(engine: Engine) -> Iterator[str]:
    name = f"roundtrip_{uuid.uuid4().hex[:8]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f"CREATE DATABASE {name}"))
    yield engine.url.set(database=name).render_as_string(hide_password=False)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))


def _tables_and_revision(database_url: str) -> tuple[set[str], str | None]:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
            revision = MigrationContext.configure(connection).get_current_revision()
            server_version = connection.dialect.server_version_info
    finally:
        engine.dispose()
    assert server_version[0] == 18
    return tables, revision


def test_migracao_do_zero_ate_head_e_downgrade_ate_base(empty_database_url, migrate):
    assert _tables_and_revision(empty_database_url) == (set(), None)

    migrate(empty_database_url)
    assert _tables_and_revision(empty_database_url) == (TEN_TABLES, "0001")

    migrate(empty_database_url, "base", downgrade=True)
    assert _tables_and_revision(empty_database_url) == (set(), None)

    migrate(empty_database_url)
    assert _tables_and_revision(empty_database_url) == (TEN_TABLES, "0001")


def test_modelos_coincidem_com_a_migracao(engine):
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []
    assert {table.name for table in Base.metadata.sorted_tables} == TEN_TABLES


def test_fks_de_job_e_tarefa_usam_restrict(engine):
    inspector = inspect(engine)
    for table in ("video_jobs", "job_attempts", "asset_prepare_tasks", "avatars", "scenes"):
        for fk in inspector.get_foreign_keys(table):
            assert fk["options"].get("ondelete") == "RESTRICT", (table, fk["name"])


# --- restrições -------------------------------------------------------------------------


def test_uma_unica_receita_vigente(session):
    add_recipe(session, is_current=True)
    add_recipe(session, is_current=False)
    add_recipe(session, is_current=False)
    session.commit()

    session.add(RenderRecipe(name="outra", max_script_chars=10, spec={}, is_current=True))
    assert_violation(session, psycopg.errors.UniqueViolation, "uq_render_recipes_current")

    current = session.scalar(
        select(func.count()).select_from(RenderRecipe).where(RenderRecipe.is_current)
    )
    assert current == 1


def test_idempotency_key_unica_por_chave_de_api(session, catalog):
    other_key = add_api_key(session, catalog["user"])
    session.add_all(
        [
            new_job(catalog, idempotency_key="pedido-1", request_hash="a"),
            new_job(catalog, api_key_id=other_key.id, idempotency_key="pedido-1"),
            new_job(catalog),
            new_job(catalog),
        ]
    )
    session.commit()

    session.add(new_job(catalog, idempotency_key="pedido-1", request_hash="b"))
    assert_violation(session, psycopg.errors.UniqueViolation, "uq_video_jobs_idempotency_api_key")


def test_idempotency_key_unica_por_usuario_do_painel(session, catalog):
    user_id = catalog["user"].id
    panel = {"origin": "panel", "api_key_id": None, "requested_by_user_id": user_id}
    session.add(new_job(catalog, idempotency_key="intencao-1", **panel))
    session.commit()

    session.add(new_job(catalog, idempotency_key="intencao-1", **panel))
    assert_violation(session, psycopg.errors.UniqueViolation, "uq_video_jobs_idempotency_user")


def test_aspect_ratio_fora_do_dominio_recusado(session, catalog):
    session.add(new_job(catalog, aspect_ratio="1:1"))
    assert_violation(session, psycopg.errors.CheckViolation, "ck_video_jobs_aspect_ratio")


def test_origem_incoerente_com_solicitante_recusada(session, catalog):
    session.add(new_job(catalog, requested_by_user_id=catalog["user"].id))
    assert_violation(
        session, psycopg.errors.CheckViolation, "ck_video_jobs_requester_matches_origin"
    )


def test_job_ready_exige_arquivo_resultante(session, catalog):
    session.add(new_job(catalog, status="ready"))
    assert_violation(session, psycopg.errors.CheckViolation, "ck_video_jobs_ready_has_file")


def test_cenario_exige_exatamente_um_fundo(session):
    background = add_file(session, "fundo.png")
    session.commit()

    session.add(
        Scene(
            name="dois",
            background_file_id=background.id,
            background_color="#000",
            composition={},
        )
    )
    assert_violation(session, psycopg.errors.CheckViolation, "ck_scenes_one_background")

    session.add(Scene(name="nenhum", composition={}))
    assert_violation(session, psycopg.errors.CheckViolation, "ck_scenes_one_background")


def test_exclusao_de_avatar_referenciado_por_job_bloqueada(session, catalog):
    job = new_job(catalog)
    session.add(job)
    session.commit()
    avatar_id = catalog["avatar"].id

    with pytest.raises(IntegrityError) as exc_info:
        session.execute(delete(Avatar).where(Avatar.id == avatar_id))
    session.rollback()
    assert isinstance(exc_info.value.orig, psycopg.errors.RestrictViolation)
    assert exc_info.value.orig.diag.constraint_name == "fk_video_jobs_avatar_id_avatars"

    assert session.get(Avatar, avatar_id) is not None


def test_exclusao_de_arquivo_do_snapshot_bloqueada(session, catalog):
    scene_file = add_file(session, "fundo.png")
    session.add(new_job(catalog, scene_file_id=scene_file.id))
    session.commit()

    with pytest.raises(IntegrityError) as exc_info:
        session.execute(delete(StoredFile).where(StoredFile.id == scene_file.id))
    session.rollback()
    assert isinstance(exc_info.value.orig, psycopg.errors.RestrictViolation)
    assert exc_info.value.orig.diag.constraint_name == "fk_video_jobs_scene_file_id_stored_files"


# --- engine e sessão por requisição ------------------------------------------------------


def test_engine_com_pre_ping_timeout_e_utc(engine):
    assert engine.pool._pre_ping is True
    with engine.connect() as connection:
        assert connection.dialect.driver == "psycopg"
        assert connection.exec_driver_sql("SHOW TimeZone").scalar() == "UTC"
        dsn = connection.connection.dbapi_connection.info.get_parameters()
    assert dsn["connect_timeout"] == str(CONNECT_TIMEOUT_SECONDS)


def test_url_sem_driver_usa_psycopg(database_url):
    plain = make_url(database_url).set(drivername="postgresql")
    engine = create_db_engine(plain.render_as_string(hide_password=False))
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_get_session_entrega_sessao_do_banco_das_settings(settings: Settings, session):
    user = add_user(session, "via-dependencia")
    session.commit()

    app = create_app(settings)

    @app.get("/_users/{username}")
    def read_user(username: str, db: Session = Depends(get_session)):  # noqa: B008
        return {"id": str(db.scalar(select(User.id).where(User.username == username)))}

    with TestClient(app) as client:
        response = client.get("/_users/via-dependencia")
    assert response.status_code == 200
    assert response.json() == {"id": str(user.id)}
