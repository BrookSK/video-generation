"""Criação de jobs de vídeo com snapshot do pedido e idempotência por solicitante."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.errors import ApiError
from avatar_api.models import Avatar, RenderRecipe, Scene, VideoJob

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
