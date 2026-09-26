"""Preparação do avatar: recorte com alfa, corte pela caixa do alfa e prévias 9:16 e 16:9."""

import io
from collections.abc import Callable
from typing import Any

from PIL import Image, ImageOps

from avatar_worker import cutout
from avatar_worker.canvas import compose_canvas

STAGE_COLOR = "#1F1C3F"
# Nome do arquivo da tentativa -> tamanho e enquadramento padrão do devseed.
PREVIEWS: dict[str, tuple[tuple[int, int], dict[str, float]]] = {
    "preview-9x16.png": ((540, 960), {"scale": 0.8, "x": 0.5, "y": 1.0}),
    "preview-16x9.png": ((960, 540), {"scale": 0.9, "x": 0.5, "y": 1.0}),
}


class PrepareInputError(ValueError):
    """A imagem de origem não serve para avatar; reenviar a mesma não adianta."""


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _open(source_bytes: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(source_bytes))
        image.load()
        return ImageOps.exif_transpose(image)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise PrepareInputError("Não foi possível ler a imagem de origem.") from exc


def prepare_avatar(
    source_bytes: bytes, session_factory: Callable[[str], Any] = cutout.local_session
) -> dict[str, bytes]:
    """Devolve prepared.png e as duas prévias em PNG, pelo nome do arquivo da tentativa.

    PNG com alfa útil passa sem recorte. Levanta PrepareInputError para imagem ilegível ou
    sem pessoa, e cutout.CutoutError quando o recorte não pode rodar.
    """
    image = cutout.ensure_alpha(_open(source_bytes), session_factory).convert("RGBA")
    box = image.getchannel("A").getbbox()
    if box is None:
        raise PrepareInputError("Nenhuma pessoa encontrada na imagem.")
    avatar = image.crop(box)
    files = {"prepared.png": _png(avatar)}
    for name, (size, composition) in PREVIEWS.items():
        files[name] = _png(compose_canvas(avatar, STAGE_COLOR, composition, size))
    return files
