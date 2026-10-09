"""Supervisor: reivindica vídeo/preparação, mantém lease e publica na API interna.

Uso: python -m avatar_worker.supervisor

Lê API_URL (padrão http://api:8000), WORKER_TOKEN (obrigatório), WORKER_ID (padrão o
hostname), WORKER_KINDS (padrão asset_prepare) e POLL_SECONDS (padrão 3). Cada tarefa tem
heartbeat numa thread própria; STALE_ATTEMPT ou lease vencido marcam a tentativa como
perdida, e dali em diante nada é enviado nem publicado. Erro de rede repete com backoff de
1 a 30 s. SIGTERM encerra depois do item atual. Os logs trazem só task_id, etapa e código,
além da linha de início com o worker_id e os tipos reivindicados.
"""

import hashlib
import json
import logging
import os
import signal
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from avatar_worker.asset_prepare import PrepareInputError, prepare_avatar
from avatar_worker.cutout import CutoutError
from avatar_worker.video import GenerationFailure, VideoRuntime, file_sha256, generate_video

logger = logging.getLogger("avatar_worker.supervisor")

SUPPORTED_KINDS = ("video", "asset_prepare")
# Arquivo da tentativa -> campo do complete da preparação.
RESULT_FIELDS = {
    "prepared.png": "prepared_file_id",
    "preview-9x16.png": "preview_9x16_file_id",
    "preview-16x9.png": "preview_16x9_file_id",
}
BACKOFF_MIN_S = 1.0
BACKOFF_MAX_S = 30.0
RETRY_STATUS = frozenset({502, 503, 504})
REQUEST_TIMEOUT_S = 60.0
CUTOUT_UNAVAILABLE_MESSAGE = "O recorte automático não está disponível no worker."
PREPARE_ERROR_MESSAGE = "Falha inesperada ao preparar o avatar."

Wait = Callable[[float, threading.Event], Any]
Now = Callable[[], datetime]


class ConfigError(ValueError):
    """Configuração do supervisor inválida; o processo encerra com código 2."""


class StaleAttempt(Exception):
    """A tentativa foi perdida (409 ou lease vencido): nada mais é enviado por ela."""


class Stopped(Exception):
    """Parada pedida enquanto a API estava fora, antes de reivindicar um item."""


class ApiStatusError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Config:
    api_url: str
    token: str
    worker_id: str
    kinds: tuple[str, ...]
    poll_seconds: float
    video_runtime: VideoRuntime = VideoRuntime()


def load_config(env: Mapping[str, str]) -> Config:
    token = env.get("WORKER_TOKEN", "")
    if not token:
        raise ConfigError("WORKER_TOKEN não definido.")
    raw_kinds = env.get("WORKER_KINDS", "asset_prepare")
    kinds = tuple(kind.strip() for kind in raw_kinds.split(",") if kind.strip())
    if not kinds or set(kinds) - set(SUPPORTED_KINDS):
        raise ConfigError(f"WORKER_KINDS aceita só: {', '.join(SUPPORTED_KINDS)}.")
    try:
        poll_seconds = float(env.get("POLL_SECONDS", "3"))
    except ValueError as exc:
        raise ConfigError("POLL_SECONDS precisa ser um número.") from exc
    return Config(
        api_url=env.get("API_URL", "http://api:8000"),
        token=token,
        worker_id=env.get("WORKER_ID") or socket.gethostname(),
        kinds=kinds,
        poll_seconds=poll_seconds,
        video_runtime=VideoRuntime.from_env(env),
    )


def _log(level: int, task_id: str, stage: str, code: str) -> None:
    logger.log(level, "task_id=%s etapa=%s codigo=%s", task_id, stage, code)


def _error_code(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return f"HTTP_{response.status_code}"


@dataclass(frozen=True)
class Task:
    id: str
    attempt_id: str
    lease_generation: int
    lease_until: datetime
    heartbeat_interval: float
    kind: str
    payload: Mapping[str, Any]

    @classmethod
    def from_claim(cls, data: Mapping[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            attempt_id=data["attempt_id"],
            lease_generation=data["lease_generation"],
            lease_until=datetime.fromisoformat(data["lease_until"]),
            heartbeat_interval=float(data["heartbeat_interval_seconds"]),
            kind=data["kind"],
            payload=data["payload"],
        )

    @property
    def base_path(self) -> str:
        queue = "jobs" if self.kind == "video" else "asset-tasks"
        return f"/internal/v1/{queue}/{self.id}"

    @property
    def ref(self) -> dict[str, Any]:
        return {"attempt_id": self.attempt_id, "lease_generation": self.lease_generation}


class Heartbeat:
    """Renova o lease numa thread própria e marca a tentativa perdida em 409 ou lease vencido."""

    def __init__(self, client: httpx.Client, task: Task, now: Now) -> None:
        self.lost = threading.Event()
        self._client = client
        self._task = task
        self._now = now
        self._lease_until = task.lease_until
        self._done = threading.Event()
        self._stage: str | None = None
        self._renew_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{task.id}", daemon=True)

    def __enter__(self) -> "Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._done.set()
        self._thread.join()

    def mark_lost(self) -> None:
        if not self.lost.is_set():
            self.lost.set()
            _log(logging.WARNING, self._task.id, "heartbeat", "STALE_ATTEMPT")

    def check(self) -> None:
        """Levanta StaleAttempt se a tentativa foi perdida ou o lease venceu sem renovação."""
        if self._now() >= self._lease_until:
            self.mark_lost()
        if self.lost.is_set():
            raise StaleAttempt

    def set_stage(self, stage: str) -> None:
        """Serializa heartbeat de etapa e periódico: etapa antiga nunca sobrescreve a nova."""
        with self._renew_lock:
            self._stage = stage
            self._renew()

    def _renew(self) -> None:
        self.check()
        body = self._task.ref
        if self._task.kind == "video" and self._stage is not None:
            body["stage"] = self._stage
        try:
            response = self._client.post(f"{self._task.base_path}/heartbeat", json=body)
        except httpx.TransportError:
            response = None
        if response is not None and response.status_code == 409:
            self.mark_lost()
        elif response is not None and response.is_success:
            self._lease_until = datetime.fromisoformat(response.json()["lease_until"])
        self.check()

    def _run(self) -> None:
        while not self._done.wait(self._task.heartbeat_interval) and not self.lost.is_set():
            try:
                with self._renew_lock:
                    self._renew()
            except StaleAttempt:
                return


class Supervisor:
    def __init__(
        self,
        config: Config,
        client: httpx.Client,
        prepare: Callable[[bytes], Mapping[str, bytes]] = prepare_avatar,
        wait: Wait | None = None,
        now: Now | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._prepare = prepare
        self._wait = wait or (lambda seconds, interrupt: interrupt.wait(seconds))
        self._now = now or (lambda: datetime.now(UTC))
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """Processa itens até a parada pedida, sempre terminando o item em andamento."""
        while not self._stop.is_set():
            try:
                worked = self.process_next()
            except Stopped:
                break
            if not worked:
                self._wait(self._config.poll_seconds, self._stop)

    def process_next(self) -> bool:
        """Reivindica e processa um item; devolve False se não havia item para processar."""
        body = {"worker_id": self._config.worker_id, "kinds": list(self._config.kinds)}
        response = self._call("POST", "/internal/v1/claim", json=body)
        if response.status_code == 204:
            return False
        if not response.is_success:
            _log(logging.WARNING, "-", "claim", _error_code(response))
            return False
        task = Task.from_claim(response.json())
        _log(logging.INFO, task.id, "claim", "OK")
        with Heartbeat(self._client, task, self._now) as heartbeat:
            try:
                if task.kind == "video":
                    self._handle_video(task, heartbeat)
                else:
                    self._handle(task, heartbeat)
            except StaleAttempt:
                _log(logging.WARNING, task.id, "publicacao", "STALE_ATTEMPT")
        return True

    def _handle_video(self, task: Task, heartbeat: Heartbeat) -> None:
        def set_stage(stage: str) -> None:
            heartbeat.set_stage(stage)
            _log(logging.INFO, task.id, stage, "OK")

        try:
            with tempfile.TemporaryDirectory(
                prefix=f"avatar-video-{task.attempt_id}-"
            ) as temporary:
                work = Path(temporary)
                set_stage("compose")
                inputs = {"avatar": work / "avatar.png"}
                self._download_path(
                    task, heartbeat, task.payload["avatar_file_id"], inputs["avatar"]
                )
                if task.payload["scene_file_id"] is not None:
                    inputs["background"] = work / "background"
                    self._download_path(
                        task, heartbeat, task.payload["scene_file_id"], inputs["background"]
                    )
                result = generate_video(
                    task.payload,
                    inputs,
                    work,
                    self._config.video_runtime,
                    heartbeat.check,
                    set_stage,
                )
                heartbeat.check()
                set_stage("upload")
                manifest = json.loads(result.files["manifest.json"].read_text())
                manifest.update(
                    job_id=task.id,
                    attempt_id=task.attempt_id,
                    lease_generation=task.lease_generation,
                    attempt_directory=f"jobs/{task.id}/{task.attempt_id}",
                )
                result.files["manifest.json"].write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                started = time.monotonic()
                # Primeiro a lista de arquivos da tentativa, para rastrear uploads órfãos.
                file_ids = {}
                for name in ("manifest.json", "audio.wav", "render.mp4", "final.mp4"):
                    file_ids[name] = self._upload_path(task, heartbeat, result.files[name])
                timings = {**result.stage_timings, "upload": time.monotonic() - started}
                response = self._call(
                    "POST",
                    f"{task.base_path}/complete",
                    heartbeat,
                    json={
                        **task.ref,
                        "result_file_id": file_ids["final.mp4"],
                        "stage_timings": timings,
                        "peak_vram_mb": result.peak_vram_mb,
                    },
                )
                if not response.is_success:
                    raise GenerationFailure("OUTPUT_INVALID", "A publicação do vídeo foi recusada.")
        except StaleAttempt:
            raise
        except GenerationFailure as exc:
            self._fail(task, heartbeat, exc.code, exc.message, exc.retryable)
        except Exception:
            self._fail(task, heartbeat, "TRANSIENT", "Falha temporária no worker de geração.", True)
        else:
            _log(logging.INFO, task.id, "complete", "OK")

    def _download_path(
        self, task: Task, heartbeat: Heartbeat, file_id: str, destination: Path
    ) -> None:
        delay = BACKOFF_MIN_S
        while True:
            heartbeat.check()
            try:
                with self._client.stream("GET", f"/internal/v1/files/{file_id}") as response:
                    heartbeat.check()
                    if response.status_code in RETRY_STATUS:
                        response = None
                    elif not response.is_success:
                        response.read()
                        if response.status_code == 409 and _error_code(response) == "STALE_ATTEMPT":
                            heartbeat.mark_lost()
                            raise StaleAttempt
                        raise GenerationFailure(
                            "INPUT_INVALID", "O arquivo do avatar ou cenário não está disponível."
                        )
                    else:
                        with destination.open("wb") as target:
                            for block in response.iter_bytes(chunk_size=1 << 20):
                                heartbeat.check()
                                target.write(block)
                        heartbeat.check()
                        return
            except httpx.TransportError:
                pass
            self._wait(delay, heartbeat.lost)
            heartbeat.check()
            delay = min(delay * 2, BACKOFF_MAX_S)

    def _upload_path(self, task: Task, heartbeat: Heartbeat, path: Path) -> str:
        content_type = {
            "manifest.json": "application/json",
            "audio.wav": "audio/wav",
            "render.mp4": "video/mp4",
            "final.mp4": "video/mp4",
        }[path.name]
        digest = file_sha256(path, heartbeat.check)
        response = self._call(
            "PUT",
            f"{task.base_path}/attempts/{task.attempt_id}/files/{path.name}",
            heartbeat,
            upload_path=path,
            upload_type=content_type,
            data={"sha256": digest, "lease_generation": str(task.lease_generation)},
        )
        if not response.is_success:
            raise GenerationFailure("OUTPUT_INVALID", "Não foi possível enviar o arquivo gerado.")
        heartbeat.check()
        return response.json()["id"]

    def _handle(self, task: Task, heartbeat: Heartbeat) -> None:
        base = f"/internal/v1/asset-tasks/{task.id}"
        try:
            source = self._download(task, heartbeat)
            files = self._prepare(source)
            file_ids = {
                RESULT_FIELDS[name]: self._upload(task, heartbeat, name, data)
                for name, data in files.items()
            }
            response = self._call(
                "POST", f"{base}/complete", heartbeat, json={**task.ref, **file_ids}
            )
            if not response.is_success:
                raise ApiStatusError(_error_code(response))
        except StaleAttempt:
            raise
        except PrepareInputError as exc:
            self._fail(task, heartbeat, "INVALID_SOURCE", str(exc), retryable=False)
        except CutoutError:
            self._fail(
                task, heartbeat, "CUTOUT_UNAVAILABLE", CUTOUT_UNAVAILABLE_MESSAGE, retryable=False
            )
        except Exception:
            self._fail(task, heartbeat, "PREPARE_ERROR", PREPARE_ERROR_MESSAGE, retryable=True)
        else:
            _log(logging.INFO, task.id, "complete", "OK")

    def _download(self, task: Task, heartbeat: Heartbeat) -> bytes:
        file_id = task.payload["source_file_id"]
        response = self._call("GET", f"/internal/v1/files/{file_id}", heartbeat)
        if response.status_code == 404:
            raise PrepareInputError("A imagem de origem não está disponível.")
        if not response.is_success:
            raise ApiStatusError(_error_code(response))
        _log(logging.INFO, task.id, "download", "OK")
        return response.content

    def _upload(self, task: Task, heartbeat: Heartbeat, name: str, data: bytes) -> str:
        response = self._call(
            "PUT",
            f"/internal/v1/asset-tasks/{task.id}/attempts/{task.attempt_id}/files/{name}",
            heartbeat,
            files={"file": (name, data, "image/png")},
            data={
                "sha256": hashlib.sha256(data).hexdigest(),
                "lease_generation": str(task.lease_generation),
            },
        )
        if not response.is_success:
            raise ApiStatusError(_error_code(response))
        _log(logging.INFO, task.id, f"upload {name}", "OK")
        return response.json()["id"]

    def _fail(
        self, task: Task, heartbeat: Heartbeat, code: str, message: str, retryable: bool
    ) -> None:
        body = {**task.ref, "error_code": code, "error_message": message, "retryable": retryable}
        path = f"{task.base_path}/fail"
        response = self._call("POST", path, heartbeat, json=body)
        _log(
            logging.WARNING, task.id, "fail", code if response.is_success else _error_code(response)
        )

    def _call(
        self,
        method: str,
        path: str,
        heartbeat: Heartbeat | None = None,
        upload_path: Path | None = None,
        upload_type: str = "application/octet-stream",
        **kwargs: Any,
    ) -> httpx.Response:
        """Faz a chamada repetindo erro de rede com backoff de 1 a 30 s.

        Com heartbeat, confere tentativa antes/depois do envio e trata só STALE_ATTEMPT como
        StaleAttempt; sem ele (claim), a parada pedida interrompe a espera com Stopped.
        """
        interrupt = heartbeat.lost if heartbeat else self._stop
        delay = BACKOFF_MIN_S
        while True:
            if heartbeat:
                heartbeat.check()
            try:
                if upload_path is None:
                    response = self._client.request(method, path, **kwargs)
                else:
                    # Cada retry começa em um descritor novo; nunca reaproveitar stream consumido.
                    with upload_path.open("rb") as stream:
                        response = self._client.request(
                            method,
                            path,
                            files={"file": (upload_path.name, stream, upload_type)},
                            **kwargs,
                        )
            except httpx.TransportError:
                response = None
            if response is not None and response.status_code not in RETRY_STATUS:
                if (
                    heartbeat
                    and response.status_code == 409
                    and _error_code(response) == "STALE_ATTEMPT"
                ):
                    heartbeat.mark_lost()
                    raise StaleAttempt
                if heartbeat:
                    heartbeat.check()
                return response
            _log(logging.WARNING, "-", f"{method} rede", "RETRY")
            self._wait(delay, interrupt)
            if interrupt.is_set():
                raise StaleAttempt if heartbeat else Stopped
            delay = min(delay * 2, BACKOFF_MAX_S)


def main(env: Mapping[str, str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(os.environ if env is None else env)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    logger.info("inicio worker_id=%s tipos=%s", config.worker_id, ",".join(config.kinds))
    headers = {"Authorization": f"Bearer {config.token}"}
    with httpx.Client(
        base_url=config.api_url,
        headers=headers,
        timeout=REQUEST_TIMEOUT_S,
        trust_env=False,
    ) as client:
        supervisor = Supervisor(config, client)
        signal.signal(signal.SIGTERM, lambda *_: supervisor.request_stop())
        supervisor.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
