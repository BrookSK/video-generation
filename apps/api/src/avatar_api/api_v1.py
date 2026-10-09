"""API pública /api/v1, autenticada por chave de API em todas as rotas."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from avatar_api import assets
from avatar_api.auth import CurrentApiKey, DbSession, require_api_key
from avatar_api.errors import ApiError
from avatar_api.job_views import (
    IdempotencyKey,
    JobCreatedOut,
    JobOut,
    WorkerStatusOut,
    download_response,
    job_created_out,
    job_out,
)
from avatar_api.jobs import (
    JobRequester,
    NewVideoJob,
    create_video_job,
    last_video_worker_heartbeat,
)
from avatar_api.models import Avatar, Scene, StoredFile, VideoJob


class PublicErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    field: str | None = None


class PublicErrorOut(BaseModel):
    error: PublicErrorDetail


router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
    responses={
        401: {"model": PublicErrorOut, "description": "Chave de API ausente ou inválida."},
        404: {"model": PublicErrorOut, "description": "Recurso não encontrado ou de outra chave."},
        409: {
            "model": PublicErrorOut,
            "description": "Conflito de intenção ou vídeo indisponível.",
        },
        422: {"model": PublicErrorOut, "description": "Dados inválidos ou fala acima do limite."},
        500: {"model": PublicErrorOut, "description": "Erro interno."},
        503: {"model": PublicErrorOut, "description": "Banco ou receita vigente indisponível."},
    },
)

AspectRatio = Annotated[Literal["9:16", "16:9"], Query()]


@router.get("/worker-status")
def worker_status(db: DbSession) -> WorkerStatusOut:
    return WorkerStatusOut(last_heartbeat_at=last_video_worker_heartbeat(db))


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
    return job_created_out(job, "/api/v1")


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, key: CurrentApiKey, db: DbSession) -> JobOut:
    return job_out(_own_job(db, key, job_id), "/api/v1")


@router.get(
    "/jobs/{job_id}/download",
    response_class=FileResponse,
    responses={
        200: {"content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}}}},
        206: {
            "description": "Intervalo solicitado por Range.",
            "content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}}},
        },
        416: {"description": "Intervalo Range fora do arquivo."},
    },
)
def download_job(
    job_id: uuid.UUID, key: CurrentApiKey, db: DbSession, request: Request
) -> FileResponse:
    return download_response(db, _own_job(db, key, job_id), request.app.state.settings.data_dir)


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


@router.get(
    "/avatars/{avatar_id}/preview",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
def avatar_preview(
    avatar_id: uuid.UUID, db: DbSession, request: Request, aspect_ratio: AspectRatio = "9:16"
) -> FileResponse:
    data_dir = request.app.state.settings.data_dir
    return _preview_response(
        *assets.public_preview(db, data_dir, "avatar", avatar_id, aspect_ratio)
    )


@router.get(
    "/scenes/{scene_id}/preview",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
def scene_preview(
    scene_id: uuid.UUID, db: DbSession, request: Request, aspect_ratio: AspectRatio = "9:16"
) -> FileResponse:
    data_dir = request.app.state.settings.data_dir
    return _preview_response(*assets.public_preview(db, data_dir, "scene", scene_id, aspect_ratio))
