"""Catálogo mínimo de desenvolvimento: receita dev-seed, um avatar ativo e um cenário.

Serve aos testes e à stack de desenvolvimento; nunca roda no servidor do cliente.
"""

import hashlib
import io
import struct
import uuid
import zlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from avatar_api.models import Avatar, RenderRecipe, Scene, StoredFile
from avatar_api.storage import save_stream

RECIPE_NAME = "dev-seed"
RECIPE_MAX_SCRIPT_CHARS = 600
AVATAR_NAME = "Avatar de desenvolvimento"
SCENE_NAME = "Cenário de desenvolvimento"
SEED_DIR = "seed"


@dataclass(frozen=True)
class DevCatalog:
    recipe_id: uuid.UUID
    avatar_id: uuid.UUID
    scene_id: uuid.UUID

    def as_json(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def _png(width: int, height: int, pixel: Callable[[int, int], tuple[int, int, int, int]]) -> bytes:
    """PNG RGBA gerado sem biblioteca de imagem; pixel(x, y) devolve (r, g, b, a)."""
    rows = b"".join(
        b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def _in_silhouette(x: int, y: int) -> bool:
    head = (x - 32) ** 2 + (y - 20) ** 2 <= 12**2
    body = 14 <= x <= 50 and y >= 34
    return head or body


def _source_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    return (224, 172, 105, 255) if _in_silhouette(x, y) else (200, 200, 200, 255)


def _prepared_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    return (224, 172, 105, 255) if _in_silhouette(x, y) else (0, 0, 0, 0)


def _seed_file(session: Session, data_dir: Path, name: str, data: bytes) -> StoredFile:
    relative_path = f"{SEED_DIR}/{name}"
    existing = session.scalar(select(StoredFile).where(StoredFile.relative_path == relative_path))
    if existing is not None:
        return existing
    sha256 = hashlib.sha256(data).hexdigest()
    return save_stream(session, data_dir, SEED_DIR, name, io.BytesIO(data), sha256, "image/png")


def _seed_recipe(session: Session) -> RenderRecipe:
    recipe = session.scalar(select(RenderRecipe).where(RenderRecipe.name == RECIPE_NAME))
    if recipe is None:
        recipe = RenderRecipe(
            name=RECIPE_NAME,
            max_script_chars=RECIPE_MAX_SCRIPT_CHARS,
            spec={"development": True, "description": "Receita mínima só para desenvolvimento."},
        )
        session.add(recipe)
    # Só assume a vigência se nenhuma outra receita for a vigente.
    if not recipe.is_current:
        current = session.scalar(select(RenderRecipe.id).where(RenderRecipe.is_current))
        recipe.is_current = current is None
    session.flush()
    return recipe


def _seed_avatar(session: Session, data_dir: Path) -> Avatar:
    avatar = session.scalar(select(Avatar).where(Avatar.name == AVATAR_NAME))
    if avatar is not None:
        return avatar
    source = _seed_file(session, data_dir, "avatar-source.png", _png(64, 64, _source_pixel))
    prepared = _seed_file(session, data_dir, "avatar-prepared.png", _png(64, 64, _prepared_pixel))
    avatar = Avatar(
        name=AVATAR_NAME,
        voice="feminina",
        source_file_id=source.id,
        prepared_file_id=prepared.id,
        prepare_status="ativo",
    )
    session.add(avatar)
    session.flush()
    return avatar


def _seed_scene(session: Session) -> Scene:
    scene = session.scalar(select(Scene).where(Scene.name == SCENE_NAME))
    if scene is not None:
        return scene
    scene = Scene(
        name=SCENE_NAME,
        background_color="#1f2937",
        composition={
            "9:16": {"scale": 0.8, "x": 0.5, "y": 1.0},
            "16:9": {"scale": 0.9, "x": 0.5, "y": 1.0},
        },
    )
    session.add(scene)
    session.flush()
    return scene


def seed_dev_catalog(session: Session, data_dir: Path) -> DevCatalog:
    """Cria, sem duplicar em execuções repetidas, a receita, o avatar e o cenário de dev."""
    recipe = _seed_recipe(session)
    avatar = _seed_avatar(session, data_dir)
    scene = _seed_scene(session)
    session.commit()
    return DevCatalog(recipe_id=recipe.id, avatar_id=avatar.id, scene_id=scene.id)
