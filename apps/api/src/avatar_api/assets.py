"""Avatares, cenários e identidade visual do painel: cadastro, listagem e arquivos.

Arquivo de asset é imutável: não há edição; para trocar, a pessoa arquiva e cadastra outro.
Na identidade, trocar o logo grava um arquivo novo e o anterior continua no volume.
"""

import hashlib
import io
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from avatar_api.errors import ApiError
from avatar_api.models import (
    ASPECT_RATIOS,
    AssetPrepareTask,
    Avatar,
    BrandIdentity,
    Scene,
    StoredFile,
)
from avatar_api.storage import resolve_path, save_stream
from avatar_api.uploads import ValidatedImage, render_previews

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
# O close aproxima o apresentador: escala maior e base abaixo do canvas.
_CLOSE_RANGES: dict[str, tuple[str, float, float]] = {
    "scale": ("escala", 0.3, 2.5),
    "x": ("posição horizontal", 0.0, 1.0),
    "y": ("base", 0.5, 2.5),
}
CLOSE_KEY = "close"

# Plano médio por formato e, opcional, "close" com o mesmo formato por dentro.
Framing = dict[str, float]
Composition = dict[str, Framing | dict[str, Framing]]


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


def _parse_framings(
    data: Any, label: str, ranges: dict[str, tuple[str, float, float]]
) -> dict[str, Framing]:
    composition: dict[str, Framing] = {}
    for ratio in ASPECT_RATIOS:
        framing = data[ratio]
        if not isinstance(framing, dict) or set(framing) != set(ranges):
            raise _composition_error(f"{label} {ratio}: informe escala, posição e base.")
        composition[ratio] = {}
        for key, (name, low, high) in ranges.items():
            value = framing[key]
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise _composition_error(f"{label} {ratio}: {name} precisa ser um número.")
            if not (math.isfinite(value) and low <= value <= high):
                raise _composition_error(
                    f"{label} {ratio}: {name} {_decimal(value)} fora da faixa de "
                    f"{_decimal(low)} a {_decimal(high)}."
                )
            composition[ratio][key] = float(value)
    return composition


def parse_composition(raw: str) -> Composition:
    """Lê o enquadramento em JSON: exatamente 9:16 e 16:9, cada um com scale, x e y na faixa.

    A chave opcional "close" traz o enquadramento fechado dos dois formatos, com faixas
    próprias; sem ela, o worker deriva o close do plano médio.
    """
    try:
        data: Any = json.loads(raw)
    except ValueError:
        raise _composition_error("Enquadramento inválido.") from None
    if not isinstance(data, dict) or set(data) - {CLOSE_KEY} != set(ASPECT_RATIOS):
        raise _composition_error("Informe o enquadramento de 9:16 e de 16:9.")
    composition: Composition = dict(_parse_framings(data, "Enquadramento", _COMPOSITION_RANGES))
    if CLOSE_KEY in data:
        close = data[CLOSE_KEY]
        if not isinstance(close, dict) or set(close) != set(ASPECT_RATIOS):
            raise _composition_error("Informe o close de 9:16 e de 16:9.")
        composition[CLOSE_KEY] = _parse_framings(close, "Close", _CLOSE_RANGES)
    return composition


def scene_status(scene: Scene) -> SceneStatus:
    return "arquivado" if scene.archived_at is not None else "ativo"


def _scene_previews(background_color: str | None, image: ValidatedImage | None) -> dict[str, bytes]:
    """PNG de cada formato: o fundo ajustado por cover e centralizado, ou a cor sólida.

    A imagem enviada só é decodificada no subprocesso limitado de uploads; a cor sólida,
    que não vem de arquivo, é desenhada aqui.
    """
    if image is not None:
        return render_previews(image.path, _SCENE_PREVIEWS, "file")
    previews = {}
    for kind, size in _SCENE_PREVIEWS.items():
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
    composition: Composition,
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


# --- identidade visual ------------------------------------------------------------------

BRAND_IDENTITY_ID = 1
_LOGO_TYPES = frozenset({"image/png", "image/jpeg"})


def _invalid_logo() -> ApiError:
    return ApiError(422, "UNSUPPORTED_FILE_TYPE", "Envie o logo em PNG ou JPEG.", "logo")


def _valid_color(value: str, field: str) -> str:
    if not HEX_COLOR.fullmatch(value):
        raise ApiError(422, "VALIDATION_ERROR", "Use uma cor no formato #RRGGBB.", field)
    return value


def get_brand_identity(session: Session) -> BrandIdentity | None:
    return session.get(BrandIdentity, BRAND_IDENTITY_ID)


def save_brand_identity(
    session: Session,
    data_dir: Path,
    user_id: uuid.UUID,
    background_color: str,
    accent_color: str,
    logo: ValidatedImage | None = None,
) -> BrandIdentity:
    """Grava as cores e, se vier, o logo novo; autor e data vão junto, num único commit.

    Sem logo, só troca as cores da identidade já cadastrada; o primeiro cadastro exige o
    logo. O logo novo vira um arquivo novo em brand/<id>/: o anterior continua no volume,
    porque as aulas já criadas guardam o ID dele. Se qualquer passo falhar, nada fica.
    """
    colors = {
        "background_color": _valid_color(background_color, "background_color"),
        "accent_color": _valid_color(accent_color, "accent_color"),
    }
    if logo is not None and logo.content_type not in _LOGO_TYPES:
        raise _invalid_logo()
    changes = {**colors, "updated_by_user_id": user_id, "updated_at": func.now()}
    try:
        if logo is None:
            updated = session.execute(
                update(BrandIdentity)
                .where(BrandIdentity.id == BRAND_IDENTITY_ID)
                .values(**changes)
            )
            if updated.rowcount == 0:
                raise ApiError(422, "VALIDATION_ERROR", "Envie o logo em PNG ou JPEG.", "logo")
        else:
            with logo.path.open("rb") as stream:
                stored = save_stream(
                    session,
                    data_dir,
                    f"brand/{uuid.uuid4()}",
                    f"logo{logo.extension}",
                    stream,
                    logo.sha256,
                    logo.content_type,
                    commit=False,
                )
            changes["logo_file_id"] = stored.id
            # Upsert da linha única: dois primeiros cadastros simultâneos não colidem.
            session.execute(
                insert(BrandIdentity)
                .values(id=BRAND_IDENTITY_ID, **changes)
                .on_conflict_do_update(index_elements=[BrandIdentity.id], set_=changes)
            )
        session.commit()
    except BaseException:
        session.rollback()
        raise
    identity = get_brand_identity(session)
    session.refresh(identity)
    return identity


def brand_logo(session: Session, data_dir: Path) -> tuple[Path, StoredFile]:
    identity = get_brand_identity(session)
    if identity is None:
        raise ApiError(404, "NOT_FOUND", "Nenhum logo cadastrado.")
    stored = session.get(StoredFile, identity.logo_file_id)
    return resolve_path(data_dir, stored), stored


# --- listagem pública -------------------------------------------------------------------

# Prévia por formato; avatar e cenário usam as mesmas colunas.
_PREVIEW_COLUMNS: dict[str, str] = {
    "9:16": "preview_9x16_file_id",
    "16:9": "preview_16x9_file_id",
}


def _public_avatars():
    return select(Avatar).where(Avatar.prepare_status == "ativo", Avatar.archived_at.is_(None))


def _public_scenes():
    return select(Scene).where(Scene.archived_at.is_(None))


def list_public_avatars(session: Session) -> list[Avatar]:
    """Só avatares ativos e não arquivados: os únicos aceitos na criação de job."""
    query = _public_avatars().order_by(Avatar.name, Avatar.created_at, Avatar.id)
    return list(session.scalars(query))


def list_public_scenes(session: Session) -> list[Scene]:
    query = _public_scenes().order_by(Scene.name, Scene.created_at, Scene.id)
    return list(session.scalars(query))


def public_preview(
    session: Session,
    data_dir: Path,
    kind: Literal["avatar", "scene"],
    item_id: uuid.UUID,
    aspect_ratio: str,
) -> tuple[Path, StoredFile]:
    """Prévia do formato pedido; item arquivado, inativo, inexistente ou sem prévia dá 404."""
    if kind == "avatar":
        item = session.scalar(_public_avatars().where(Avatar.id == item_id))
        label = "Avatar"
    else:
        item = session.scalar(_public_scenes().where(Scene.id == item_id))
        label = "Cenário"
    file_id = getattr(item, _PREVIEW_COLUMNS[aspect_ratio]) if item is not None else None
    if file_id is None:
        raise ApiError(404, "NOT_FOUND", f"{label} não encontrado.")
    stored = session.get(StoredFile, file_id)
    return resolve_path(data_dir, stored), stored
