"""API interna /internal/v1, usada só pelo worker e autenticada pelo WORKER_TOKEN."""

import hmac
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, Field

from avatar_api import jobs
from avatar_api.auth import DbSession
from avatar_api.errors import ApiError
from avatar_api.jobs import (
    AssetPreparePayload,
    AttemptFileName,
    ProcessingStage,
    QueueItem,
    QueueKind,
    VideoPayload,
)


def require_worker(request: Request) -> None:
    """Aceita só `Authorization: Bearer <WORKER_TOKEN>`; sem token configurado, a API interna
    fica desligada (503) em vez de aceitar um token vazio."""
    expected = request.app.state.settings.worker_token
    if not expected:
        raise ApiError(
            503, "SERVICE_UNAVAILABLE", "API interna desativada: WORKER_TOKEN não configurado."
        )
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    token_ok = hmac.compare_digest(token.encode(), expected.encode())
    if scheme.lower() != "bearer" or not token_ok:
        raise ApiError(401, "UNAUTHORIZED", "Token de worker ausente ou inválido.")


router = APIRouter(prefix="/internal/v1", dependencies=[Depends(require_worker)])


class ClaimIn(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)
    kinds: list[QueueKind] = Field(min_length=1)


class ClaimOut(BaseModel):
    kind: QueueKind
    id: uuid.UUID
    attempt_id: uuid.UUID
    lease_generation: int
    lease_until: datetime
    heartbeat_interval_seconds: int
    payload: VideoPayload | AssetPreparePayload


class AttemptRef(BaseModel):
    attempt_id: uuid.UUID
    lease_generation: int


class VideoHeartbeatIn(AttemptRef):
    stage: ProcessingStage | None = None


class HeartbeatOut(BaseModel):
    lease_until: datetime


@router.post("/claim", response_model=ClaimOut, responses={204: {"description": "Fila vazia."}})
def claim(body: ClaimIn, db: DbSession, request: Request):
    settings = request.app.state.settings
    claimed = jobs.claim_next(db, body.worker_id, body.kinds, settings.lease_seconds)
    if claimed is None:
        db.rollback()
        return Response(status_code=204)
    db.commit()
    return ClaimOut(
        kind=claimed.kind,
        id=claimed.id,
        attempt_id=claimed.attempt_id,
        lease_generation=claimed.lease_generation,
        lease_until=claimed.lease_until,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        payload=claimed.payload,
    )


@router.post("/jobs/{job_id}/heartbeat")
def job_heartbeat(
    job_id: uuid.UUID, body: VideoHeartbeatIn, db: DbSession, request: Request
) -> HeartbeatOut:
    lease_until = jobs.heartbeat(
        db,
        "video",
        job_id,
        body.attempt_id,
        body.lease_generation,
        request.app.state.settings.lease_seconds,
        body.stage,
    )
    return HeartbeatOut(lease_until=lease_until)


@router.post("/asset-tasks/{task_id}/heartbeat")
def asset_task_heartbeat(
    task_id: uuid.UUID, body: AttemptRef, db: DbSession, request: Request
) -> HeartbeatOut:
    lease_until = jobs.heartbeat(
        db,
        "asset_prepare",
        task_id,
        body.attempt_id,
        body.lease_generation,
        request.app.state.settings.lease_seconds,
    )
    return HeartbeatOut(lease_until=lease_until)


# --- publicação -----------------------------------------------------------------------


class AttemptFileOut(BaseModel):
    id: uuid.UUID
    name: str
    size_bytes: int
    sha256: str
    content_type: str


class VideoCompleteIn(AttemptRef):
    result_file_id: uuid.UUID
    stage_timings: dict[str, float] = Field(default_factory=dict)
    peak_vram_mb: int | None = Field(default=None, ge=0)


class CompleteOut(BaseModel):
    id: uuid.UUID
    status: str
    finished_at: datetime | None
    result_file_id: uuid.UUID | None = None


class FailIn(AttemptRef):
    error_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    error_message: str = Field(min_length=1, max_length=2000)
    retryable: bool


class FailOut(BaseModel):
    id: uuid.UUID
    status: str
    attempt: int


@router.put("/jobs/{job_id}/attempts/{attempt_id}/files/{name}")
def upload_attempt_file(
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    name: AttemptFileName,
    file: Annotated[UploadFile, File()],
    sha256: Annotated[str, Form(pattern=r"^[0-9a-fA-F]{64}$")],
    lease_generation: Annotated[int, Form()],
    db: DbSession,
    request: Request,
    response: Response,
) -> AttemptFileOut:
    settings = request.app.state.settings
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Arquivo maior que o permitido.", "file")
    stored, created = jobs.save_attempt_file(
        db, settings.data_dir, job_id, attempt_id, lease_generation, name, file.file, sha256
    )
    response.status_code = 201 if created else 200
    return AttemptFileOut(
        id=stored.id,
        name=stored.name,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        content_type=stored.content_type,
    )


def _complete_out(item: QueueItem) -> CompleteOut:
    return CompleteOut(
        id=item.id,
        status=item.status,
        finished_at=item.finished_at,
        result_file_id=getattr(item, "result_file_id", None),
    )


def _fail(kind: QueueKind, item_id: uuid.UUID, body: FailIn, db: DbSession) -> FailOut:
    item = jobs.fail_item(
        db,
        kind,
        item_id,
        body.attempt_id,
        body.lease_generation,
        body.error_code,
        body.error_message,
        body.retryable,
    )
    return FailOut(id=item.id, status=item.status, attempt=item.attempt)


@router.post("/jobs/{job_id}/complete")
def job_complete(
    job_id: uuid.UUID, body: VideoCompleteIn, db: DbSession, request: Request
) -> CompleteOut:
    job = jobs.complete_item(
        db,
        "video",
        job_id,
        body.attempt_id,
        body.lease_generation,
        request.app.state.settings.data_dir,
        result_file_id=body.result_file_id,
        stage_timings=body.stage_timings,
        peak_vram_mb=body.peak_vram_mb,
    )
    return _complete_out(job)


@router.post("/jobs/{job_id}/fail")
def job_fail(job_id: uuid.UUID, body: FailIn, db: DbSession) -> FailOut:
    return _fail("video", job_id, body, db)


@router.post("/asset-tasks/{task_id}/complete")
def asset_task_complete(
    task_id: uuid.UUID, body: AttemptRef, db: DbSession, request: Request
) -> CompleteOut:
    task = jobs.complete_item(
        db,
        "asset_prepare",
        task_id,
        body.attempt_id,
        body.lease_generation,
        request.app.state.settings.data_dir,
    )
    return _complete_out(task)


@router.post("/asset-tasks/{task_id}/fail")
def asset_task_fail(task_id: uuid.UUID, body: FailIn, db: DbSession) -> FailOut:
    return _fail("asset_prepare", task_id, body, db)
