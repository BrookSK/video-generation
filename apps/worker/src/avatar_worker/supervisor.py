"""Supervisor do worker: reivindica tarefas na API interna, prepara o avatar e publica.

Uso: python -m avatar_worker.supervisor

Lê API_URL (padrão http://api:8000), WORKER_TOKEN (obrigatório), WORKER_ID (padrão o
hostname), WORKER_KINDS (padrão asset_prepare) e POLL_SECONDS (padrão 3). Cada tarefa tem
heartbeat numa thread própria; 409 ou lease vencido sem renovação marcam a tentativa como
perdida, e dali em diante nada é enviado nem publicado. Erro de rede repete com backoff de
1 a 30 s. SIGTERM encerra depois do item atual. Os logs trazem só task_id, etapa e código.
"""

import hashlib
import logging
import os
import signal
import socket
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from avatar_worker.asset_prepare import PrepareInputError, prepare_avatar
from avatar_worker.cutout import CutoutError

logger = logging.getLogger("avatar_worker.supervisor")

SUPPORTED_KINDS = ("asset_prepare",)
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


def load_config(env: Mapping[str, str]) -> Config:
    token = env.get("WORKER_TOKEN", "")
    if not token:
        raise ConfigError("WORKER_TOKEN não definido.")
    raw_kinds = env.get("WORKER_KINDS", "asset_prepare")
    kinds = tuple(kind.strip() for kind in raw_kinds.split(",") if kind.strip())
    if "video" in kinds:
        raise ConfigError("WORKER_KINDS=video não é aceito: o estágio de vídeo chega na P04.")
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
    source_file_id: str

    @classmethod
    def from_claim(cls, data: Mapping[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            attempt_id=data["attempt_id"],
            lease_generation=data["lease_generation"],
            lease_until=datetime.fromisoformat(data["lease_until"]),
            heartbeat_interval=float(data["heartbeat_interval_seconds"]),
            source_file_id=data["payload"]["source_file_id"],
        )

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

    def _run(self) -> None:
        path = f"/internal/v1/asset-tasks/{self._task.id}/heartbeat"
        while not self._done.wait(self._task.heartbeat_interval) and not self.lost.is_set():
            try:
                response = self._client.post(path, json=self._task.ref)
            except httpx.TransportError:
                response = None
            if response is not None and response.status_code == 409:
                self.mark_lost()
            elif response is not None and response.is_success:
                self._lease_until = datetime.fromisoformat(response.json()["lease_until"])
            elif self._now() >= self._lease_until:
                self.mark_lost()


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
                self._handle(task, heartbeat)
            except StaleAttempt:
                _log(logging.WARNING, task.id, "publicacao", "STALE_ATTEMPT")
        return True

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
        response = self._call("GET", f"/internal/v1/files/{task.source_file_id}", heartbeat)
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
        path = f"/internal/v1/asset-tasks/{task.id}/fail"
        response = self._call("POST", path, heartbeat, json=body)
        _log(
            logging.WARNING, task.id, "fail", code if response.is_success else _error_code(response)
        )

    def _call(
        self, method: str, path: str, heartbeat: Heartbeat | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Faz a chamada repetindo erro de rede com backoff de 1 a 30 s.

        Com heartbeat, confere a tentativa antes de cada envio e transforma 409 em
        StaleAttempt; sem ele (claim), a parada pedida interrompe a espera com Stopped.
        """
        interrupt = heartbeat.lost if heartbeat else self._stop
        delay = BACKOFF_MIN_S
        while True:
            if heartbeat:
                heartbeat.check()
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TransportError:
                response = None
            if response is not None and response.status_code not in RETRY_STATUS:
                if heartbeat and response.status_code == 409:
                    heartbeat.mark_lost()
                    raise StaleAttempt
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
    headers = {"Authorization": f"Bearer {config.token}"}
    with httpx.Client(
        base_url=config.api_url, headers=headers, timeout=REQUEST_TIMEOUT_S
    ) as client:
        supervisor = Supervisor(config, client)
        signal.signal(signal.SIGTERM, lambda *_: supervisor.request_stop())
        supervisor.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
