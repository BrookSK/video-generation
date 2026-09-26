"""Avatares e cenários do painel: cadastro, listagem, arquivamento e arquivos.

Arquivo de asset é imutável: não há edição; para trocar, a pessoa arquiva e cadastra outro.
"""

import hashlib
import io
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageOps
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api.errors import ApiError
from avatar_api.models import ASPECT_RATIOS, AssetPrepareTask, Avatar, Scene, StoredFile
from avatar_api.storage import resolve_path, save_stream
from avatar_api.uploads import ValidatedImage

AvatarStatus = Literal["preparando", "ativo", "falha", "arquivado"]
AvatarFileKind = Literal["source", "prepared", "preview-9x16", "preview-16x9"]
SceneStatus = Literal["ativo", "arquivado"]
SceneFileKind = Literal["background", "preview-9x16", "preview-16x9"]

_AVATAR_FILE_COLUMNS: dict[str, str] = {
    "source": "source_file_id",
    "prepared": "prepared_file_id",
    "preview-9x16": "preview_9x16_file_id",
    "preview-16x9": "preview_16x9_file_id",
}

_SCENE_FILE_COLUMNS: dict[str, str] = {
    "background": "background_file_id",
    "preview-9x16": "preview_9x16_file_id",
    "preview-16x9": "preview_16x9_file_id",
}

# Prévia do fundo por formato, no tamanho em que o painel a mostra.
_SCENE_PREVIEWS: dict[str, tuple[int, int]] = {
    "preview-9x16": (540, 960),
    "preview-16x9": (960, 540),
}

HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")

# Geometria de canvas.compose_canvas do worker: scale é a altura do avatar sobre a altura do
# canvas, x o centro horizontal e y a base, em frações do canvas.
_COMPOSITION_RANGES: dict[str, tuple[str, float, float]] = {
    "scale": ("escala", 0.3, 1.2),
    "x": ("posição horizontal", 0.0, 1.0),
    "y": ("base", 0.5, 1.2),
}


def asset_dir(asset_id: uuid.UUID) -> str:
    return f"assets/{asset_id}"


def avatar_status(avatar: Avatar) -> AvatarStatus:
    return "arquivado" if avatar.archived_at is not None else avatar.prepare_status


def create_avatar(
    session: Session,
    data_dir: Path,
    user_id: uuid.UUID,
    name: str,
    voice: str,
    image: ValidatedImage,
) -> Avatar:
    """Grava a imagem, o avatar em preparando e a tarefa asset_prepare num único commit.

    Se qualquer passo falhar, nada fica: a transação é desfeita e o arquivo gravado é apagado.
    """
    avatar_id = uuid.uuid4()
    try:
        with image.path.open("rb") as stream:
            source = save_stream(
                session,
                data_dir,
                asset_dir(avatar_id),
                f"source{image.extension}",
                stream,
                image.sha256,
                image.content_type,
                commit=False,
            )
        avatar = Avatar(
            id=avatar_id,
            name=name,
            voice=voice,
            source_file_id=source.id,
            prepare_status="preparando",
            authorized_by_user_id=user_id,
            authorized_at=func.now(),
            created_by_user_id=user_id,
        )
        session.add(avatar)
        session.flush()
        session.add(AssetPrepareTask(avatar_id=avatar_id, status="queued"))
        session.commit()
    except BaseException:
        session.rollback()
        raise
    session.refresh(avatar)
    return avatar


def get_avatar(session: Session, avatar_id: uuid.UUID, for_update: bool = False) -> Avatar:
    avatar = session.get(Avatar, avatar_id, with_for_update=for_update)
    if avatar is None:
        raise ApiError(404, "NOT_FOUND", "Avatar não encontrado.")
    return avatar


def list_avatars(session: Session, include_archived: bool = False) -> list[Avatar]:
    query = select(Avatar).order_by(Avatar.created_at.desc(), Avatar.id)
    if not include_archived:
        query = query.where(Avatar.archived_at.is_(None))
    return list(session.scalars(query))


def archive_avatar(session: Session, avatar_id: uuid.UUID) -> Avatar:
    """Tira o avatar de novos usos sem apagar arquivo; arquivar de novo não muda nada."""
    avatar = get_avatar(session, avatar_id, for_update=True)
    if avatar.archived_at is None:
        if avatar.prepare_status == "preparando":
            raise ApiError(
                409,
                "AVATAR_PREPARING",
                "O avatar ainda está em preparação. Aguarde terminar para arquivar.",
            )
        avatar.archived_at = func.now()
    session.commit()
    session.refresh(avatar)
    return avatar


def avatar_file(
    session: Session, data_dir: Path, avatar_id: uuid.UUID, kind: AvatarFileKind
) -> tuple[Path, StoredFile]:
    file_id = getattr(get_avatar(session, avatar_id), _AVATAR_FILE_COLUMNS[kind])
    if file_id is None:
        raise ApiError(404, "NOT_FOUND", "Arquivo do avatar ainda não disponível.")
    stored = session.get(StoredFile, file_id)
    return resolve_path(data_dir, stored), stored


# --- cenários ---------------------------------------------------------------------------


def _decimal(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _composition_error(message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, "composition")


def parse_composition(raw: str) -> dict[str, dict[str, float]]:
    """Lê o enquadramento em JSON: exatamente 9:16 e 16:9, cada um com scale, x e y na faixa."""
    try:
        data: Any = json.loads(raw)
    except ValueError:
        raise _composition_error("Enquadramento inválido.") from None
    if not isinstance(data, dict) or set(data) != set(ASPECT_RATIOS):
        raise _composition_error("Informe o enquadramento de 9:16 e de 16:9.")
    composition: dict[str, dict[str, float]] = {}
    for ratio in ASPECT_RATIOS:
        framing = data[ratio]
        if not isinstance(framing, dict) or set(framing) != set(_COMPOSITION_RANGES):
            raise _composition_error(f"Enquadramento {ratio}: informe escala, posição e base.")
        composition[ratio] = {}
        for key, (label, low, high) in _COMPOSITION_RANGES.items():
            value = framing[key]
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise _composition_error(f"Enquadramento {ratio}: {label} precisa ser um número.")
            if not (math.isfinite(value) and low <= value <= high):
                raise _composition_error(
                    f"Enquadramento {ratio}: {label} {_decimal(value)} fora da faixa de "
                    f"{_decimal(low)} a {_decimal(high)}."
                )
            composition[ratio][key] = float(value)
    return composition


def scene_status(scene: Scene) -> SceneStatus:
    return "arquivado" if scene.archived_at is not None else "ativo"


def _scene_previews(background_color: str | None, image: ValidatedImage | None) -> dict[str, bytes]:
    """PNG de cada formato: o fundo ajustado por cover e centralizado, ou a cor sólida."""
    source = None
    if image is not None:
        with Image.open(image.path) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
    previews = {}
    for kind, size in _SCENE_PREVIEWS.items():
        if source is not None:
            preview = ImageOps.fit(source, size, Image.Resampling.LANCZOS)
        else:
            preview = Image.new("RGB", size, background_color)
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG")
        previews[kind] = buffer.getvalue()
    return previews


def create_scene(
    session: Session,
    data_dir: Path,
    user_id: uuid.UUID,
    name: str,
    composition: dict[str, dict[str, float]],
    background_color: str | None = None,
    image: ValidatedImage | None = None,
) -> Scene:
    """Grava o fundo, as prévias e o cenário já ativo num único commit.

    Recebe exatamente um fundo: a cor #RRGGBB ou a imagem validada. Se qualquer passo
    falhar, nada fica: a transação é desfeita e os arquivos gravados são apagados.
    O CHECK one_background do banco recusa zero ou dois fundos.
    """
    scene_id = uuid.uuid4()
    directory = asset_dir(scene_id)
    try:
        background_file_id = None
        if image is not None:
            with image.path.open("rb") as stream:
                background = save_stream(
                    session,
                    data_dir,
                    directory,
                    f"background{image.extension}",
                    stream,
                    image.sha256,
                    image.content_type,
                    commit=False,
                )
            background_file_id = background.id
        preview_ids = {}
        for kind, data in _scene_previews(background_color, image).items():
            preview = save_stream(
                session,
                data_dir,
                directory,
                f"{kind}.png",
                io.BytesIO(data),
                hashlib.sha256(data).hexdigest(),
                "image/png",
                commit=False,
            )
            preview_ids[kind] = preview.id
        scene = Scene(
            id=scene_id,
            name=name,
            background_file_id=background_file_id,
            background_color=background_color,
            composition=composition,
            preview_9x16_file_id=preview_ids["preview-9x16"],
            preview_16x9_file_id=preview_ids["preview-16x9"],
            created_by_user_id=user_id,
        )
        session.add(scene)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    session.refresh(scene)
    return scene


def get_scene(session: Session, scene_id: uuid.UUID, for_update: bool = False) -> Scene:
    scene = session.get(Scene, scene_id, with_for_update=for_update)
    if scene is None:
        raise ApiError(404, "NOT_FOUND", "Cenário não encontrado.")
    return scene


def list_scenes(session: Session, include_archived: bool = False) -> list[Scene]:
    query = select(Scene).order_by(Scene.created_at.desc(), Scene.id)
    if not include_archived:
        query = query.where(Scene.archived_at.is_(None))
    return list(session.scalars(query))


def archive_scene(session: Session, scene_id: uuid.UUID) -> Scene:
    """Tira o cenário de novos usos sem apagar arquivo; arquivar de novo não muda nada."""
    scene = get_scene(session, scene_id, for_update=True)
    if scene.archived_at is None:
        scene.archived_at = func.now()
    session.commit()
    session.refresh(scene)
    return scene


def scene_file(
    session: Session, data_dir: Path, scene_id: uuid.UUID, kind: SceneFileKind
) -> tuple[Path, StoredFile]:
    file_id = getattr(get_scene(session, scene_id), _SCENE_FILE_COLUMNS[kind])
    if file_id is None:
        raise ApiError(404, "NOT_FOUND", "O cenário não tem esse arquivo.")
    stored = session.get(StoredFile, file_id)
    return resolve_path(data_dir, stored), stored
