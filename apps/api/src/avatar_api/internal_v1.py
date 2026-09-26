"""API interna /internal/v1, usada só pelo worker e autenticada pelo WORKER_TOKEN."""

import hmac
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from avatar_api import jobs
from avatar_api.auth import DbSession
from avatar_api.errors import ApiError
from avatar_api.jobs import AssetPreparePayload, ProcessingStage, QueueKind, VideoPayload


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
