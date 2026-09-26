"""Jobs de vídeo e fila de trabalho.

Criação com snapshot do pedido e idempotência por solicitante; claim exclusivo por
SELECT ... FOR UPDATE SKIP LOCKED, lease pelo relógio do banco e heartbeat da tentativa vigente.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.errors import ApiError
from avatar_api.models import (
    AssetPrepareTask,
    Avatar,
    JobAttempt,
    RenderRecipe,
    Scene,
    VideoJob,
)

IDEMPOTENCY_KEY_MAX_CHARS = 128


class NewVideoJob(BaseModel):
    script_text: str
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
    """SHA-256 do corpo normalizado: texto sem espaços nas pontas, formato padrão aplicado."""
    body = payload.model_dump(mode="json")
    body["script_text"] = payload.script_text.strip()
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
    script = script_text.strip()
    if not script:
        raise ApiError(422, "SCRIPT_EMPTY", "O texto do vídeo está vazio.", "script_text")
    if len(script) > recipe.max_script_chars:
        raise ApiError(
            422,
            "SCRIPT_TOO_LONG",
            f"O texto passa do limite de {recipe.max_script_chars} caracteres.",
            "script_text",
        )
    return script


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


def _video_payload(job: VideoJob) -> VideoPayload:
    return VideoPayload(
        script_text=job.script_text,
        avatar_id=job.avatar_id,
        avatar_file_id=job.avatar_file_id,
        scene_id=job.scene_id,
        scene_file_id=job.scene_file_id,
        voice=job.voice,
        aspect_ratio=job.aspect_ratio,
        recipe_id=job.recipe_id,
    )


def _asset_payload(session: Session, task: AssetPrepareTask) -> AssetPreparePayload:
    source_file_id = session.scalar(
        select(Avatar.source_file_id).where(Avatar.id == task.avatar_id)
    )
    return AssetPreparePayload(avatar_id=task.avatar_id, source_file_id=source_file_id)


def claim_next(
    session: Session, worker_id: str, kinds: list[QueueKind], lease_seconds: int
) -> Claim | None:
    """Reivindica o item queued mais antigo do primeiro tipo, na ordem de `kinds`, que tiver um.

    A linha é travada com FOR UPDATE SKIP LOCKED: outra transação que já a travou faz esta
    pular para a próxima, sem esperar e sem devolver o mesmo item. O lease vem de now() do
    banco. Não faz commit: o chamador faz, e só depois disso o item pertence ao worker.
    """
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
            _video_payload(item) if isinstance(item, VideoJob) else _asset_payload(session, item)
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
    model = QUEUE_MODELS[kind]
    row = session.execute(
        select(model, (model.lease_until > func.now()).label("lease_alive"))
        .where(model.id == item_id)
        .with_for_update(of=model)
    ).one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Item da fila não encontrado.")
    item, lease_alive = row
    if (
        item.status != "processing"
        or item.current_attempt_id != attempt_id
        or item.lease_generation != lease_generation
        or not lease_alive
    ):
        raise _stale_attempt()
    return item


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
    session.flush()
    session.refresh(item)
    lease_until = item.lease_until
    session.commit()
    return lease_until
