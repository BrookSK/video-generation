"""Painel logado, identidade visual e corpo de aula para os testes de aula."""

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from avatar_api.auth import CSRF_HEADER, create_user
from avatar_api.config import Settings
from avatar_api.devseed import DevCatalog
from avatar_api.main import create_app

LESSON_USER = "painel-aulas"
LESSON_PASSWORD = "senha-isolada-das-aulas"
SCENE_TEXTS = ("Primeira cena da aula.", "Segunda cena, em close.", "Terceira e última cena.")


def logo_png(color: tuple[int, int, int] = (240, 240, 240)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (160, 60), color).save(buffer, format="PNG")
    return buffer.getvalue()


def put_identity(client: TestClient, logo: bytes | None, background: str, accent: str):
    files = {"logo": ("logo.png", logo, "image/png")} if logo is not None else None
    response = client.put(
        "/panel/brand-identity",
        data={"background_color": background, "accent_color": accent},
        files=files,
    )
    assert response.status_code == 200, response.text
    return response.json()


def lesson_body(catalog: DevCatalog, shots=("medio", "close", "medio"), **overrides) -> dict:
    return {
        "avatar_id": str(catalog.avatar_id),
        "scene_id": str(catalog.scene_id),
        "aspect_ratio": "16:9",
        "scenes": [
            {"script_text": text, "shot": shot}
            for text, shot in zip(SCENE_TEXTS, shots, strict=False)
        ],
        **overrides,
    }


@pytest.fixture
def lesson_panel(settings: Settings, session: Session) -> Iterator[TestClient]:
    create_user(session, LESSON_USER, LESSON_PASSWORD)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post(
            "/panel/auth/login", json={"username": LESSON_USER, "password": LESSON_PASSWORD}
        )
        assert response.status_code == 200, response.text
        client.headers[CSRF_HEADER] = response.json()["csrf_token"]
        yield client


@pytest.fixture
def brand(lesson_panel: TestClient) -> dict:
    return put_identity(lesson_panel, logo_png(), "#0B2545", "#F2A541")
