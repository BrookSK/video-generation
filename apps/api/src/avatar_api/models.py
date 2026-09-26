import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

VOICES = ("masculina", "feminina")
PREPARE_STATUSES = ("preparando", "ativo", "falha")
ORIGINS = ("panel", "api")
ASPECT_RATIOS = ("9:16", "16:9")
QUEUE_STATUSES = ("queued", "processing", "ready", "failed")
JOB_STAGES = ("waiting", "compose", "tts", "render", "finalize", "upload")
ATTEMPT_OUTCOMES = ("running", "completed", "failed", "expired")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True), dict[str, Any]: JSONB}


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def _fk(target: str, nullable: bool = False) -> Mapped[Any]:
    return mapped_column(ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _id()
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    disabled_at: Mapped[datetime | None]


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    csrf_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = _id()
    prefix: Mapped[str] = mapped_column(Text, unique=True)
    key_hash: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = _fk("users.id")
    created_at: Mapped[datetime] = _created_at()
    revoked_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    )

    id: Mapped[uuid.UUID] = _id()
    relative_path: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = _created_at()


class RenderRecipe(Base):
    __tablename__ = "render_recipes"
    __table_args__ = (
        CheckConstraint("max_script_chars > 0", name="max_script_chars"),
        Index(
            "uq_render_recipes_current",
            "is_current",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(Text, unique=True)
    max_script_chars: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict[str, Any]]
    is_current: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()


class Avatar(Base):
    __tablename__ = "avatars"
    __table_args__ = (
        CheckConstraint(_in("voice", VOICES), name="voice"),
        CheckConstraint(_in("prepare_status", PREPARE_STATUSES), name="prepare_status"),
    )

    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(Text)
    voice: Mapped[str] = mapped_column(Text)
    source_file_id: Mapped[uuid.UUID] = _fk("stored_files.id")
    prepared_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    preview_9x16_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    preview_16x9_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    prepare_status: Mapped[str] = mapped_column(Text, server_default=text("'preparando'"))
    prepare_error: Mapped[str | None] = mapped_column(Text)
    authorized_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    authorized_at: Mapped[datetime | None]
    archived_at: Mapped[datetime | None]
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _created_at()


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(background_file_id, background_color) = 1", name="one_background"
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(Text)
    background_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    background_color: Mapped[str | None] = mapped_column(Text)
    composition: Mapped[dict[str, Any]]
    preview_9x16_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    preview_16x9_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    archived_at: Mapped[datetime | None]
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _created_at()


class VideoJob(Base):
    __tablename__ = "video_jobs"
    __table_args__ = (
        CheckConstraint(_in("origin", ORIGINS), name="origin"),
        CheckConstraint(
            "(origin = 'panel' AND requested_by_user_id IS NOT NULL AND api_key_id IS NULL)"
            " OR (origin = 'api' AND api_key_id IS NOT NULL AND requested_by_user_id IS NULL)",
            name="requester_matches_origin",
        ),
        CheckConstraint("char_length(idempotency_key) <= 128", name="idempotency_key_length"),
        CheckConstraint(_in("voice", VOICES), name="voice"),
        CheckConstraint(_in("aspect_ratio", ASPECT_RATIOS), name="aspect_ratio"),
        CheckConstraint(_in("status", QUEUE_STATUSES), name="status"),
        CheckConstraint(_in("stage", JOB_STAGES), name="stage"),
        CheckConstraint("attempt >= 0", name="attempt"),
        CheckConstraint("lease_generation >= 0", name="lease_generation"),
        CheckConstraint("status <> 'ready' OR result_file_id IS NOT NULL", name="ready_has_file"),
        Index(
            "uq_video_jobs_idempotency_api_key",
            "api_key_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("api_key_id IS NOT NULL AND idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_video_jobs_idempotency_user",
            "requested_by_user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text(
                "requested_by_user_id IS NOT NULL AND idempotency_key IS NOT NULL"
            ),
        ),
        Index("ix_video_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    origin: Mapped[str] = mapped_column(Text)
    requested_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    api_key_id: Mapped[uuid.UUID | None] = _fk("api_keys.id", nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    request_hash: Mapped[str | None] = mapped_column(Text)
    script_text: Mapped[str] = mapped_column(Text)
    avatar_id: Mapped[uuid.UUID] = _fk("avatars.id")
    avatar_file_id: Mapped[uuid.UUID] = _fk("stored_files.id")
    scene_id: Mapped[uuid.UUID] = _fk("scenes.id")
    scene_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    voice: Mapped[str] = mapped_column(Text)
    aspect_ratio: Mapped[str] = mapped_column(Text)
    recipe_id: Mapped[uuid.UUID] = _fk("render_recipes.id")
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    stage: Mapped[str] = mapped_column(Text, server_default=text("'waiting'"))
    attempt: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    lease_until: Mapped[datetime | None]
    lease_generation: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    current_attempt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    worker_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    result_file_id: Mapped[uuid.UUID | None] = _fk("stored_files.id", nullable=True)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number"),
        CheckConstraint("attempt_number >= 1", name="attempt_number"),
        CheckConstraint(_in("outcome", ATTEMPT_OUTCOMES), name="outcome"),
        CheckConstraint("peak_vram_mb >= 0", name="peak_vram_mb"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[uuid.UUID] = _fk("video_jobs.id")
    attempt_number: Mapped[int] = mapped_column(Integer)
    lease_generation: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(Text)
    claimed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_heartbeat_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    outcome: Mapped[str] = mapped_column(Text, server_default=text("'running'"))
    stage_timings: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    peak_vram_mb: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class AssetPrepareTask(Base):
    __tablename__ = "asset_prepare_tasks"
    __table_args__ = (
        CheckConstraint(_in("status", QUEUE_STATUSES), name="status"),
        CheckConstraint("attempt >= 0", name="attempt"),
        CheckConstraint("lease_generation >= 0", name="lease_generation"),
        Index("ix_asset_prepare_tasks_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    avatar_id: Mapped[uuid.UUID] = _fk("avatars.id")
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    attempt: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    lease_until: Mapped[datetime | None]
    lease_generation: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    current_attempt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    worker_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
