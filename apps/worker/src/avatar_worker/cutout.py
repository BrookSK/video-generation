"""Recorte do avatar com rembg e o modelo birefnet-portrait, sem download."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image
from rembg import new_session, remove

MODEL_NAME = "birefnet-portrait"


class CutoutError(RuntimeError):
    """O recorte não pode rodar, por exemplo sem o modelo em U2NET_HOME."""


def local_session(model_name: str) -> Any:
    """Abre a sessão do rembg só se o modelo já estiver em U2NET_HOME, para nunca baixar."""
    home = os.environ.get("U2NET_HOME")
    if not home:
        raise CutoutError("U2NET_HOME não definido; o recorte não baixa modelos")
    model_path = Path(home) / f"{model_name}.onnx"
    if not model_path.is_file():
        raise CutoutError(f"modelo de recorte ausente em {model_path}")
    return new_session(model_name)


def _has_useful_alpha(image: Image.Image) -> bool:
    if image.mode not in ("RGBA", "LA", "PA") and "transparency" not in image.info:
        return False
    low, _ = image.convert("RGBA").getchannel("A").getextrema()
    return low < 255


def ensure_alpha(
    image: Image.Image, session_factory: Callable[[str], Any] = local_session
) -> Image.Image:
    """Devolve a imagem como está se já tiver alfa útil; senão recorta com birefnet-portrait."""
    if _has_useful_alpha(image):
        return image
    session = session_factory(MODEL_NAME)
    return remove(image.convert("RGB"), session=session)
