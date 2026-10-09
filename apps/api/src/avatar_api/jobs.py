"""Jobs de vídeo e fila de trabalho.

Criação com snapshot do pedido e idempotência por solicitante; claim exclusivo por
SELECT ... FOR UPDATE SKIP LOCKED, lease pelo relógio do banco e heartbeat da tentativa vigente.
Envio de arquivos, complete e fail só pela tentativa vigente; varredura de leases vencidos.
"""

import hashlib
import json
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, BinaryIO, Literal

from pydantic import AfterValidator, BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.assets import asset_dir
from avatar_api.errors import ApiError
from avatar_api.models import (
    AssetPrepareTask,
    Avatar,
    JobAttempt,
    RenderRecipe,
    Scene,
    StoredFile,
    VideoJob,
    WorkerHeartbeat,
)
from avatar_api.storage import resolve_path, save_stream
from avatar_api.uploads import validate_image

IDEMPOTENCY_KEY_MAX_CHARS = 128


def _without_nul(value: str) -> str:
    # O PostgreSQL não aceita NUL em text; recusar aqui evita erro do banco no INSERT.
    if "\x00" in value:
        raise ValueError("texto com caractere NUL")
    return value


class NewVideoJob(BaseModel):
    script_text: Annotated[str, AfterValidator(_without_nul)]
    avatar_id: uuid.UUID
    scene_id: uuid.UUID
    aspect_ratio: Literal["9:16", "16:9"] = "9:16"


@dataclass(frozen=True)
class JobRequester:
    """Quem pede o job: uma chave de API (origin api) ou um usuário do painel (origin panel)."""

    origin: Literal["api", "panel"]
    api_key_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


def request_hash(payload: NewVideoJob) -> str:
    """SHA-256 do corpo canônico: fala literal intacta, formato padrão aplicado."""
    body = payload.model_dump(mode="json")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _find_by_idempotency_key(
    session: Session, requester: JobRequester, idempotency_key: str
) -> VideoJob | None:
    owner = (
        VideoJob.api_key_id == requester.api_key_id
        if requester.origin == "api"
        else VideoJob.requested_by_user_id == requester.user_id
    )
    return session.scalar(
        select(VideoJob).where(owner, VideoJob.idempotency_key == idempotency_key)
    )


def _replay(job: VideoJob, hash_: str) -> VideoJob:
    if job.request_hash != hash_:
        raise ApiError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "Idempotency-Key já usada com outro conteúdo de pedido.",
        )
    return job


def _current_recipe(session: Session) -> RenderRecipe:
    recipe = session.scalar(select(RenderRecipe).where(RenderRecipe.is_current))
    if recipe is None:
        raise ApiError(
            503, "RECIPE_UNAVAILABLE", "Nenhuma receita de geração vigente. Tente mais tarde."
        )
    return recipe


def _available_avatar(session: Session, avatar_id: uuid.UUID) -> Avatar:
    # FOR SHARE impede que o avatar seja arquivado ou alterado até o commit do job.
    avatar = session.get(Avatar, avatar_id, with_for_update={"read": True})
    if (
        avatar is None
        or avatar.prepare_status != "ativo"
        or avatar.archived_at is not None
        or avatar.prepared_file_id is None
    ):
        raise ApiError(
            422, "AVATAR_UNAVAILABLE", "Avatar inexistente ou indisponível.", "avatar_id"
        )
    return avatar


def _available_scene(session: Session, scene_id: uuid.UUID) -> Scene:
    scene = session.get(Scene, scene_id, with_for_update={"read": True})
    if scene is None or scene.archived_at is not None:
        raise ApiError(422, "SCENE_UNAVAILABLE", "Cenário inexistente ou indisponível.", "scene_id")
    return scene


def _valid_script(script_text: str, recipe: RenderRecipe) -> str:
    if not script_text.strip():
        raise ApiError(422, "SCRIPT_EMPTY", "O texto do vídeo está vazio.", "script_text")
    if len(script_text) > recipe.max_script_chars:
        raise ApiError(
            422,
            "SCRIPT_TOO_LONG",
            f"O texto passa do limite de {recipe.max_script_chars} caracteres.",
            "script_text",
        )
    return script_text


def create_video_job(
    session: Session,
    requester: JobRequester,
    payload: NewVideoJob,
    idempotency_key: str | None = None,
) -> VideoJob:
    """Valida, grava o job com snapshot e faz commit; devolve o job já persistido.

    Com Idempotency-Key repetida e mesmo corpo, devolve o job existente sem criar outro.
    """
    hash_ = request_hash(payload)
    if idempotency_key is not None:
        existing = _find_by_idempotency_key(session, requester, idempotency_key)
        if existing is not None:
            return _replay(existing, hash_)

    recipe = _current_recipe(session)
    avatar = _available_avatar(session, payload.avatar_id)
    scene = _available_scene(session, payload.scene_id)
    script = _valid_script(payload.script_text, recipe)

    job = VideoJob(
        origin=requester.origin,
        api_key_id=requester.api_key_id,
        requested_by_user_id=requester.user_id,
        idempotency_key=idempotency_key,
        request_hash=hash_,
        script_text=script,
        avatar_id=avatar.id,
        avatar_file_id=avatar.prepared_file_id,
        scene_id=scene.id,
        scene_file_id=scene.background_file_id,
        voice=avatar.voice,
        aspect_ratio=payload.aspect_ratio,
        recipe_id=recipe.id,
        status="queued",
        stage="waiting",
        attempt=0,
        lease_generation=0,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # Outra requisição com a mesma chave gravou primeiro: vale o job dela.
        if idempotency_key is not None:
            existing = _find_by_idempotency_key(session, requester, idempotency_key)
            if existing is not None:
                return _replay(existing, hash_)
        raise
    return job


# --- fila: claim, lease e heartbeat ---------------------------------------------------

QueueKind = Literal["video", "asset_prepare"]
ProcessingStage = Literal["compose", "tts", "render", "finalize", "upload"]
QueueItem = VideoJob | AssetPrepareTask

QUEUE_MODELS: dict[str, type[QueueItem]] = {
    "video": VideoJob,
    "asset_prepare": AssetPrepareTask,
}


class VideoPayload(BaseModel):
    """Snapshot congelado na criação do job: é tudo o que o worker usa para gerar o vídeo."""

    script_text: str
    avatar_id: uuid.UUID
    avatar_file_id: uuid.UUID
    scene_id: uuid.UUID
    scene_file_id: uuid.UUID | None
    voice: str
    aspect_ratio: str
    recipe_id: uuid.UUID
    recipe_spec: dict[str, Any]
    background_color: str | None
    composition: dict[str, dict[str, float]]


class AssetPreparePayload(BaseModel):
    avatar_id: uuid.UUID
    source_file_id: uuid.UUID


@dataclass(frozen=True)
class Claim:
    kind: QueueKind
    id: uuid.UUID
    attempt_id: uuid.UUID
    lease_generation: int
    lease_until: datetime
    payload: VideoPayload | AssetPreparePayload


def _video_payload(session: Session, job: VideoJob) -> VideoPayload:
    # Receitas e parâmetros de cenas não são editáveis: IDs do job preservam a versão.
    recipe = session.get(RenderRecipe, job.recipe_id)
    scene = session.get(Scene, job.scene_id)
    return VideoPayload(
        script_text=job.script_text,
        avatar_id=job.avatar_id,
        avatar_file_id=job.avatar_file_id,
        scene_id=job.scene_id,
        scene_file_id=job.scene_file_id,
        voice=job.voice,
        aspect_ratio=job.aspect_ratio,
        recipe_id=job.recipe_id,
        recipe_spec=recipe.spec,
        background_color=scene.background_color,
        composition=scene.composition,
    )


def _asset_payload(session: Session, task: AssetPrepareTask) -> AssetPreparePayload:
    source_file_id = session.scalar(
        select(Avatar.source_file_id).where(Avatar.id == task.avatar_id)
    )
    return AssetPreparePayload(avatar_id=task.avatar_id, source_file_id=source_file_id)


def _record_video_worker(session: Session, worker_id: str) -> None:
    session.execute(
        insert(WorkerHeartbeat)
        .values(worker_id=worker_id, last_heartbeat_at=func.now())
        .on_conflict_do_update(
            index_elements=[WorkerHeartbeat.worker_id],
            set_={"last_heartbeat_at": func.now()},
        )
    )


def last_video_worker_heartbeat(session: Session) -> datetime | None:
    return session.scalar(select(func.max(WorkerHeartbeat.last_heartbeat_at)))


def claim_next(
    session: Session, worker_id: str, kinds: list[QueueKind], lease_seconds: int
) -> Claim | None:
    """Reivindica o item queued mais antigo do primeiro tipo, na ordem de `kinds`, que tiver um.

    A linha é travada com FOR UPDATE SKIP LOCKED: outra transação que já a travou faz esta
    pular para a próxima, sem esperar e sem devolver o mesmo item. O lease vem de now() do
    banco. Não faz commit: o chamador faz, e só depois disso o item pertence ao worker.
    """
    if "video" in kinds:
        _record_video_worker(session, worker_id)
    for kind in dict.fromkeys(kinds):
        model = QUEUE_MODELS[kind]
        item = session.scalar(
            select(model)
            .where(model.status == "queued")
            .order_by(model.created_at, model.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if item is None:
            continue
        attempt_id = uuid.uuid4()
        item.attempt += 1
        item.lease_generation += 1
        item.current_attempt_id = attempt_id
        item.worker_id = worker_id
        item.status = "processing"
        item.started_at = func.now()
        item.lease_until = func.now() + timedelta(seconds=lease_seconds)
        if isinstance(item, VideoJob):
            session.add(
                JobAttempt(
                    attempt_id=attempt_id,
                    job_id=item.id,
                    attempt_number=item.attempt,
                    lease_generation=item.lease_generation,
                    worker_id=worker_id,
                )
            )
        session.flush()
        session.refresh(item)
        payload = (
            _video_payload(session, item)
            if isinstance(item, VideoJob)
            else _asset_payload(session, item)
        )
        return Claim(
            kind=kind,
            id=item.id,
            attempt_id=attempt_id,
            lease_generation=item.lease_generation,
            lease_until=item.lease_until,
            payload=payload,
        )
    return None


def _stale_attempt() -> ApiError:
    return ApiError(
        409, "STALE_ATTEMPT", "Esta tentativa não é mais a vigente para o item. Pare o trabalho."
    )


def lock_current_attempt(
    session: Session,
    kind: QueueKind,
    item_id: uuid.UUID,
    attempt_id: uuid.UUID,
    lease_generation: int,
) -> QueueItem:
    """Trava a linha e exige a tentativa vigente: processing, mesmo attempt_id, mesma
    lease_generation e lease ainda no futuro pelo relógio do banco. Senão, 409 STALE_ATTEMPT.
    """
    item, lease_alive = _lock_item(session, kind, item_id)
    _require_current(item, lease_alive, attempt_id, lease_generation)
    return item


def _lock_item(session: Session, kind: QueueKind, item_id: uuid.UUID) -> tuple[QueueItem, bool]:
    """Trava a linha com FOR UPDATE e diz se o lease ainda vale pelo relógio do banco."""
    model = QUEUE_MODELS[kind]
    row = session.execute(
        select(model, (model.lease_until > func.now()).label("lease_alive"))
        .where(model.id == item_id)
        .with_for_update(of=model)
    ).one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Item da fila não encontrado.")
    item, lease_alive = row
    return item, bool(lease_alive)


def _require_current(
    item: QueueItem, lease_alive: bool, attempt_id: uuid.UUID, lease_generation: int
) -> None:
    if (
        item.status != "processing"
        or item.current_attempt_id != attempt_id
        or item.lease_generation != lease_generation
        or not lease_alive
    ):
        raise _stale_attempt()


def heartbeat(
    session: Session,
    kind: QueueKind,
    item_id: uuid.UUID,
    attempt_id: uuid.UUID,
    lease_generation: int,
    lease_seconds: int,
    stage: ProcessingStage | None = None,
) -> datetime:
    """Renova o lease da tentativa vigente e faz commit; devolve o novo lease_until."""
    item = lock_current_attempt(session, kind, item_id, attempt_id, lease_generation)
    item.lease_until = func.now() + timedelta(seconds=lease_seconds)
    if isinstance(item, VideoJob):
        if stage is not None:
            item.stage = stage
        session.execute(
            update(JobAttempt)
            .where(JobAttempt.attempt_id == attempt_id)
            .values(last_heartbeat_at=func.now())
        )
        _record_video_worker(session, item.worker_id)
    session.flush()
    session.refresh(item)
    lease_until = item.lease_until
    session.commit()
    return lease_until


# --- publicação: arquivos da tentativa, complete e fail --------------------------------

MAX_ATTEMPTS = 3
AttemptFileName = Literal["audio.wav", "render.mp4", "final.mp4", "manifest.json"]
ATTEMPT_FILE_TYPES: dict[str, str] = {
    "audio.wav": "audio/wav",
    "render.mp4": "video/mp4",
    "final.mp4": "video/mp4",
    "manifest.json": "application/json",
}
RESULT_FILE_NAME = "final.mp4"
AssetFileName = Literal["prepared.png", "preview-9x16.png", "preview-16x9.png"]
# Coluna do avatar preenchida no complete da preparação -> arquivo esperado da tentativa.
ASSET_RESULT_FILES: dict[str, str] = {
    "prepared_file_id": "prepared.png",
    "preview_9x16_file_id": "preview-9x16.png",
    "preview_16x9_file_id": "preview-16x9.png",
}


def attempt_dir(job_id: uuid.UUID, attempt_id: uuid.UUID) -> str:
    return f"jobs/{job_id}/{attempt_id}"


def _item_attempt_dir(item: QueueItem, attempt_id: uuid.UUID) -> str:
    """Vídeo em jobs/<job_id>/<attempt_id>; preparação em assets/<avatar_id>/<attempt_id>."""
    if isinstance(item, VideoJob):
        return attempt_dir(item.id, attempt_id)
    return f"{asset_dir(item.avatar_id)}/{attempt_id}"


def _existing_attempt_file(session: Session, relative_path: str, sha256: str) -> StoredFile | None:
    """Arquivo já gravado no caminho: o mesmo SHA-256 é reenvio; outro SHA é conflito."""
    existing = session.scalar(select(StoredFile).where(StoredFile.relative_path == relative_path))
    if existing is not None and existing.sha256 != sha256:
        raise ApiError(
            409, "FILE_EXISTS", "Já existe outro arquivo com esse nome nesta tentativa.", "name"
        )
    return existing


def _save_png(
    session: Session,
    data_dir: Path,
    directory: str,
    name: str,
    stream: BinaryIO,
    sha256: str,
    attempt_id: uuid.UUID,
) -> StoredFile:
    """Grava o arquivo da preparação só se for um PNG legível; a validação usa um temporário
    fora de DATA_DIR, então a recusa não deixa nada no volume."""
    with tempfile.TemporaryDirectory(prefix="asset-prepare-") as tmp_dir:
        image = validate_image(stream, "file", Path(tmp_dir))
        if image.content_type != "image/png":
            raise ApiError(422, "UNSUPPORTED_FILE_TYPE", "Envie o arquivo em PNG.", "file")
        with image.path.open("rb") as validated:
            return save_stream(
                session,
                data_dir,
                directory,
                name,
                validated,
                sha256,
                image.content_type,
                attempt_id=attempt_id,
            )


def save_attempt_file(
    session: Session,
    data_dir: Path,
    kind: QueueKind,
    item_id: uuid.UUID,
    attempt_id: uuid.UUID,
    lease_generation: int,
    name: AttemptFileName | AssetFileName,
    stream: BinaryIO,
    sha256: str,
) -> tuple[StoredFile, bool]:
    """Grava um arquivo da tentativa vigente no diretório da tentativa (ver _item_attempt_dir).

    Devolve o arquivo e se ele foi criado agora. A vigência é conferida com a linha travada,
    e a trava é solta antes de receber o conteúdo: um envio longo não pode segurar heartbeat
    nem varredor. O envio não altera o item; só o complete publica, e ele exige a tentativa
    vigente e os arquivos gravados por ela. Na preparação de avatar, o arquivo precisa ser PNG.
    """
    sha256 = sha256.lower()
    item = lock_current_attempt(session, kind, item_id, attempt_id, lease_generation)
    directory = _item_attempt_dir(item, attempt_id)
    existing = _existing_attempt_file(session, f"{directory}/{name}", sha256)
    session.commit()
    if existing is not None:
        return existing, False
    try:
        if kind == "video":
            stored = save_stream(
                session,
                data_dir,
                directory,
                name,
                stream,
                sha256,
                ATTEMPT_FILE_TYPES[name],
                attempt_id=attempt_id,
            )
        else:
            stored = _save_png(session, data_dir, directory, name, stream, sha256, attempt_id)
    except ApiError as exc:
        # Reenvio concorrente do mesmo arquivo: quem gravou primeiro vale.
        if exc.code != "FILE_EXISTS":
            raise
        existing = _existing_attempt_file(session, f"{directory}/{name}", sha256)
        if existing is None:
            raise
        return existing, False
    return stored, True


def _invalid_result(message: str) -> ApiError:
    return ApiError(422, "RESULT_FILE_INVALID", message, "result_file_id")


def _written_by(stored: StoredFile | None, expected_path: str, attempt_id: uuid.UUID) -> bool:
    return (
        stored is not None
        and stored.relative_path == expected_path
        and stored.attempt_id == attempt_id
    )


def _intact(data_dir: Path, stored: StoredFile) -> bool:
    path = resolve_path(data_dir, stored)
    try:
        if not path.is_file() or path.stat().st_size != stored.size_bytes:
            return False
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest() == stored.sha256
    except OSError:
        return False


def _own_result_file(
    session: Session,
    data_dir: Path,
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    result_file_id: uuid.UUID,
) -> StoredFile:
    """O resultado só vale se for o final.mp4 gravado por esta tentativa e presente no volume."""
    stored = session.get(StoredFile, result_file_id)
    expected_path = f"{attempt_dir(job_id, attempt_id)}/{RESULT_FILE_NAME}"
    if not _written_by(stored, expected_path, attempt_id):
        raise _invalid_result("O resultado precisa ser o final.mp4 enviado por esta tentativa.")
    if not _intact(data_dir, stored):
        raise _invalid_result("O final.mp4 desta tentativa não está íntegro no volume.")
    return stored


def _invalid_asset_file(column: str, message: str) -> ApiError:
    return ApiError(422, "INVALID_RESULT", message, column)


def _publish_prepared_avatar(
    session: Session,
    data_dir: Path,
    task: AssetPrepareTask,
    attempt_id: uuid.UUID,
    file_ids: dict[str, uuid.UUID | None],
) -> None:
    """Grava no avatar o recorte e as duas prévias e o deixa ativo, na transação do complete.

    Cada arquivo precisa ser o de nome esperado gravado por esta tentativa e presente no
    volume; senão 422 INVALID_RESULT e o avatar fica como estava.
    """
    directory = _item_attempt_dir(task, attempt_id)
    for column, name in ASSET_RESULT_FILES.items():
        file_id = file_ids.get(column)
        stored = session.get(StoredFile, file_id) if file_id is not None else None
        if not _written_by(stored, f"{directory}/{name}", attempt_id):
            raise _invalid_asset_file(column, f"Informe o {name} enviado por esta tentativa.")
        if not _intact(data_dir, stored):
            raise _invalid_asset_file(column, f"O {name} desta tentativa não está íntegro.")
    avatar = session.get(Avatar, task.avatar_id, with_for_update=True)
    for column in ASSET_RESULT_FILES:
        setattr(avatar, column, file_ids[column])
    avatar.prepare_status = "ativo"
    avatar.prepare_error = None


def _same_result(
    session: Session,
    item: QueueItem,
    result_file_id: uuid.UUID | None,
    asset_files: dict[str, uuid.UUID | None],
) -> bool:
    """O complete repetido traz o mesmo resultado que a tentativa já publicou."""
    if isinstance(item, VideoJob):
        return item.result_file_id == result_file_id
    avatar = session.get(Avatar, item.avatar_id)
    return all(getattr(avatar, column) == asset_files.get(column) for column in ASSET_RESULT_FILES)


def _finish_attempt(session: Session, item: QueueItem, outcome: str, **values: object) -> None:
    """Fecha a linha de job_attempts da tentativa vigente; asset_prepare não tem essa tabela."""
    if isinstance(item, VideoJob):
        session.execute(
            update(JobAttempt)
            .where(JobAttempt.attempt_id == item.current_attempt_id)
            .values(outcome=outcome, finished_at=func.now(), **values)
        )


def _requeue(item: QueueItem) -> None:
    # attempt e lease_generation ficam: o próximo claim soma a partir deles.
    item.status = "queued"
    item.lease_until = None
    if isinstance(item, VideoJob):
        item.stage = "waiting"


def _mark_failed(session: Session, item: QueueItem, error_code: str, error_message: str) -> None:
    """Falha definitiva; na preparação, o avatar fica em falha com a mensagem como motivo."""
    item.status = "failed"
    item.lease_until = None
    item.error_code = error_code
    item.error_message = error_message
    item.finished_at = func.now()
    if isinstance(item, AssetPrepareTask):
        session.execute(
            update(Avatar)
            .where(Avatar.id == item.avatar_id)
            .values(prepare_status="falha", prepare_error=error_message)
        )


def _commit_item(session: Session, item: QueueItem) -> QueueItem:
    session.flush()
    session.refresh(item)
    session.commit()
    return item


def complete_item(
    session: Session,
    kind: QueueKind,
    item_id: uuid.UUID,
    attempt_id: uuid.UUID,
    lease_generation: int,
    data_dir: Path,
    result_file_id: uuid.UUID | None = None,
    stage_timings: dict[str, float] | None = None,
    peak_vram_mb: int | None = None,
    asset_files: dict[str, uuid.UUID | None] | None = None,
) -> QueueItem:
    """Conclui o item pela tentativa vigente e faz commit.

    No vídeo, result_file_id, ready, finished_at e o outcome completed da tentativa vão na
    mesma transação. Na preparação, asset_files traz os ids de ASSET_RESULT_FILES, e o
    avatar recebe os três arquivos e fica ativo na mesma transação que deixa a tarefa ready.
    O complete repetido pela tentativa que já concluiu devolve o mesmo resultado sem alterar
    nada.
    """
    asset_files = asset_files or {}
    item, lease_alive = _lock_item(session, kind, item_id)
    if (
        item.status == "ready"
        and item.current_attempt_id == attempt_id
        and item.lease_generation == lease_generation
        and _same_result(session, item, result_file_id, asset_files)
    ):
        session.commit()
        return item
    _require_current(item, lease_alive, attempt_id, lease_generation)
    if isinstance(item, VideoJob):
        if result_file_id is None:
            raise _invalid_result("Informe o final.mp4 enviado por esta tentativa.")
        stored = _own_result_file(session, data_dir, item_id, attempt_id, result_file_id)
        item.result_file_id = stored.id
    else:
        _publish_prepared_avatar(session, data_dir, item, attempt_id, asset_files)
    item.status = "ready"
    item.lease_until = None
    item.finished_at = func.now()
    _finish_attempt(
        session,
        item,
        "completed",
        stage_timings=stage_timings or {},
        peak_vram_mb=peak_vram_mb,
    )
    return _commit_item(session, item)


def fail_item(
    session: Session,
    kind: QueueKind,
    item_id: uuid.UUID,
    attempt_id: uuid.UUID,
    lease_generation: int,
    error_code: str,
    error_message: str,
    retryable: bool,
) -> QueueItem:
    """Registra a falha da tentativa vigente e faz commit: com retryable e menos de
    MAX_ATTEMPTS tentativas o item volta a queued; senão fica failed com o código e a mensagem.
    """
    item = lock_current_attempt(session, kind, item_id, attempt_id, lease_generation)
    if retryable and item.attempt < MAX_ATTEMPTS:
        _requeue(item)
    else:
        _mark_failed(session, item, error_code, error_message)
    _finish_attempt(session, item, "failed", error_code=error_code, error_message=error_message)
    return _commit_item(session, item)


# --- varredura de leases vencidos ------------------------------------------------------

WORKER_LOST = "WORKER_LOST"
WORKER_LOST_MESSAGE = f"O worker parou de responder nas {MAX_ATTEMPTS} tentativas."


@dataclass(frozen=True)
class SweepResult:
    requeued: int
    lost: int


def sweep_expired_leases(session: Session) -> SweepResult:
    """Trata os itens em processing com lease vencido pelo relógio do banco e faz commit.

    Com menos de MAX_ATTEMPTS tentativas o item volta a queued; na última fica failed com
    WORKER_LOST. A tentativa vencida fica expired. SKIP LOCKED pula a linha que um heartbeat,
    complete ou fail estiver travando; a próxima varredura a vê de novo, se ainda vencida.
    """
    requeued = lost = 0
    for model in QUEUE_MODELS.values():
        expired = session.scalars(
            select(model)
            .where(model.status == "processing", model.lease_until <= func.now())
            .with_for_update(skip_locked=True)
        ).all()
        for item in expired:
            if item.attempt < MAX_ATTEMPTS:
                _requeue(item)
                requeued += 1
            else:
                _mark_failed(session, item, WORKER_LOST, WORKER_LOST_MESSAGE)
                lost += 1
            _finish_attempt(session, item, "expired")
    session.commit()
    return SweepResult(requeued=requeued, lost=lost)
