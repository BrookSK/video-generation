import io
from collections.abc import Callable

import pytest
from PIL import Image

_PILLOW_FORMATS = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}

ImageBytes = Callable[..., bytes]


@pytest.fixture
def image_bytes() -> ImageBytes:
    """Gera em memória uma imagem JPEG, PNG ou WebP: image_bytes(fmt, size, alpha)."""

    def make(fmt: str, size: tuple[int, int] = (64, 48), alpha: bool = False) -> bytes:
        mode = "RGBA" if alpha else "RGB"
        color = (200, 120, 40, 128) if alpha else (200, 120, 40)
        buffer = io.BytesIO()
        Image.new(mode, size, color).save(buffer, format=_PILLOW_FORMATS[fmt])
        return buffer.getvalue()

    return make
