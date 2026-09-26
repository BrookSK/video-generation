"""API pública /api/v1, autenticada por chave de API em todas as rotas."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from avatar_api import assets
from avatar_api.auth import CurrentApiKey, DbSession, require_api_key
from avatar_api.errors import ApiError
from avatar_api.jobs import IDEMPOTENCY_KEY_MAX_CHARS, JobRequester, NewVideoJob, create_video_job
from avatar_api.models import Avatar, Scene, StoredFile, VideoJob
from avatar_api.storage import resolve_path

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])

IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=1, max_length=IDEMPOTENCY_KEY_MAX_CHARS)
]
JobStatus = Literal["queued", "processing", "ready", "failed"]
AspectRatio = Annotated[Literal["9:16", "16:9"], Query()]


class JobCreatedOut(BaseModel):
    id: uuid.UUID
    status: JobStatus
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


def _urls(job: VideoJob) -> tuple[str, str | None]:
    status_url = f"/api/v1/jobs/{job.id}"
    return status_url, f"{status_url}/download" if job.status == "ready" else None


def _job_created_out(job: VideoJob) -> JobCreatedOut:
    status_url, download_url = _urls(job)
    return JobCreatedOut(
        id=job.id, status=job.status, status_url=status_url, download_url=download_url
    )


def _job_out(job: VideoJob) -> JobOut:
    status_url, download_url = _urls(job)
    error = None
    if job.status == "failed":
        error = JobErrorOut(code=job.error_code or "", message=job.error_message or "")
    return JobOut(
        id=job.id,
        status=job.status,
        stage=job.stage if job.status == "processing" else None,
        aspect_ratio=job.aspect_ratio,
        created_at=job.created_at,
        finished_at=job.finished_at,
        error=error,
        status_url=status_url,
        download_url=download_url,
    )


def _own_job(db: DbSession, key: CurrentApiKey, job_id: uuid.UUID) -> VideoJob:
    # Job de outra chave responde igual a job inexistente: 404 sem revelar que existe.
    job = db.scalar(select(VideoJob).where(VideoJob.id == job_id, VideoJob.api_key_id == key.id))
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Job não encontrado.")
    return job


@router.post("/jobs", status_code=202)
def create_job(
    body: NewVideoJob,
    key: CurrentApiKey,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> JobCreatedOut:
    # create_video_job só volta depois do commit: nenhum 202 sai com o job fora do banco.
    job = create_video_job(db, JobRequester(origin="api", api_key_id=key.id), body, idempotency_key)
    return _job_created_out(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, key: CurrentApiKey, db: DbSession) -> JobOut:
    return _job_out(_own_job(db, key, job_id))


@router.get("/jobs/{job_id}/download")
def download_job(
    job_id: uuid.UUID, key: CurrentApiKey, db: DbSession, request: Request
) -> FileResponse:
    job = _own_job(db, key, job_id)
    if job.status == "failed":
        raise ApiError(409, "JOB_FAILED", f"O job falhou: {job.error_code}: {job.error_message}")
    if job.status != "ready":
        raise ApiError(
            409, "JOB_NOT_READY", f"O vídeo ainda não está pronto. Status atual: {job.status}."
        )
    stored = db.get(StoredFile, job.result_file_id)
    path = resolve_path(request.app.state.settings.data_dir, stored)
    return FileResponse(path, media_type=stored.content_type, filename=f"video-{job.id}.mp4")


# --- avatares e cenários ----------------------------------------------------------------
# Só o que a criação de job aceita; sem id de arquivo, caminho do volume ou autorização.


class PublicAvatarOut(BaseModel):
    id: uuid.UUID
    name: str
    voice: str
    preview_url: str | None
    created_at: datetime


class PublicSceneOut(BaseModel):
    id: uuid.UUID
    name: str
    preview_url: str | None
    created_at: datetime


class AvatarListOut(BaseModel):
    items: list[PublicAvatarOut]


class SceneListOut(BaseModel):
    items: list[PublicSceneOut]


def _preview_url(prefix: str, item: Avatar | Scene) -> str | None:
    return f"/api/v1/{prefix}/{item.id}/preview" if item.preview_9x16_file_id else None


def _preview_response(path: Path, stored: StoredFile) -> FileResponse:
    return FileResponse(path, media_type=stored.content_type, headers={"Cache-Control": "private"})


@router.get("/avatars")
def list_avatars(db: DbSession) -> AvatarListOut:
    return AvatarListOut(
        items=[
            PublicAvatarOut(
                id=avatar.id,
                name=avatar.name,
                voice=avatar.voice,
                preview_url=_preview_url("avatars", avatar),
                created_at=avatar.created_at,
            )
            for avatar in assets.list_public_avatars(db)
        ]
    )


@router.get("/scenes")
def list_scenes(db: DbSession) -> SceneListOut:
    return SceneListOut(
        items=[
            PublicSceneOut(
                id=scene.id,
                name=scene.name,
                preview_url=_preview_url("scenes", scene),
                created_at=scene.created_at,
            )
            for scene in assets.list_public_scenes(db)
        ]
    )


@router.get("/avatars/{avatar_id}/preview")
def avatar_preview(
    avatar_id: uuid.UUID, db: DbSession, request: Request, aspect_ratio: AspectRatio = "9:16"
) -> FileResponse:
    data_dir = request.app.state.settings.data_dir
    return _preview_response(
        *assets.public_preview(db, data_dir, "avatar", avatar_id, aspect_ratio)
    )


@router.get("/scenes/{scene_id}/preview")
def scene_preview(
    scene_id: uuid.UUID, db: DbSession, request: Request, aspect_ratio: AspectRatio = "9:16"
) -> FileResponse:
    data_dir = request.app.state.settings.data_dir
    return _preview_response(*assets.public_preview(db, data_dir, "scene", scene_id, aspect_ratio))
