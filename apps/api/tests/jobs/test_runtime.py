from pathlib import Path

import pytest
from fastapi import Query
from fastapi.testclient import TestClient

from avatar_api.config import Settings
from avatar_api.errors import ApiError
from avatar_api.main import create_app


@pytest.fixture
def app(tmp_path: Path):
    settings = Settings(database_url="", data_dir=tmp_path, worker_token="t")
    app = create_app(settings)

    @app.get("/_boom")
    def boom():
        raise RuntimeError("detalhe secreto do driver")

    @app.get("/_api-error")
    def api_error():
        raise ApiError(409, "JOB_NOT_READY", "O vídeo ainda não está pronto.", "status")

    @app.get("/_validate")
    def validate(count: int = Query()):
        return {"count": count}

    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def assert_envelope(response, status: int, code: str) -> dict:
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["request_id"]
    return error


def test_healthz_responde_ok_com_request_id(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_request_id_recebido_e_propagado(client):
    response = client.get("/healthz", headers={"X-Request-ID": "req-123"})
    assert response.headers["X-Request-ID"] == "req-123"


def test_rota_inexistente_no_envelope(client):
    response = client.get("/nao-existe", headers={"X-Request-ID": "req-404"})
    error = assert_envelope(response, 404, "NOT_FOUND")
    assert error["request_id"] == "req-404"
    assert "field" not in error


def test_excecao_nao_tratada_sem_traceback(client):
    response = client.get("/_boom", headers={"X-Request-ID": "req-500"})
    error = assert_envelope(response, 500, "INTERNAL_ERROR")
    assert error["request_id"] == "req-500"
    assert "Traceback" not in response.text
    assert "detalhe secreto" not in response.text
    assert "RuntimeError" not in response.text


def test_api_error_com_field(client):
    error = assert_envelope(client.get("/_api-error"), 409, "JOB_NOT_READY")
    assert error["field"] == "status"


def test_validacao_vira_422_com_field(client):
    error = assert_envelope(client.get("/_validate?count=abc"), 422, "VALIDATION_ERROR")
    assert error["field"] == "count"
