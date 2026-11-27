"""One-request HTTP entry point for a Verda Batch Jobs replica."""

import fcntl
import hashlib
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from collections.abc import Mapping
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from avatar_worker.manifest import _load_checked, pull


def seed_cache(manifest: Path, models: Path) -> None:
    models.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    marker = models / f".estudioia-{digest}"
    with (models / ".estudioia-cache.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if marker.is_file():
            return
        policy = _load_checked(manifest)
        if policy is None:
            raise ValueError("Model manifest rejected")
        pull(policy, models)
        marker.touch()


def run_video(env: Mapping[str, str], dispatch_id: str, job_id: str) -> bool:
    from avatar_worker.supervisor import Supervisor, load_config

    config = load_config(env)
    seed_cache(config.video_runtime.manifest_path, config.video_runtime.models_dir)
    with httpx.Client(
        base_url=config.api_url,
        headers={"Authorization": f"Bearer {config.token}"},
        timeout=60,
        trust_env=False,
    ) as client:
        return Supervisor(config, client).process_next(dispatch_id=dispatch_id, job_id=job_id)


class BatchServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, port: int, config: Mapping[str, str]):
        self.config = config
        self.render_lock = threading.Lock()
        self.exit_code = 1
        super().__init__(("0.0.0.0", port), BatchHandler)


class BatchHandler(BaseHTTPRequestHandler):
    server: BatchServer

    def reply(self, status: int, result: dict) -> None:
        body = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_GET(self) -> None:
        self.reply(200 if urlsplit(self.path).path == "/health" else 404, {})

    def do_POST(self) -> None:
        if not self.server.render_lock.acquire(blocking=False):
            self.reply(409, {})
            return
        try:
            self.run_job()
        finally:
            self.server.shutdown()

    def run_job(self) -> None:
        dispatch_id = None
        try:
            if urlsplit(self.path).path != "/render":
                self.reply(404, {"dispatch_id": None})
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError
            request = json.loads(self.rfile.read(size))
            dispatch_id = str(UUID(request["dispatch_id"]))
            job_id = str(UUID(request["job_id"]))
        except (TypeError, ValueError, KeyError, AttributeError):
            self.reply(400, {"dispatch_id": dispatch_id})
            return
        try:
            completed = run_video(self.server.config, dispatch_id, job_id)
        except Exception as exc:
            logging.error("Verda batch failed: %s", type(exc).__name__)
            self.reply(500, {"dispatch_id": dispatch_id})
            return
        self.reply(200 if completed else 409, {"dispatch_id": dispatch_id})
        self.server.exit_code = 0 if completed else 1

    def log_message(self, format, *args):
        # Only structured worker diagnostics are emitted.
        pass


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    config = os.environ.copy()
    if config.get("WORKER_KINDS") != "video":
        raise ValueError("Batch replicas accept only video jobs")
    with BatchServer(int(os.getenv("PORT", "8000")), config) as server:
        server.serve_forever(poll_interval=0.1)
        return server.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
