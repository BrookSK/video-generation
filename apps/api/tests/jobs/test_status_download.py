import hashlib
import io
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.devseed import DevCatalog
from avatar_api.models import ApiKey, StoredFile, VideoJob
from avatar_api.storage import save_stream

VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 64


@pytest.fixture
def api_key(session: Session) -> tuple[str, ApiKey]:
    user = create_user(session, "admin", "senha-de-teste-bem-longa")
    issued = issue_api_key(session, user.id, "ERP")
    return issued.key, issued.row


@pytest.fixture
def auth(api_key: tuple[str, ApiKey]) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key[0]}"}


@pytest.fixture
def other_auth(session: Session, api_key: tuple[str, ApiKey]) -> dict[str, str]:
    other = issue_api_key(session, api_key[1].created_by_user_id, "CRM")
    return {"Authorization": f"Bearer {other.key}"}


@pytest.fixture
def job_id(client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog) -> uuid.UUID:
    response = client.post(
        "/api/v1/jobs",
        json={
            "script_text": "Olá, este é o vídeo de teste.",
            "avatar_id": str(seeded_catalog.avatar_id),
            "scene_id": str(seeded_catalog.scene_id),
        },
        headers=auth,
    )
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()["id"])


def set_job(session: Session, job_id: uuid.UUID, **values) -> VideoJob:
    session.execute(update(VideoJob).where(VideoJob.id == job_id).values(**values))
    session.commit()
    job = session.get(VideoJob, job_id)
    session.refresh(job)
    return job


def make_ready(session: Session, settings: Settings, job_id: uuid.UUID) -> StoredFile:
    stored = save_stream(
        session,
        settings.data_dir,
        f"jobs/{job_id}/attempt-1",
        "final.mp4",
        io.BytesIO(VIDEO_BYTES),
        hashlib.sha256(VIDEO_BYTES).hexdigest(),
        "video/mp4",
    )
    set_job(
        session,
        job_id,
        status="ready",
        stage="upload",
        result_file_id=stored.id,
        finished_at=func.now(),
    )
    return stored


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    error = dict(response.json()["error"])
    assert error["code"] == code
    error.pop("request_id")
    return error


# --- GET /api/v1/jobs/{id} nos quatro estados -----------------------------------------


def test_status_queued(client: TestClient, auth: dict[str, str], job_id: uuid.UUID, session):
    response = client.get(f"/api/v1/jobs/{job_id}", headers=auth)

    assert response.status_code == 200, response.text
    data = response.json()
    job = session.get(VideoJob, job_id)
    assert data == {
        "id": str(job_id),
        "status": "queued",
        "stage": None,
        "aspect_ratio": "9:16",
        "created_at": data["created_at"],
        "finished_at": None,
        "error": None,
        "status_url": f"/api/v1/jobs/{job_id}",
        "download_url": None,
    }
    assert datetime.fromisoformat(data["created_at"]) == job.created_at


def test_status_processing_mostra_a_etapa(
    client: TestClient, auth: dict[str, str], job_id: uuid.UUID, session: Session
):
    set_job(session, job_id, status="processing", stage="render", attempt=1, lease_generation=1)

    data = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()

    assert (data["status"], data["stage"]) == ("processing", "render")
    assert data["error"] is None
    assert data["download_url"] is None
    assert data["finished_at"] is None


def test_status_failed_mostra_codigo_e_mensagem(
    client: TestClient, auth: dict[str, str], job_id: uuid.UUID, session: Session
):
    job = set_job(
        session,
        job_id,
        status="failed",
        stage="render",
        error_code="WORKER_LOST",
        error_message="O worker parou de responder.",
        finished_at=func.now(),
    )

    data = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()

    assert data["status"] == "failed"
    assert data["stage"] is None
    assert data["error"] == {"code": "WORKER_LOST", "message": "O worker parou de responder."}
    assert datetime.fromisoformat(data["finished_at"]) == job.finished_at
    assert data["download_url"] is None


def test_status_ready_mostra_download_url(
    client: TestClient,
    auth: dict[str, str],
    job_id: uuid.UUID,
    session: Session,
    settings: Settings,
):
    make_ready(session, settings, job_id)

    data = client.get(f"/api/v1/jobs/{job_id}", headers=auth).json()

    assert data["status"] == "ready"
    assert data["stage"] is None
    assert data["error"] is None
    assert data["finished_at"] is not None
    assert data["download_url"] == f"/api/v1/jobs/{job_id}/download"


# --- 404 para job de outra chave ou inexistente ---------------------------------------


@pytest.mark.parametrize("suffix", ["", "/download"], ids=["status", "download"])
def test_job_de_outra_chave_ou_inexistente_responde_404_igual(
    client: TestClient,
    auth: dict[str, str],
    other_auth: dict[str, str],
    job_id: uuid.UUID,
    session: Session,
    settings: Settings,
    suffix: str,
):
    make_ready(session, settings, job_id)

    of_other_key = client.get(f"/api/v1/jobs/{job_id}{suffix}", headers=other_auth)
    missing = client.get(f"/api/v1/jobs/{uuid.uuid4()}{suffix}", headers=other_auth)

    assert assert_error(of_other_key, 404, "NOT_FOUND") == assert_error(missing, 404, "NOT_FOUND")
    assert str(job_id) not in of_other_key.text
    # A dona do job continua vendo o próprio job.
    assert client.get(f"/api/v1/jobs/{job_id}{suffix}", headers=auth).status_code == 200


# --- download --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["queued", "processing"])
def test_download_fora_de_ready_responde_409_com_o_status(
    client: TestClient, auth: dict[str, str], job_id: uuid.UUID, session: Session, status: str
):
    if status == "processing":
        set_job(session, job_id, status="processing", stage="tts", attempt=1, lease_generation=1)

    response = client.get(f"/api/v1/jobs/{job_id}/download", headers=auth)

    error = assert_error(response, 409, "JOB_NOT_READY")
    assert f"Status atual: {status}." in error["message"]
    assert "content-disposition" not in response.headers


def test_download_de_job_failed_responde_409_com_o_motivo(
    client: TestClient, auth: dict[str, str], job_id: uuid.UUID, session: Session
):
    set_job(
        session,
        job_id,
        status="failed",
        error_code="RENDER_FAILED",
        error_message="Falha ao renderizar.",
        finished_at=func.now(),
    )

    response = client.get(f"/api/v1/jobs/{job_id}/download", headers=auth)

    error = assert_error(response, 409, "JOB_FAILED")
    assert "RENDER_FAILED" in error["message"]
    assert "Falha ao renderizar." in error["message"]


def test_download_em_ready_entrega_o_arquivo(
    client: TestClient,
    auth: dict[str, str],
    api_key: tuple[str, ApiKey],
    job_id: uuid.UUID,
    session: Session,
    settings: Settings,
):
    stored = make_ready(session, settings, job_id)

    response = client.get(f"/api/v1/jobs/{job_id}/download", headers=auth)

    assert response.status_code == 200
    assert response.content == VIDEO_BYTES
    assert hashlib.sha256(response.content).hexdigest() == stored.sha256
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-disposition"] == f'attachment; filename="video-{job_id}.mp4"'

    # Nada de caminho no volume, hash ou prefixo da chave nas respostas públicas.
    status = client.get(f"/api/v1/jobs/{job_id}", headers=auth)
    public = status.text + str(status.headers) + str(response.headers)
    key_row = session.get(ApiKey, api_key[1].id)
    for internal in (
        stored.relative_path,
        str(settings.data_dir),
        "attempt-1",
        key_row.key_hash,
        key_row.prefix,
    ):
        assert internal not in public
