"""API pública /api/v1, autenticada por chave de API em todas as rotas."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from avatar_api.auth import CurrentApiKey, DbSession, require_api_key
from avatar_api.jobs import IDEMPOTENCY_KEY_MAX_CHARS, JobRequester, NewVideoJob, create_video_job
from avatar_api.models import VideoJob

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])

IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=1, max_length=IDEMPOTENCY_KEY_MAX_CHARS)
]


class JobCreatedOut(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "processing", "ready", "failed"]
    status_url: str
    download_url: str | None


def _job_created_out(job: VideoJob) -> JobCreatedOut:
    status_url = f"/api/v1/jobs/{job.id}"
    return JobCreatedOut(
        id=job.id,
        status=job.status,
        status_url=status_url,
        download_url=f"{status_url}/download" if job.status == "ready" else None,
    )


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
