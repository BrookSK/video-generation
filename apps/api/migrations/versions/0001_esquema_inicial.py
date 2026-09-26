"""esquema inicial

Cria as dez tabelas do ciclo: users, sessions, api_keys, stored_files, render_recipes,
avatars, scenes, video_jobs, job_attempts e asset_prepare_tasks.

Revision ID: 0001
Revises:
Create Date: 2026-09-26 11:08:05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "render_recipes",
    "stored_files",
    "users",
    "api_keys",
    "avatars",
    "scenes",
    "sessions",
    "asset_prepare_tasks",
    "video_jobs",
    "job_attempts",
)

QUEUE_STATUSES = "status IN ('queued', 'processing', 'ready', 'failed')"
VOICES = "voice IN ('masculina', 'feminina')"


def _id(name: str = "id") -> sa.Column:
    return sa.Column(name, sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str, nullable: bool = True, now: bool = False) -> sa.Column:
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _created_at() -> sa.Column:
    return _ts("created_at", nullable=False, now=True)


def _text(name: str, nullable: bool = False, default: str | None = None) -> sa.Column:
    server_default = sa.text(default) if default is not None else None
    return sa.Column(name, sa.Text(), server_default=server_default, nullable=nullable)


def _uuid(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _int(name: str, default: str | None = None, nullable: bool = False) -> sa.Column:
    server_default = sa.text(default) if default is not None else None
    return sa.Column(name, sa.Integer(), server_default=server_default, nullable=nullable)


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.id"],
        name=op.f(f"fk_{table}_{column}_{target}"),
        ondelete="RESTRICT",
    )


def _ck(table: str, name: str, condition: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def _pk(table: str, column: str = "id") -> sa.PrimaryKeyConstraint:
    return sa.PrimaryKeyConstraint(column, name=op.f(f"pk_{table}"))


def _uq(table: str, *columns: str) -> sa.UniqueConstraint:
    return sa.UniqueConstraint(*columns, name=op.f(f"uq_{table}_{'_'.join(columns)}"))


def upgrade() -> None:
    op.create_table(
        "render_recipes",
        _id(),
        _text("name"),
        _int("max_script_chars"),
        sa.Column("spec", JSONB(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _created_at(),
        _ck("render_recipes", "max_script_chars", "max_script_chars > 0"),
        _pk("render_recipes"),
        _uq("render_recipes", "name"),
    )
    op.create_index(
        "uq_render_recipes_current",
        "render_recipes",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "stored_files",
        _id(),
        _text("relative_path"),
        _text("name"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        _text("sha256"),
        _text("content_type"),
        _uuid("attempt_id", nullable=True),
        _created_at(),
        _ck("stored_files", "sha256", "sha256 ~ '^[0-9a-f]{64}$'"),
        _ck("stored_files", "size_bytes", "size_bytes >= 0"),
        _pk("stored_files"),
        _uq("stored_files", "relative_path"),
    )

    op.create_table(
        "users",
        _id(),
        _text("username"),
        _text("password_hash"),
        _created_at(),
        _ts("disabled_at"),
        _pk("users"),
        _uq("users", "username"),
    )

    op.create_table(
        "api_keys",
        _id(),
        _text("prefix"),
        _text("key_hash"),
        _text("description"),
        _uuid("created_by_user_id"),
        _created_at(),
        _ts("revoked_at"),
        _ts("last_used_at"),
        _fk("api_keys", "created_by_user_id", "users"),
        _pk("api_keys"),
        _uq("api_keys", "prefix"),
    )

    op.create_table(
        "avatars",
        _id(),
        _text("name"),
        _text("voice"),
        _uuid("source_file_id"),
        _uuid("prepared_file_id", nullable=True),
        _uuid("preview_9x16_file_id", nullable=True),
        _uuid("preview_16x9_file_id", nullable=True),
        _text("prepare_status", default="'preparando'"),
        _text("prepare_error", nullable=True),
        _uuid("authorized_by_user_id", nullable=True),
        _ts("authorized_at"),
        _ts("archived_at"),
        _uuid("created_by_user_id", nullable=True),
        _created_at(),
        _ck(
            "avatars",
            "prepare_status",
            "prepare_status IN ('preparando', 'ativo', 'falha')",
        ),
        _ck("avatars", "voice", VOICES),
        _fk("avatars", "authorized_by_user_id", "users"),
        _fk("avatars", "created_by_user_id", "users"),
        _fk("avatars", "prepared_file_id", "stored_files"),
        _fk("avatars", "preview_16x9_file_id", "stored_files"),
        _fk("avatars", "preview_9x16_file_id", "stored_files"),
        _fk("avatars", "source_file_id", "stored_files"),
        _pk("avatars"),
    )

    op.create_table(
        "scenes",
        _id(),
        _text("name"),
        _uuid("background_file_id", nullable=True),
        _text("background_color", nullable=True),
        sa.Column("composition", JSONB(), nullable=False),
        _uuid("preview_9x16_file_id", nullable=True),
        _uuid("preview_16x9_file_id", nullable=True),
        _ts("archived_at"),
        _uuid("created_by_user_id", nullable=True),
        _created_at(),
        _ck(
            "scenes",
            "one_background",
            "num_nonnulls(background_file_id, background_color) = 1",
        ),
        _fk("scenes", "background_file_id", "stored_files"),
        _fk("scenes", "created_by_user_id", "users"),
        _fk("scenes", "preview_16x9_file_id", "stored_files"),
        _fk("scenes", "preview_9x16_file_id", "stored_files"),
        _pk("scenes"),
    )

    op.create_table(
        "sessions",
        _id(),
        _uuid("user_id"),
        _text("token_hash"),
        _text("csrf_hash"),
        _created_at(),
        _ts("expires_at", nullable=False),
        _ts("revoked_at"),
        _fk("sessions", "user_id", "users"),
        _pk("sessions"),
        _uq("sessions", "token_hash"),
    )

    op.create_table(
        "asset_prepare_tasks",
        _id(),
        _uuid("avatar_id"),
        _text("status", default="'queued'"),
        _int("attempt", default="0"),
        _ts("lease_until"),
        _int("lease_generation", default="0"),
        _uuid("current_attempt_id", nullable=True),
        _text("worker_id", nullable=True),
        _text("error_code", nullable=True),
        _text("error_message", nullable=True),
        _created_at(),
        _ts("started_at"),
        _ts("finished_at"),
        _ck("asset_prepare_tasks", "status", QUEUE_STATUSES),
        _ck("asset_prepare_tasks", "attempt", "attempt >= 0"),
        _ck("asset_prepare_tasks", "lease_generation", "lease_generation >= 0"),
        _fk("asset_prepare_tasks", "avatar_id", "avatars"),
        _pk("asset_prepare_tasks"),
    )
    op.create_index(
        "ix_asset_prepare_tasks_status_created_at",
        "asset_prepare_tasks",
        ["status", "created_at"],
    )

    op.create_table(
        "video_jobs",
        _id(),
        _text("origin"),
        _uuid("requested_by_user_id", nullable=True),
        _uuid("api_key_id", nullable=True),
        _text("idempotency_key", nullable=True),
        _text("request_hash", nullable=True),
        _text("script_text"),
        _uuid("avatar_id"),
        _uuid("avatar_file_id"),
        _uuid("scene_id"),
        _uuid("scene_file_id", nullable=True),
        _text("voice"),
        _text("aspect_ratio"),
        _uuid("recipe_id"),
        _text("status", default="'queued'"),
        _text("stage", default="'waiting'"),
        _int("attempt", default="0"),
        _ts("lease_until"),
        _int("lease_generation", default="0"),
        _uuid("current_attempt_id", nullable=True),
        _text("worker_id", nullable=True),
        _text("error_code", nullable=True),
        _text("error_message", nullable=True),
        _uuid("result_file_id", nullable=True),
        _created_at(),
        _ts("started_at"),
        _ts("finished_at"),
        _ck(
            "video_jobs",
            "requester_matches_origin",
            "(origin = 'panel' AND requested_by_user_id IS NOT NULL AND api_key_id IS NULL)"
            " OR (origin = 'api' AND api_key_id IS NOT NULL AND requested_by_user_id IS NULL)",
        ),
        _ck("video_jobs", "aspect_ratio", "aspect_ratio IN ('9:16', '16:9')"),
        _ck("video_jobs", "origin", "origin IN ('panel', 'api')"),
        _ck(
            "video_jobs",
            "stage",
            "stage IN ('waiting', 'compose', 'tts', 'render', 'finalize', 'upload')",
        ),
        _ck("video_jobs", "ready_has_file", "status <> 'ready' OR result_file_id IS NOT NULL"),
        _ck("video_jobs", "status", QUEUE_STATUSES),
        _ck("video_jobs", "voice", VOICES),
        _ck("video_jobs", "attempt", "attempt >= 0"),
        _ck("video_jobs", "idempotency_key_length", "char_length(idempotency_key) <= 128"),
        _ck("video_jobs", "lease_generation", "lease_generation >= 0"),
        _fk("video_jobs", "api_key_id", "api_keys"),
        _fk("video_jobs", "avatar_file_id", "stored_files"),
        _fk("video_jobs", "avatar_id", "avatars"),
        _fk("video_jobs", "recipe_id", "render_recipes"),
        _fk("video_jobs", "requested_by_user_id", "users"),
        _fk("video_jobs", "result_file_id", "stored_files"),
        _fk("video_jobs", "scene_file_id", "stored_files"),
        _fk("video_jobs", "scene_id", "scenes"),
        _pk("video_jobs"),
    )
    op.create_index("ix_video_jobs_status_created_at", "video_jobs", ["status", "created_at"])
    op.create_index(
        "uq_video_jobs_idempotency_api_key",
        "video_jobs",
        ["api_key_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("api_key_id IS NOT NULL AND idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_video_jobs_idempotency_user",
        "video_jobs",
        ["requested_by_user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text(
            "requested_by_user_id IS NOT NULL AND idempotency_key IS NOT NULL"
        ),
    )

    op.create_table(
        "job_attempts",
        _id("attempt_id"),
        _uuid("job_id"),
        _int("attempt_number"),
        _int("lease_generation"),
        _text("worker_id"),
        _ts("claimed_at", nullable=False, now=True),
        _ts("last_heartbeat_at"),
        _ts("finished_at"),
        _text("outcome", default="'running'"),
        sa.Column("stage_timings", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        _int("peak_vram_mb", nullable=True),
        _text("error_code", nullable=True),
        _text("error_message", nullable=True),
        _ck(
            "job_attempts",
            "outcome",
            "outcome IN ('running', 'completed', 'failed', 'expired')",
        ),
        _ck("job_attempts", "attempt_number", "attempt_number >= 1"),
        _ck("job_attempts", "peak_vram_mb", "peak_vram_mb >= 0"),
        _fk("job_attempts", "job_id", "video_jobs"),
        _pk("job_attempts", "attempt_id"),
        _uq("job_attempts", "job_id", "attempt_number"),
    )


def downgrade() -> None:
    # Remover a tabela remove junto seus índices e restrições; a ordem respeita as FKs.
    for table in reversed(TABLES):
        op.drop_table(table)
