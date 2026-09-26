import io
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from avatar_api.auth import CSRF_HEADER, create_user
from avatar_api.config import Settings
from avatar_api.main import create_app

_PILLOW_FORMATS = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}

PANEL_USERNAME = "painel"
PANEL_PASSWORD = "senha-do-painel-de-teste"

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


@pytest.fixture
def panel(settings: Settings, session: Session) -> Iterator[TestClient]:
    """Cliente já logado no painel, com o cookie de sessão e o cabeçalho X-CSRF-Token."""
    create_user(session, PANEL_USERNAME, PANEL_PASSWORD)
    # O cookie de sessão é Secure: o cliente precisa falar HTTPS para reenviá-lo.
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post(
            "/panel/auth/login", json={"username": PANEL_USERNAME, "password": PANEL_PASSWORD}
        )
        assert response.status_code == 200, response.text
        client.headers[CSRF_HEADER] = response.json()["csrf_token"]
        yield client
