"""aulas e identidade visual

Acrescenta brand_identity (linha única), lessons, lesson_scenes e lesson_assemble_tasks, e
em video_jobs as colunas lesson_id, lesson_position e shot. Aditiva: jobs existentes ficam
avulsos, em plano médio.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUEUE_STATUSES = "status IN ('queued', 'processing', 'ready', 'failed')"
SHOTS = "shot IN ('medio', 'close')"
HEX_COLOR = "~ '^#[0-9A-Fa-f]{6}$'"


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
        "brand_identity",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        _uuid("logo_file_id"),
        _text("background_color"),
        _text("accent_color"),
        _uuid("music_file_id", nullable=True),
        _uuid("updated_by_user_id"),
        _ts("updated_at", nullable=False, now=True),
        _ck("brand_identity", "single_row", "id = 1"),
        _ck("brand_identity", "background_color", f"background_color {HEX_COLOR}"),
        _ck("brand_identity", "accent_color", f"accent_color {HEX_COLOR}"),
        _fk("brand_identity", "logo_file_id", "stored_files"),
        _fk("brand_identity", "music_file_id", "stored_files"),
        _fk("brand_identity", "updated_by_user_id", "users"),
        _pk("brand_identity"),
    )

    op.create_table(
        "lessons",
        _id(),
        _uuid("requested_by_user_id"),
        _text("idempotency_key", nullable=True),
        _text("request_hash", nullable=True),
        _uuid("avatar_id"),
        _uuid("scene_id"),
        _text("aspect_ratio"),
        sa.Column("music_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _uuid("logo_file_id"),
        _text("background_color"),
        _text("accent_color"),
        _uuid("music_file_id", nullable=True),
        _text("status", default="'queued'"),
        _uuid("result_file_id", nullable=True),
        _text("error_code", nullable=True),
        _text("error_message", nullable=True),
        _created_at(),
        _ts("finished_at"),
        _ck("lessons", "aspect_ratio", "aspect_ratio IN ('9:16', '16:9')"),
        _ck("lessons", "status", "status IN ('queued', 'assembling', 'ready', 'failed')"),
        _ck("lessons", "idempotency_key_length", "char_length(idempotency_key) <= 128"),
        _ck("lessons", "background_color", f"background_color {HEX_COLOR}"),
        _ck("lessons", "accent_color", f"accent_color {HEX_COLOR}"),
        _ck("lessons", "ready_has_file", "status <> 'ready' OR result_file_id IS NOT NULL"),
        _fk("lessons", "requested_by_user_id", "users"),
        _fk("lessons", "avatar_id", "avatars"),
        _fk("lessons", "scene_id", "scenes"),
        _fk("lessons", "logo_file_id", "stored_files"),
        _fk("lessons", "music_file_id", "stored_files"),
        _fk("lessons", "result_file_id", "stored_files"),
        _pk("lessons"),
    )
    op.create_index("ix_lessons_created_at", "lessons", ["created_at"])
    op.create_index(
        "uq_lessons_idempotency_user",
        "lessons",
        ["requested_by_user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column("video_jobs", _uuid("lesson_id", nullable=True))
    op.add_column("video_jobs", _int("lesson_position", nullable=True))
    op.add_column("video_jobs", _text("shot", default="'medio'"))
    op.create_foreign_key(
        op.f("fk_video_jobs_lesson_id_lessons"),
        "video_jobs",
        "lessons",
        ["lesson_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(op.f("ck_video_jobs_shot"), "video_jobs", SHOTS)
    op.create_check_constraint(
        op.f("ck_video_jobs_lesson_position_with_lesson"),
        "video_jobs",
        "(lesson_id IS NULL) = (lesson_position IS NULL)",
    )
    op.create_unique_constraint(
        op.f("uq_video_jobs_lesson_id_lesson_position"),
        "video_jobs",
        ["lesson_id", "lesson_position"],
    )

    op.create_table(
        "lesson_scenes",
        _id(),
        _uuid("lesson_id"),
        _int("position"),
        _text("script_text"),
        _text("shot"),
        sa.Column("topics", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        _uuid("image_file_id", nullable=True),
        _uuid("video_job_id"),
        _ck("lesson_scenes", "position", "position BETWEEN 1 AND 12"),
        _ck("lesson_scenes", "shot", SHOTS),
        _fk("lesson_scenes", "lesson_id", "lessons"),
        _fk("lesson_scenes", "image_file_id", "stored_files"),
        _fk("lesson_scenes", "video_job_id", "video_jobs"),
        _pk("lesson_scenes"),
        _uq("lesson_scenes", "lesson_id", "position"),
        _uq("lesson_scenes", "video_job_id"),
    )

    op.create_table(
        "lesson_assemble_tasks",
        _id(),
        _uuid("lesson_id"),
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
        _ck("lesson_assemble_tasks", "status", QUEUE_STATUSES),
        _ck("lesson_assemble_tasks", "attempt", "attempt >= 0"),
        _ck("lesson_assemble_tasks", "lease_generation", "lease_generation >= 0"),
        _fk("lesson_assemble_tasks", "lesson_id", "lessons"),
        _pk("lesson_assemble_tasks"),
        _uq("lesson_assemble_tasks", "lesson_id"),
    )
    op.create_index(
        "ix_lesson_assemble_tasks_status_created_at",
        "lesson_assemble_tasks",
        ["status", "created_at"],
    )


def downgrade() -> None:
    # A ordem respeita as FKs: tabelas filhas, colunas de video_jobs e só então lessons.
    op.drop_table("lesson_assemble_tasks")
    op.drop_table("lesson_scenes")
    op.drop_constraint(op.f("fk_video_jobs_lesson_id_lessons"), "video_jobs", type_="foreignkey")
    for column in ("shot", "lesson_position", "lesson_id"):
        op.drop_column("video_jobs", column)
    op.drop_table("lessons")
    op.drop_table("brand_identity")
