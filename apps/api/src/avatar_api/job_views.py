"""Representação e entrega de mídia comuns ao painel e à API pública."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from avatar_api.errors import ApiError
from avatar_api.jobs import IDEMPOTENCY_KEY_MAX_CHARS
from avatar_api.models import StoredFile, VideoJob
from avatar_api.storage import resolve_path

IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=1, max_length=IDEMPOTENCY_KEY_MAX_CHARS)
]


class JobCreatedOut(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "processing", "ready", "failed"]
    status_url: str
    download_url: str | None


class JobErrorOut(BaseModel):
    code: str
    message: str


class JobOut(JobCreatedOut):
    stage: str | None
    aspect_ratio: str
    created_at: datetime
    finished_at: datetime | None
    error: JobErrorOut | None


class WorkerStatusOut(BaseModel):
    last_heartbeat_at: datetime | None


def job_created_out(job: VideoJob, prefix: str) -> JobCreatedOut:
    status_url = f"{prefix}/jobs/{job.id}"
    return JobCreatedOut(
        id=job.id,
        status=job.status,
        status_url=status_url,
        download_url=f"{status_url}/download" if job.status == "ready" else None,
    )


def job_out(job: VideoJob, prefix: str) -> JobOut:
    error = None
    if job.status == "failed":
        error = JobErrorOut(code=job.error_code or "", message=job.error_message or "")
    return JobOut(
        **job_created_out(job, prefix).model_dump(),
        stage=job.stage if job.status == "processing" else None,
        aspect_ratio=job.aspect_ratio,
        created_at=job.created_at,
        finished_at=job.finished_at,
        error=error,
    )


def download_response(db: Session, job: VideoJob, data_dir: Path) -> FileResponse:
    if job.status == "failed":
        raise ApiError(409, "JOB_FAILED", f"O job falhou: {job.error_code}: {job.error_message}")
    if job.status != "ready":
        raise ApiError(
            409, "JOB_NOT_READY", f"O vídeo ainda não está pronto. Status atual: {job.status}."
        )
    stored = db.get(StoredFile, job.result_file_id)
    path = resolve_path(data_dir, stored) if stored else None
    if path is None or not path.is_file():
        raise ApiError(404, "NOT_FOUND", "O arquivo do vídeo não está disponível.")
    return FileResponse(
        path,
        media_type=stored.content_type,
        filename=f"video-{job.id}.mp4",
        headers={"Cache-Control": "private"},
    )
