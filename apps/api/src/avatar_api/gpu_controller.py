"""Consume the video queue with a single disposable Verda instance."""

import logging
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from avatar_api.db import create_db_engine
from avatar_api.models import GpuLifecycle, VideoJob, WorkerHeartbeat
from avatar_api.verda import Verda, VerdaError

LOG = logging.getLogger(__name__)
LOCK_ID = 0x4156415441524750
ACTIVE_PHASES = {"starting", "ready"}


@dataclass(frozen=True)
class Policy:
    worker_id: str
    instance_type: str
    location: str
    volume_id: UUID
    ssh_key_id: UUID
    boot_timeout: timedelta
    idle_timeout: timedelta
    max_runtime: timedelta
    max_launches_per_hour: int
    spot: bool = False

    @classmethod
    def from_env(cls):
        policy = cls(
            worker_id=os.environ["VERDA_WORKER_ID"],
            instance_type=os.environ["VERDA_INSTANCE_TYPE"],
            location=os.environ["VERDA_LOCATION"],
            volume_id=UUID(os.environ["VERDA_BOOT_VOLUME_ID"]),
            ssh_key_id=UUID(os.environ["VERDA_SSH_KEY_ID"]),
            boot_timeout=timedelta(seconds=int(os.getenv("VERDA_BOOT_TIMEOUT_SECONDS", "900"))),
            idle_timeout=timedelta(seconds=int(os.getenv("VERDA_IDLE_SECONDS", "60"))),
            max_runtime=timedelta(seconds=int(os.environ["VERDA_MAX_RUNTIME_SECONDS"])),
            max_launches_per_hour=int(os.getenv("VERDA_MAX_LAUNCHES_PER_HOUR", "1")),
            spot=os.getenv("VERDA_SPOT") == "true",
        )
        if (
            not policy.worker_id.strip()
            or not timedelta(0) < policy.idle_timeout < policy.boot_timeout < policy.max_runtime
            or policy.max_launches_per_hour < 1
        ):
            raise ValueError("Invalid Verda worker identity or time limits")
        return policy


def video_enabled(session: Session, configured_worker: str, request_worker: str) -> bool:
    if request_worker != configured_worker:
        return False
    gpu = session.get(GpuLifecycle, configured_worker, with_for_update=True)
    return gpu is not None and gpu.phase in ACTIVE_PHASES


def queue_has(session: Session, status: str) -> bool:
    return bool(session.scalar(select(exists().where(VideoJob.status == status))))


def clear_instance(gpu, retry_at=None):
    gpu.phase = "cooldown" if retry_at else "idle"
    gpu.retry_at = retry_at
    gpu.hostname = None
    gpu.instance_id = None
    gpu.volume_id = None
    gpu.started_at = None
    gpu.idle_since = None


def identified_instance(gpu, instance):
    return (
        isinstance(instance, dict)
        and instance.get("hostname") == gpu.hostname
        and instance.get("os_volume_id") == str(gpu.volume_id)
        and (gpu.instance_id is None or instance.get("id") == str(gpu.instance_id))
    )


def launch(session: Session, gpu: GpuLifecycle, policy: Policy, verda: Verda, now):
    if gpu.window_started_at is None or now - gpu.window_started_at >= timedelta(hours=1):
        gpu.window_started_at = now
        gpu.launches = 0
    if gpu.launches >= policy.max_launches_per_hour:
        clear_instance(gpu, retry_at=gpu.window_started_at + timedelta(hours=1))
        session.commit()
        return

    # Reconcile a restored DB or an operator-created VM before spending on another instance.
    session.commit()
    if verda.volume_in_use(policy.volume_id):
        LOG.error("Configured Verda boot volume is already attached; creation skipped")
        clear_instance(gpu, retry_at=now + timedelta(minutes=5))
        return
    gpu.phase = "starting"
    gpu.hostname = f"estudioia-{uuid4().hex}"
    gpu.volume_id = policy.volume_id
    gpu.started_at = now
    gpu.launches += 1
    session.commit()
    LOG.info("Creating GPU %s", gpu.hostname)

    # The intent survives a crash or an ambiguous POST. Only reconcile that hostname.
    try:
        created = verda.create(
            gpu.hostname,
            policy.instance_type,
            policy.location,
            gpu.volume_id,
            policy.ssh_key_id,
            policy.spot,
        )
    except VerdaError as exc:
        if exc.status in {400, 401, 402, 403, 404, 422}:
            clear_instance(gpu, retry_at=now + timedelta(minutes=5))
            session.commit()
        raise
    instance_id = created.get("id") if isinstance(created, dict) else created
    if isinstance(instance_id, str):
        gpu.instance_id = UUID(instance_id)
        session.commit()


def locate(gpu: GpuLifecycle, verda: Verda):
    instance = verda.get(gpu.instance_id) if gpu.instance_id else verda.find(gpu.hostname)
    if instance is None:
        return None
    if not identified_instance(gpu, instance):
        LOG.error("Verda instance identity does not match the journal entry for %s", gpu.hostname)
        raise VerdaError(None)
    return instance


def reconcile(session: Session, policy: Policy, verda: Verda):
    gpu = session.get(GpuLifecycle, policy.worker_id, with_for_update=True)
    if gpu is None:
        gpu = GpuLifecycle(worker_id=policy.worker_id, phase="idle", launches=0)
        session.add(gpu)
    now = session.scalar(select(func.now()))

    if gpu.phase == "cooldown" and now >= gpu.retry_at:
        clear_instance(gpu)
    if gpu.phase in {"idle", "cooldown"}:
        if (
            gpu.phase == "idle"
            and queue_has(session, "queued")
            and not queue_has(session, "processing")
        ):
            launch(session, gpu, policy, verda, now)
        session.commit()
        return

    # Release the row lock before reaching the provider, then obtain a new queue snapshot.
    session.commit()
    instance = locate(gpu, verda)
    gpu = session.get(GpuLifecycle, policy.worker_id, populate_existing=True, with_for_update=True)
    since_start = now - gpu.started_at
    if instance is None:
        if gpu.instance_id and (gpu.phase != "starting" or since_start >= policy.boot_timeout):
            LOG.info("GPU %s absent at Verda", gpu.hostname)
            retry_at = gpu.retry_at if gpu.retry_at and gpu.retry_at > now else None
            clear_instance(gpu, retry_at=retry_at)
        elif gpu.phase != "unknown" and since_start >= policy.boot_timeout:
            gpu.phase = "unknown"
            LOG.warning("Unconfirmed GPU creation for %s; looking for the same VM", gpu.hostname)
        session.commit()
        return

    gpu.instance_id = UUID(instance["id"])
    if gpu.phase == "unknown":
        gpu.phase = "starting"

    heartbeat = session.get(WorkerHeartbeat, policy.worker_id)
    if gpu.phase == "starting" and heartbeat and heartbeat.last_heartbeat_at >= gpu.started_at:
        gpu.phase = "ready"

    # Once the phase is stopping, the claim endpoint will not give this VM more jobs.
    runtime_exceeded = since_start >= policy.max_runtime
    processing = queue_has(session, "processing")
    queued = queue_has(session, "queued")
    last_seen = heartbeat.last_heartbeat_at if heartbeat else gpu.started_at
    worker_lost = (
        gpu.phase == "ready"
        and queued
        and not processing
        and (now - last_seen >= policy.boot_timeout)
    )
    if (
        runtime_exceeded
        or worker_lost
        or (gpu.phase == "starting" and since_start >= policy.boot_timeout)
    ):
        gpu.phase = "stopping"
        gpu.retry_at = gpu.retry_at or now + timedelta(minutes=5)
    if gpu.phase == "ready":
        if processing or queued:
            gpu.idle_since = None
        else:
            gpu.idle_since = gpu.idle_since or now
            if now - gpu.idle_since >= policy.idle_timeout:
                gpu.phase = "stopping"

    stop = gpu.phase == "stopping" and (runtime_exceeded or not processing)
    session.commit()
    if stop and str(instance.get("status", "")).lower() != "deleting":
        LOG.info("Deleting GPU %s and retaining its boot volume", gpu.hostname)
        verda.delete(gpu.instance_id)


def run_once(engine, policy: Policy, verda: Verda):
    # A transaction row lock arbitrates claims. The session lock arbitrates provider calls,
    # including calls between transactions. Closing the connection releases both after crashes.
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID})
        connection.commit()
        if not acquired:
            return
        try:
            with Session(connection, expire_on_commit=False) as session:
                reconcile(session, policy, verda)
        finally:
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
                connection.commit()
            except Exception:
                connection.invalidate()
                raise


def main():
    logging.basicConfig(level=logging.INFO)
    policy = Policy.from_env()
    engine = create_db_engine(os.environ["DATABASE_URL"])
    verda = Verda(os.environ["VERDA_CLIENT_ID"], os.environ["VERDA_CLIENT_SECRET"])
    while True:
        try:
            run_once(engine, policy, verda)
        except Exception as exc:
            if isinstance(exc, VerdaError):
                LOG.error("GPU controller reconciliation failed: %s", exc)
            else:
                LOG.error("GPU controller reconciliation failed: %s", type(exc).__name__)
        time.sleep(10)


if __name__ == "__main__":
    main()
