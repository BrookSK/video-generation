from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.main import create_app
from avatar_api.models import WorkerHeartbeat


@pytest.fixture
def auth(session: Session) -> dict[str, str]:
    user = create_user(session, "admin", "senha-de-teste-bem-longa")
    key = issue_api_key(session, user.id, "ERP")
    return {"Authorization": f"Bearer {key.key}"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer invalida"},
        {"Authorization": "Bearer token-do-worker-de-teste"},
    ],
)
def test_presenca_exige_chave_publica(client: TestClient, headers: dict[str, str]):
    response = client.get("/api/v1/worker-status", headers=headers)
    assert response.status_code == 401


def test_presenca_nunca_vista_e_cpu_only_sao_null(
    client: TestClient, auth: dict[str, str], settings: Settings
):
    response = client.get("/api/v1/worker-status", headers=auth)
    assert response.status_code == 200
    assert response.json() == {"last_heartbeat_at": None}
    response = client.post(
        "/internal/v1/claim",
        headers={"Authorization": f"Bearer {settings.worker_token}"},
        json={"worker_id": "cpu", "kinds": ["asset_prepare"]},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/worker-status", headers=auth).json() == {"last_heartbeat_at": None}


def test_presenca_ociosa_publica_sobrevive_reinicio_sem_expor_worker(
    client: TestClient, auth: dict[str, str], settings: Settings, engine: Engine
):
    response = client.post(
        "/internal/v1/claim",
        headers={"Authorization": f"Bearer {settings.worker_token}"},
        json={"worker_id": "gpu-identidade-privada", "kinds": ["video"]},
    )
    assert response.status_code == 204
    with Session(engine) as reader:
        observed = reader.get(WorkerHeartbeat, "gpu-identidade-privada").last_heartbeat_at
    with TestClient(create_app(settings)) as restarted:
        response = restarted.get("/api/v1/worker-status", headers=auth)
    assert response.status_code == 200
    assert set(response.json()) == {"last_heartbeat_at"}
    assert datetime.fromisoformat(response.json()["last_heartbeat_at"]) == observed
