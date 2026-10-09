import hashlib
import io
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.devseed import DevCatalog
from avatar_api.main import create_app
from avatar_api.models import RenderRecipe, StoredFile, VideoJob
from avatar_api.storage import resolve_path

PASSWORD = "senha-isolada-do-painel"
VIDEO = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 64


@pytest.fixture
def panel(settings: Settings, session: Session) -> Iterator[TestClient]:
    create_user(session, "painel", PASSWORD)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post(
            "/panel/auth/login", json={"username": "painel", "password": PASSWORD}
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield client


@pytest.fixture
def payload(seeded_catalog: DevCatalog) -> dict:
    return {
        "script_text": "Fala literal do teste.",
        "avatar_id": str(seeded_catalog.avatar_id),
        "scene_id": str(seeded_catalog.scene_id),
        "aspect_ratio": "16:9",
    }


def create(panel, payload, key="intencao-1"):
    response = panel.post("/panel/jobs", json=payload, headers={"Idempotency-Key": key})
    assert response.status_code == 202, response.text
    return response.json()


def finish(panel, settings, ident):
    headers = {"Authorization": f"Bearer {settings.worker_token}"}
    claim = panel.post(
        "/internal/v1/claim", headers=headers, json={"worker_id": "test-gpu", "kinds": ["video"]}
    ).json()
    assert claim["id"] == ident
    for name, content in [
        ("manifest.json", json.dumps({"audio_seconds": 1.2}).encode()),
        ("final.mp4", VIDEO),
    ]:
        response = panel.put(
            f"/internal/v1/jobs/{ident}/attempts/{claim['attempt_id']}/files/{name}",
            headers=headers,
            files={"file": (name, io.BytesIO(content))},
            data={
                "lease_generation": claim["lease_generation"],
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        )
        assert response.status_code == 201, response.text
    response = panel.post(
        f"/internal/v1/jobs/{ident}/complete",
        headers=headers,
        json={
            "attempt_id": claim["attempt_id"],
            "lease_generation": claim["lease_generation"],
            "result_file_id": response.json()["id"],
        },
    )
    assert response.status_code == 200, response.text


def test_rotas_de_jobs_exigem_cookie_e_csrf(client, payload):
    for path in (
        "/panel/jobs",
        f"/panel/jobs/{uuid.uuid4()}",
        "/panel/worker-status",
        "/panel/generation-config",
    ):
        assert client.get(path).status_code == 401
    assert client.post("/panel/jobs", json=payload).status_code == 401


def test_criacao_sem_csrf_nao_grava_job(panel, payload, session):
    csrf = panel.headers.pop("X-CSRF-Token")
    assert panel.post("/panel/jobs", json=payload).status_code == 403
    assert session.scalar(select(VideoJob)) is None
    panel.headers["X-CSRF-Token"] = csrf
    created = create(panel, payload)
    assert created["status_url"] == f"/panel/jobs/{created['id']}"
    assert panel.get(created["status_url"]).json()["script_text"] == payload["script_text"]


def test_intencao_idempotente_e_conflito_nao_duplicam(panel, payload, session):
    first = create(panel, payload)
    assert create(panel, payload)["id"] == first["id"]
    response = panel.post(
        "/panel/jobs",
        json={**payload, "script_text": "Outra fala."},
        headers={"Idempotency-Key": "intencao-1"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(list(session.scalars(select(VideoJob)))) == 1


def test_limites_config_sem_receita_e_receita_vigente(panel, payload, session, seeded_catalog):
    recipe = session.get(RenderRecipe, seeded_catalog.recipe_id)
    recipe.spec = {"limits": {"max_audio_seconds": 28, "chars_per_second": 12}}
    session.commit()
    assert panel.get("/panel/generation-config").json() == {
        "max_script_chars": recipe.max_script_chars,
        "max_audio_seconds": 28,
        "chars_per_second": 12,
    }
    response = panel.post(
        "/panel/jobs", json={**payload, "script_text": "x" * (recipe.max_script_chars + 1)}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCRIPT_TOO_LONG"
    recipe.is_current = False
    session.commit()
    assert panel.get("/panel/generation-config").json() == {
        "max_script_chars": None,
        "max_audio_seconds": None,
        "chars_per_second": None,
    }
    assert panel.post("/panel/jobs", json=payload).status_code == 503


def test_historia_equipe_inclui_origem_api_sem_quebrar_posse_publica(panel, payload, session):
    panel_job = create(panel, payload)
    user = create_user(session, "integrador", PASSWORD)
    key = issue_api_key(session, user.id, "ERP")
    headers = {"Authorization": f"Bearer {key.key}"}
    api_job = panel.post("/api/v1/jobs", json=payload, headers=headers)
    assert api_job.status_code == 202
    history = panel.get("/panel/jobs").json()
    assert {job["id"] for job in history} == {panel_job["id"], api_job.json()["id"]}
    assert {job["origin"] for job in history} == {"api", "panel"}
    assert {job["requested_by"] for job in history} == {"painel", "ERP"}
    assert panel.get(f"/api/v1/jobs/{panel_job['id']}", headers=headers).status_code == 404


def test_download_player_e_metadados_so_apos_publicacao(panel, payload, settings):
    created = create(panel, payload)
    ident = created["id"]
    response = panel.get(f"/panel/jobs/{ident}/download")
    assert response.status_code == 409
    queued = panel.get(created["status_url"]).json()
    assert queued["status"] == "queued" and queued["download_url"] is None
    finish(panel, settings, ident)
    ready = panel.get(created["status_url"]).json()
    assert ready["file_exists"] is True
    assert ready["duration_seconds"] == 1.2 and ready["size_bytes"] == len(VIDEO)
    assert (ready["aspect_ratio"], ready["voice"]) == ("16:9", "feminina")
    response = panel.get(ready["download_url"])
    assert response.status_code == 200 and response.content == VIDEO
    partial = panel.get(ready["download_url"], headers={"Range": "bytes=0-23"})
    assert partial.status_code == 206 and partial.content == VIDEO[:24]
    panel.post("/panel/auth/logout")
    assert panel.get(ready["download_url"]).status_code == 401


def test_arquivo_ausente_nao_promete_download(panel, payload, settings, session):
    ident = create(panel, payload)["id"]
    finish(panel, settings, ident)
    job = session.get(VideoJob, uuid.UUID(ident))
    stored = session.get(StoredFile, job.result_file_id)
    resolve_path(settings.data_dir, stored).unlink()
    detail = panel.get(f"/panel/jobs/{ident}").json()
    assert detail["file_exists"] is False and detail["download_url"] is None
    assert detail["duration_seconds"] is None
    assert panel.get(f"/panel/jobs/{ident}/download").status_code == 404


def test_falha_motivo_e_etapa_processando_persistem(panel, payload, settings, session):
    ident = create(panel, payload)["id"]
    headers = {"Authorization": f"Bearer {settings.worker_token}"}
    claimed = panel.post(
        "/internal/v1/claim", json={"worker_id": "gpu", "kinds": ["video"]}, headers=headers
    ).json()
    ref = {"attempt_id": claimed["attempt_id"], "lease_generation": claimed["lease_generation"]}
    assert (
        panel.post(
            f"/internal/v1/jobs/{ident}/heartbeat", headers=headers, json={**ref, "stage": "render"}
        ).status_code
        == 200
    )
    processing = panel.get(f"/panel/jobs/{ident}").json()
    assert processing["stage"] == "render" and processing["started_at"] is not None
    assert panel.get("/panel/worker-status").json()["last_heartbeat_at"] is not None
    response = panel.post(
        f"/internal/v1/jobs/{ident}/fail",
        headers=headers,
        json={
            **ref,
            "error_code": "RENDER_FAILED",
            "error_message": "Não foi possível animar.",
            "retryable": False,
        },
    )
    assert response.status_code == 200
    failure = panel.get(f"/panel/jobs/{ident}").json()
    assert failure["status"] == "failed" and failure["stage"] is None
    assert failure["error"] == {"code": "RENDER_FAILED", "message": "Não foi possível animar."}
    assert panel.get(f"/panel/jobs/{ident}/download").json()["error"]["code"] == "JOB_FAILED"


def test_ausencia_de_heartbeat_independe_de_receita(panel):
    assert panel.get("/panel/worker-status").json() == {"last_heartbeat_at": None}


def test_jobs_desconhecidos_retornam_404(panel):
    ident = uuid.uuid4()
    assert panel.get(f"/panel/jobs/{ident}").status_code == 404
    assert panel.get(f"/panel/jobs/{ident}/download").status_code == 404
