"""Aulas do painel: várias cenas em ordem, cada uma um job de vídeo comum.

A aula, as cenas e os jobs filhos são gravados na mesma transação, com a identidade visual
vigente (logo, cores e, se ligada, a trilha) copiada para a aula. Tópicos e imagem de cada
cena vão para a montagem; a imagem é enviada antes, por POST /panel/lessons/images. A GPU
não sabe que o job pertence a uma aula; a montagem final roda depois, no supervisor CPU
(ver jobs.py).
"""

import hashlib
import json
import uuid
from pathlib import Path
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
    MAX_SCENE_TOPICS,
    MAX_TOPIC_CHARS,
    MIN_LESSON_SCENES,
    Lesson,
    LessonScene,
    RenderRecipe,
    StoredFile,
    VideoJob,
)
from avatar_api.storage import resolve_path, save_stream
from avatar_api.uploads import ValidatedImage

LESSON_IMAGES_DIR = "lesson-images"


class NewLessonScene(BaseModel):
    script_text: Annotated[str, AfterValidator(_without_nul)]
    shot: Literal["medio", "close"] = "medio"
    topics: list[Annotated[str, AfterValidator(_without_nul)]] = []
    image_file_id: uuid.UUID | None = None


class NewLesson(BaseModel):
    avatar_id: uuid.UUID
    scene_id: uuid.UUID
    aspect_ratio: Literal["9:16", "16:9"] = "9:16"
    scenes: list[NewLessonScene]
    music_enabled: bool = False


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


def _scene_topics(topics: list[str], position: int) -> list[str]:
    """Até 5 tópicos com até 80 caracteres; o texto fica exatamente como foi informado."""
    field = f"scenes.{position - 1}.topics"

    def invalid(reason: str) -> ApiError:
        return ApiError(422, "LESSON_TOPICS_INVALID", f"Cena {position}: {reason}.", field)

    if len(topics) > MAX_SCENE_TOPICS:
        raise invalid(f"no máximo {MAX_SCENE_TOPICS} tópicos")
    for number, topic in enumerate(topics, start=1):
        if not topic.strip():
            raise invalid(f"o tópico {number} está vazio")
        if len(topic) > MAX_TOPIC_CHARS:
            raise invalid(f"o tópico {number} passa de {MAX_TOPIC_CHARS} caracteres")
    return topics


def _scene_image(session: Session, file_id: uuid.UUID | None, position: int) -> None:
    """A imagem precisa ter sido enviada por POST /panel/lessons/images."""
    if file_id is None:
        return
    stored = session.get(StoredFile, file_id)
    if stored is None or not stored.relative_path.startswith(f"{LESSON_IMAGES_DIR}/"):
        raise ApiError(
            422,
            "LESSON_IMAGE_NOT_FOUND",
            f"Cena {position}: a imagem não foi encontrada. Envie a imagem de novo.",
            f"scenes.{position - 1}.image_file_id",
        )


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
    for position, item in enumerate(payload.scenes, start=1):
        _scene_topics(item.topics, position)
        _scene_image(session, item.image_file_id, position)
    identity = get_brand_identity(session)
    if identity is None:
        raise ApiError(
            422,
            "BRAND_IDENTITY_MISSING",
            "Cadastre o logo e as cores na tela Identidade antes de gerar uma aula.",
        )
    if payload.music_enabled and identity.music_file_id is None:
        raise ApiError(
            422,
            "BRAND_MUSIC_MISSING",
            "Envie a trilha na tela Identidade ou desligue a trilha da aula.",
            "music_enabled",
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
        music_enabled=payload.music_enabled,
        music_file_id=identity.music_file_id if payload.music_enabled else None,
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
                topics=item.topics,
                image_file_id=item.image_file_id,
                video_job_id=job.id,
            )
            for job, item in zip(jobs, payload.scenes, strict=True)
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


def save_lesson_image(session: Session, data_dir: Path, image: ValidatedImage) -> StoredFile:
    """Grava a imagem validada de uma cena; a aula a referencia depois pelo ID."""
    with image.path.open("rb") as stream:
        return save_stream(
            session,
            data_dir,
            f"{LESSON_IMAGES_DIR}/{uuid.uuid4()}",
            f"imagem{image.extension}",
            stream,
            image.sha256,
            image.content_type,
        )


def lesson_image(session: Session, data_dir: Path, file_id: uuid.UUID) -> tuple[Path, StoredFile]:
    stored = session.get(StoredFile, file_id)
    if stored is None or not stored.relative_path.startswith(f"{LESSON_IMAGES_DIR}/"):
        raise ApiError(404, "NOT_FOUND", "Imagem não encontrada.")
    return resolve_path(data_dir, stored), stored


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
