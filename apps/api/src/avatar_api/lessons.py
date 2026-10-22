"""Aulas do painel: várias cenas em ordem, cada uma um job de vídeo comum.

A aula, as cenas e os jobs filhos são gravados na mesma transação, com a identidade visual
vigente copiada para a aula. A GPU não sabe que o job pertence a uma aula; a montagem final
roda depois, no supervisor CPU (ver jobs.py).
"""

import hashlib
import json
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.assets import get_brand_identity
from avatar_api.errors import ApiError
from avatar_api.jobs import (
    _available_avatar,
    _available_scene,
    _current_recipe,
    _replay,
    _valid_script,
    _without_nul,
)
from avatar_api.models import (
    MAX_LESSON_SCENES,
    MIN_LESSON_SCENES,
    Lesson,
    LessonScene,
    RenderRecipe,
    VideoJob,
)


class NewLessonScene(BaseModel):
    script_text: Annotated[str, AfterValidator(_without_nul)]
    shot: Literal["medio", "close"] = "medio"


class NewLesson(BaseModel):
    avatar_id: uuid.UUID
    scene_id: uuid.UUID
    aspect_ratio: Literal["9:16", "16:9"] = "9:16"
    scenes: list[NewLessonScene]


def lesson_request_hash(payload: NewLesson) -> str:
    """SHA-256 do corpo canônico: textos literais intactos, padrões aplicados."""
    body = payload.model_dump(mode="json")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _find_by_idempotency_key(
    session: Session, user_id: uuid.UUID, idempotency_key: str
) -> Lesson | None:
    return session.scalar(
        select(Lesson).where(
            Lesson.requested_by_user_id == user_id, Lesson.idempotency_key == idempotency_key
        )
    )


def _valid_scene_count(payload: NewLesson) -> None:
    if not MIN_LESSON_SCENES <= len(payload.scenes) <= MAX_LESSON_SCENES:
        raise ApiError(
            422,
            "LESSON_SCENES_OUT_OF_RANGE",
            f"A aula precisa ter de {MIN_LESSON_SCENES} a {MAX_LESSON_SCENES} cenas.",
            "scenes",
        )


def _scene_script(script_text: str, position: int, recipe: RenderRecipe) -> str:
    """Valida o texto da cena com as regras do vídeo avulso, indicando a posição da cena."""
    try:
        return _valid_script(script_text, recipe)
    except ApiError as exc:
        reason = (
            "o texto está vazio"
            if exc.code == "SCRIPT_EMPTY"
            else f"o texto passa do limite de {recipe.max_script_chars} caracteres"
        )
        field = f"scenes.{position - 1}.script_text"
        raise ApiError(exc.status, exc.code, f"Cena {position}: {reason}.", field) from None


def create_lesson(
    session: Session,
    user_id: uuid.UUID,
    payload: NewLesson,
    idempotency_key: str | None = None,
) -> Lesson:
    """Valida, grava aula, cenas e jobs filhos e faz commit; devolve a aula já persistida.

    Com Idempotency-Key repetida e mesmo corpo, devolve a aula existente sem criar outra;
    com corpo diferente, 409 IDEMPOTENCY_CONFLICT. Qualquer recusa não grava nada.
    """
    hash_ = lesson_request_hash(payload)
    if idempotency_key is not None:
        existing = _find_by_idempotency_key(session, user_id, idempotency_key)
        if existing is not None:
            return _replay(existing, hash_)

    _valid_scene_count(payload)
    recipe = _current_recipe(session)
    avatar = _available_avatar(session, payload.avatar_id)
    scene = _available_scene(session, payload.scene_id)
    scripts = [
        _scene_script(item.script_text, position, recipe)
        for position, item in enumerate(payload.scenes, start=1)
    ]
    identity = get_brand_identity(session)
    if identity is None:
        raise ApiError(
            422,
            "BRAND_IDENTITY_MISSING",
            "Cadastre o logo e as cores na tela Identidade antes de gerar uma aula.",
        )

    lesson = Lesson(
        id=uuid.uuid4(),
        requested_by_user_id=user_id,
        idempotency_key=idempotency_key,
        request_hash=hash_,
        avatar_id=avatar.id,
        scene_id=scene.id,
        aspect_ratio=payload.aspect_ratio,
        logo_file_id=identity.logo_file_id,
        background_color=identity.background_color,
        accent_color=identity.accent_color,
        music_file_id=identity.music_file_id,
        status="queued",
    )
    jobs = [
        VideoJob(
            id=uuid.uuid4(),
            origin="panel",
            requested_by_user_id=user_id,
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
            lesson_id=lesson.id,
            lesson_position=position,
            shot=item.shot,
        )
        for position, (item, script) in enumerate(zip(payload.scenes, scripts, strict=True), 1)
    ]
    try:
        # Sem relationship() nos modelos, o flush por etapa garante a ordem das FKs no INSERT.
        session.add(lesson)
        session.flush()
        session.add_all(jobs)
        session.flush()
        session.add_all(
            LessonScene(
                lesson_id=lesson.id,
                position=job.lesson_position,
                script_text=job.script_text,
                shot=job.shot,
                video_job_id=job.id,
            )
            for job in jobs
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        # Outra requisição com a mesma chave gravou primeiro: vale a aula dela.
        if idempotency_key is not None:
            existing = _find_by_idempotency_key(session, user_id, idempotency_key)
            if existing is not None:
                return _replay(existing, hash_)
        raise
    return lesson


def get_lesson(session: Session, lesson_id: uuid.UUID) -> Lesson:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise ApiError(404, "NOT_FOUND", "Aula não encontrada.")
    return lesson


def lesson_scenes(session: Session, lesson_id: uuid.UUID) -> list[tuple[LessonScene, VideoJob]]:
    """Cenas da aula em ordem de posição, cada uma com o job filho."""
    rows = session.execute(
        select(LessonScene, VideoJob)
        .join(VideoJob, VideoJob.id == LessonScene.video_job_id)
        .where(LessonScene.lesson_id == lesson_id)
        .order_by(LessonScene.position)
    )
    return [(scene, job) for scene, job in rows]


def list_lessons(session: Session) -> list[Lesson]:
    return list(session.scalars(select(Lesson).order_by(Lesson.created_at.desc(), Lesson.id)))
