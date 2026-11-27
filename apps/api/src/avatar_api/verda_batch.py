"""Dispatch queued videos to a single-replica Verda Batch Job deployment."""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from avatar_api.db import create_db_engine
from avatar_api.jobs import _mark_failed
from avatar_api.models import VerdaBatchDispatch, VideoJob
from avatar_api.verda import NoRedirect, VerdaError

LOG = logging.getLogger(__name__)
LOCK_ID = 0x4156415441524254
TASKS = "https://tasks.verda.com"
MAX_LAUNCHES_PER_VIDEO = 3
REJECTED = {400, 401, 403, 404, 422, 429}


class Batch:
    def __init__(self, deployment: str, token: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", deployment) or not token:
            raise ValueError("Invalid Verda Batch deployment or token")
        self.deployment = deployment
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def call(self, method: str, path: str, dispatch_id: UUID, body: dict | None = None):
        request = urllib.request.Request(
            TASKS + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-Inference-Id": str(dispatch_id),
            },
            method=method,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise VerdaError(None)
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise VerdaError(exc.code) from None
        except (OSError, ValueError):
            raise VerdaError(None) from None

    def submit(self, dispatch: VerdaBatchDispatch) -> None:
        result = self.call(
            "POST",
            f"/{self.deployment}/render",
            dispatch.dispatch_id,
            {"dispatch_id": str(dispatch.dispatch_id), "job_id": str(dispatch.video_id)},
        )
        if not isinstance(result, dict) or result.get("Id") != str(dispatch.dispatch_id):
            raise VerdaError(None)

    def finished(self, dispatch: VerdaBatchDispatch) -> bool:
        try:
            result = self.call("GET", f"/result/{self.deployment}", dispatch.dispatch_id)
        except VerdaError as exc:
            if exc.status in {202, 404, 409, 425}:
                return False
            raise
        return isinstance(result, dict) and result.get("dispatch_id") == str(dispatch.dispatch_id)


def selected_video(
    session: Session, worker_id: str, dispatch_id: UUID | None, job_id: UUID | None
) -> UUID | None:
    if dispatch_id is None or job_id is None:
        return None
    row = session.get(VerdaBatchDispatch, worker_id, with_for_update=True)
    if (
        row is not None
        and row.dispatch_id == dispatch_id
        and row.video_id == job_id
        and row.phase in {"pending", "submitted"}
        and row.expires_at > session.scalar(select(func.now()))
    ):
        row.phase = "claimed"
        return job_id
    return None


def reconcile(session: Session, worker: str, provider: Batch, horizon: timedelta):
    now = session.scalar(select(func.now()))
    row = session.get(VerdaBatchDispatch, worker, with_for_update=True)
    if row and now < row.expires_at:
        if row.phase != "cooldown":
            session.commit()
            if provider.finished(row):
                row.phase = "cooldown"
                row.expires_at = now + timedelta(seconds=60)
                session.commit()
        return
    if session.scalar(select(VideoJob.id).where(VideoJob.status == "processing").limit(1)):
        return
    video = session.scalar(
        select(VideoJob)
        .where(VideoJob.status == "queued")
        .order_by(
            VideoJob.created_at,
            VideoJob.id,
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if video is None:
        return
    launches = row.launches if row and row.video_id == video.id else 0
    if launches >= MAX_LAUNCHES_PER_VIDEO:
        _mark_failed(
            session,
            video,
            "VERDA_BATCH_EXHAUSTED",
            "O lote Verda não entregou o vídeo após três envios.",
        )
        session.commit()
        return
    if row is None:
        row = VerdaBatchDispatch(worker_id=worker)
        session.add(row)
    row.dispatch_id = uuid4()
    row.video_id = video.id
    row.launches = launches + 1
    row.submitted_at = now
    row.expires_at = now + horizon
    row.phase = "pending"
    session.commit()
    LOG.info("Submitting batch %s for video %s", row.dispatch_id, row.video_id)
    try:
        provider.submit(row)
    except VerdaError as exc:
        if exc.status in REJECTED:
            row = session.get(
                VerdaBatchDispatch, worker, populate_existing=True, with_for_update=True
            )
            if row.phase == "pending":
                row.phase = "cooldown"
                row.expires_at = now + timedelta(minutes=5)
                session.commit()
        # A lost response is reconciled using the original ID, never by a second POST.
        raise
    row = session.get(VerdaBatchDispatch, worker, populate_existing=True, with_for_update=True)
    if row.phase == "pending":
        row.phase = "submitted"
    session.commit()


def run_once(engine, worker: str, provider: Batch, horizon: timedelta):
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID})
        connection.commit()
        if not acquired:
            return
        try:
            with Session(connection, expire_on_commit=False) as session:
                reconcile(session, worker, provider, horizon)
        finally:
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
                connection.commit()
            except Exception:
                connection.invalidate()
                raise


def main():
    logging.basicConfig(level=logging.INFO)
    worker = os.environ["VERDA_WORKER_ID"]
    provider = Batch(os.environ["VERDA_BATCH_DEPLOYMENT"], os.environ["VERDA_BATCH_TOKEN"])
    horizon = int(os.environ["VERDA_BATCH_HORIZON_SECONDS"])
    if horizon < 600 or not worker.strip():
        raise ValueError("Batch horizon must cover provider queue TTL plus execution deadline")
    engine = create_db_engine(os.environ["DATABASE_URL"])
    while True:
        try:
            run_once(engine, worker, provider, timedelta(seconds=horizon))
        except Exception as exc:
            LOG.error("Verda Batch reconciliation failed: %s", type(exc).__name__)
        time.sleep(10)


if __name__ == "__main__":
    main()
