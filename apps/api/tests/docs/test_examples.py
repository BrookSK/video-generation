import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy.orm import Session

from avatar_api.auth import create_user, issue_api_key
from avatar_api.main import create_app
from avatar_api.models import RenderRecipe

ROOT = Path(__file__).resolve().parents[4]
CONTRACT = json.loads((ROOT / "docs/api/openapi.json").read_text())
GUIDE = (ROOT / "docs/api/GUIA.md").read_text()
EXAMPLES = re.findall(
    r"<!-- example: (request|response) (GET|POST) (\S+)(?: (\d+))? -->\s*```json\s*(.*?)\s*```",
    GUIDE,
    re.DOTALL,
)


def validate(value, path, method, status=None):
    operation = CONTRACT["paths"][path][method.lower()]
    selected = (
        operation["requestBody"]["content"]["application/json"]["schema"]
        if status is None
        else operation["responses"][str(status)]["content"]["application/json"]["schema"]
    )
    Draft202012Validator({**CONTRACT, **selected}, format_checker=FormatChecker()).validate(value)


def test_export_corresponde_ao_contrato_da_aplicacao():
    assert CONTRACT == create_app().openapi()


@pytest.mark.parametrize("kind,method,path,status,body", EXAMPLES)
def test_exemplo_publicado_valida_com_openapi(kind, method, path, status, body):
    validate(json.loads(body), path, method, status if kind == "response" else None)


def test_contrato_publico_documenta_auth_e_midia_binaria_sem_json_falso():
    assert CONTRACT["components"]["securitySchemes"]["ApiKeyBearer"]["scheme"] == "bearer"
    for path, methods in CONTRACT["paths"].items():
        if path.startswith("/api/v1/"):
            for operation in methods.values():
                assert operation["security"] == [{"ApiKeyBearer": []}]
    download = CONTRACT["paths"]["/api/v1/jobs/{job_id}/download"]["get"]["responses"]
    assert set(download["200"]["content"]) == {"video/mp4"}
    assert download["206"]["content"]["video/mp4"]["schema"]["format"] == "binary"


def test_consumidor_http_valida_auth_limite_intencao_e_falha_real(
    client, session: Session, seeded_catalog, settings
):
    user = create_user(session, "docs", "isolated-docs-password")
    issued = issue_api_key(session, user.id, "Consumidor do guia")
    auth = {"Authorization": f"Bearer {issued.key}"}
    payload = {
        "script_text": "  Fala literal.\n",
        "avatar_id": str(seeded_catalog.avatar_id),
        "scene_id": str(seeded_catalog.scene_id),
    }
    for path in ("/api/v1/avatars", "/api/v1/scenes", "/api/v1/worker-status"):
        response = client.get(path)
        assert response.status_code == 401
        validate(response.json(), path, "GET", 401)
        response = client.get(path, headers=auth)
        assert response.status_code == 200
        validate(response.json(), path, "GET", 200)
    key = {**auth, "Idempotency-Key": "intencao-documentada"}
    created = client.post("/api/v1/jobs", json=payload, headers=key)
    assert created.status_code == 202
    validate(created.json(), "/api/v1/jobs", "POST", 202)
    assert (
        client.post("/api/v1/jobs", json=payload, headers=key).json()["id"] == created.json()["id"]
    )
    conflict = client.post(
        "/api/v1/jobs", json={**payload, "script_text": "Outra fala"}, headers=key
    )
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    )
    validate(conflict.json(), "/api/v1/jobs", "POST", 409)
    recipe = session.get(RenderRecipe, seeded_catalog.recipe_id)
    too_long = client.post(
        "/api/v1/jobs",
        json={**payload, "script_text": "x" * (recipe.max_script_chars + 1)},
        headers=auth,
    )
    assert too_long.status_code == 422 and too_long.json()["error"]["code"] == "SCRIPT_TOO_LONG"
    validate(too_long.json(), "/api/v1/jobs", "POST", 422)
    status_url = created.json()["status_url"]
    queued = client.get(status_url, headers=auth)
    validate(queued.json(), "/api/v1/jobs/{job_id}", "GET", 200)
    assert queued.json()["status"] == "queued" and queued.json()["aspect_ratio"] == "9:16"
    pending = client.get(status_url + "/download", headers=auth)
    assert pending.status_code == 409
    validate(pending.json(), "/api/v1/jobs/{job_id}/download", "GET", 409)
    worker_auth = {"Authorization": f"Bearer {settings.worker_token}"}
    claim = client.post(
        "/internal/v1/claim", json={"worker_id": "docs", "kinds": ["video"]}, headers=worker_auth
    ).json()
    ref = {"attempt_id": claim["attempt_id"], "lease_generation": claim["lease_generation"]}
    heartbeat = client.post(
        status_url.replace("/api/v1", "/internal/v1") + "/heartbeat",
        headers=worker_auth,
        json={**ref, "stage": "tts"},
    )
    assert heartbeat.status_code == 200
    processing = client.get(status_url, headers=auth)
    validate(processing.json(), "/api/v1/jobs/{job_id}", "GET", 200)
    assert processing.json()["status"] == "processing" and processing.json()["stage"] == "tts"
    failed = client.post(
        status_url.replace("/api/v1", "/internal/v1") + "/fail",
        headers=worker_auth,
        json={
            **ref,
            "error_code": "RENDER_FAILED",
            "error_message": "Falha controlada do teste do guia.",
            "retryable": False,
        },
    )
    assert failed.status_code == 200
    final = client.get(status_url, headers=auth)
    validate(final.json(), "/api/v1/jobs/{job_id}", "GET", 200)
    assert final.json()["status"] == "failed" and final.json()["download_url"] is None
    assert final.json()["error"]["code"] == "RENDER_FAILED"
    other = issue_api_key(session, user.id, "Outra chave")
    hidden = client.get(status_url, headers={"Authorization": f"Bearer {other.key}"})
    assert hidden.status_code == 404
    validate(hidden.json(), "/api/v1/jobs/{job_id}", "GET", 404)
