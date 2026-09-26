import socket
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.db import get_engine
from avatar_api.devseed import DevCatalog
from avatar_api.main import create_app
from avatar_api.models import VideoJob

GHOST_USER = "usuario_fantasma"
GHOST_PASSWORD = "senha_fantasma"


def closed_port() -> int:
    """Porta local livre: reservada e liberada em seguida, então ninguém escuta nela."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def job_count(session: Session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(VideoJob))


def assert_no_driver_detail(response, port: int) -> None:
    text = response.text
    for leaked in ("127.0.0.1", "localhost", str(port), GHOST_USER, GHOST_PASSWORD):
        assert leaked not in text
    for leaked in ("psycopg", "OperationalError", "connection", "refused", "Traceback"):
        assert leaked.lower() not in text.lower()


@pytest.fixture
def port() -> int:
    return closed_port()


@pytest.fixture
def offline_client(settings: Settings, port: int) -> Iterator[TestClient]:
    """Segundo app, igual ao de teste mas com DATABASE_URL numa porta fechada."""
    url = f"postgresql+psycopg://{GHOST_USER}:{GHOST_PASSWORD}@127.0.0.1:{port}/avatar"
    with TestClient(create_app(replace(settings, database_url=url))) as client:
        yield client
    get_engine(url).dispose()


@pytest.fixture
def api_key(session: Session) -> str:
    user = create_user(session, "admin", "senha-de-teste-bem-longa")
    return issue_api_key(session, user.id, "ERP").key


def test_post_de_job_sem_banco_responde_503_sem_gravar(
    client: TestClient,
    offline_client: TestClient,
    session: Session,
    seeded_catalog: DevCatalog,
    api_key: str,
    port: int,
):
    body = {
        "script_text": "Olá, este é o vídeo de teste.",
        "avatar_id": str(seeded_catalog.avatar_id),
        "scene_id": str(seeded_catalog.scene_id),
    }
    auth = {"Authorization": f"Bearer {api_key}"}
    # Um job gravado pelo app com banco: a contagem de referência não parte de zero.
    assert client.post("/api/v1/jobs", json=body, headers=auth).status_code == 202
    before = job_count(session)
    assert before == 1

    response = offline_client.post(
        "/api/v1/jobs", json=body, headers={**auth, "X-Request-ID": "req-sem-banco"}
    )
    print("POST /api/v1/jobs sem banco:", response.status_code, response.text)

    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error["code"] == "SERVICE_UNAVAILABLE"
    assert error["message"]
    assert error["request_id"] == "req-sem-banco"
    assert response.headers["X-Request-ID"] == "req-sem-banco"
    assert_no_driver_detail(response, port)

    after = job_count(session)
    print("video_jobs antes/depois:", before, after)
    assert after == before


def test_healthz_continua_200_e_readyz_503_sem_banco(offline_client: TestClient, port: int):
    health = offline_client.get("/healthz")
    print("GET /healthz sem banco:", health.status_code, health.text)
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    ready = offline_client.get("/readyz")
    print("GET /readyz sem banco:", ready.status_code, ready.text)
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable", "database": "error", "storage": "ok"}
    assert_no_driver_detail(ready, port)


def test_readyz_200_com_banco_e_volume(client: TestClient, settings: Settings):
    response = client.get("/readyz")
    print("GET /readyz com banco:", response.status_code, response.text)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "storage": "ok"}
    assert list(Path(settings.data_dir).iterdir()) == []


def test_readyz_503_com_data_dir_sem_escrita(client: TestClient, settings: Settings):
    settings.data_dir.chmod(0o555)
    try:
        response = client.get("/readyz")
        health = client.get("/healthz")
    finally:
        settings.data_dir.chmod(0o755)
    print("GET /readyz sem escrita:", response.status_code, response.text)
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "ok", "storage": "error"}
    assert health.status_code == 200
