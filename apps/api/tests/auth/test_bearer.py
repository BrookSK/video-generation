import base64
import logging
import secrets
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api import auth as auth_module
from avatar_api.auth import API_KEY_VISIBLE_CHARS, create_user
from avatar_api.config import Settings
from avatar_api.devseed import DevCatalog
from avatar_api.main import create_app
from avatar_api.models import ApiKey, User, VideoJob

PASSWORD = "senha-de-teste-bem-longa"
REQUEST_ID = "pedido-fixo"
UNAUTHORIZED_BODY = {
    "error": {
        "code": "UNAUTHORIZED",
        "message": "Chave de API ausente ou inválida.",
        "request_id": REQUEST_ID,
    }
}


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # O cookie de sessão do painel é Secure: o cliente precisa falar HTTPS para reenviá-lo.
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        yield client


@pytest.fixture
def admin(session: Session) -> User:
    return create_user(session, "admin", PASSWORD)


@pytest.fixture
def csrf(client: TestClient, admin: User) -> dict[str, str]:
    response = client.post("/panel/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def issued(client: TestClient, csrf: dict[str, str]) -> dict:
    """Chave emitida pelo painel, como o operador faz."""
    response = client.post("/panel/api-keys", json={"description": "ERP"}, headers=csrf)
    assert response.status_code == 201
    return response.json()


def job_body(catalog: DevCatalog) -> dict:
    return {
        "script_text": "Olá, este é o vídeo de teste.",
        "avatar_id": str(catalog.avatar_id),
        "scene_id": str(catalog.scene_id),
    }


def public_calls(catalog: DevCatalog) -> list[tuple[str, str, dict | None]]:
    job_id = uuid.uuid4()
    return [
        ("POST", "/api/v1/jobs", job_body(catalog)),
        ("GET", f"/api/v1/jobs/{job_id}", None),
        ("GET", f"/api/v1/jobs/{job_id}/download", None),
        ("GET", "/api/v1/jobs/nao-e-uuid", None),
    ]


def call(client: TestClient, method: str, path: str, json, headers: dict[str, str], **kw):
    headers = {"X-Request-ID": REQUEST_ID, **headers}
    return client.request(method, path, json=json, headers=headers, **kw)


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def unknown_key() -> str:
    return "avk_" + secrets.token_urlsafe(32)


def job_count(session: Session) -> int:
    session.rollback()
    return session.scalar(select(func.count()).select_from(VideoJob))


def assert_refused(response) -> None:
    assert response.status_code == 401, response.text
    assert response.json() == UNAUTHORIZED_BODY


# --- variantes de recusa com o mesmo corpo --------------------------------------------


def refused_headers(key: str) -> dict[str, dict[str, str]]:
    return {
        "sem cabeçalho": {},
        "cabeçalho vazio": {"Authorization": ""},
        "Bearer sem chave": {"Authorization": "Bearer "},
        "esquema Basic": {
            "Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()
        },
        "esquema Basic com a chave": {"Authorization": f"Basic {key}"},
        "chave sem esquema": {"Authorization": key},
        "chave malformada": bearer("avk_curta"),
        "chave sem prefixo": bearer(key[len("avk_") :]),
        "chave com caractere inválido": bearer(key[:-1] + "!"),
        "chave truncada": bearer(key[:-1]),
        "chave com sobra": bearer(key + "x"),
        "chave desconhecida": bearer(unknown_key()),
        "prefixo certo e segredo errado": bearer(
            key[:API_KEY_VISIBLE_CHARS] + unknown_key()[API_KEY_VISIBLE_CHARS:]
        ),
    }


def test_toda_variante_sem_chave_valida_recebe_o_mesmo_401(
    client: TestClient, issued: dict, seeded_catalog: DevCatalog, session: Session
):
    key = issued["key"]
    for name, headers in refused_headers(key).items():
        for method, path, json in public_calls(seeded_catalog):
            response = call(client, method, path, json, headers)
            assert_refused(response)
            assert key not in response.text, name
    assert job_count(session) == 0


def test_chave_em_query_string_e_ignorada(
    client: TestClient, issued: dict, seeded_catalog: DevCatalog, session: Session
):
    key = issued["key"]
    for param in ("api_key", "key", "access_token", "token"):
        for method, path, json in public_calls(seeded_catalog):
            assert_refused(call(client, method, path, json, {}, params={param: key}))
    assert job_count(session) == 0


def test_chave_revogada_no_painel_recusada_na_chamada_seguinte(
    client: TestClient,
    issued: dict,
    csrf: dict[str, str],
    seeded_catalog: DevCatalog,
    session: Session,
):
    headers = bearer(issued["key"])
    accepted = call(client, "POST", "/api/v1/jobs", job_body(seeded_catalog), headers)
    assert accepted.status_code == 202, accepted.text

    revoked = client.post(f"/panel/api-keys/{issued['id']}/revoke", headers=csrf)
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    for method, path, json in public_calls(seeded_catalog):
        assert_refused(call(client, method, path, json, headers))
    # O job aceito antes da revogação também deixa de ser entregue.
    assert_refused(call(client, "GET", f"/api/v1/jobs/{accepted.json()['id']}", None, headers))
    assert job_count(session) == 1


def test_recusa_de_chave_desconhecida_e_revogada_passa_pela_comparacao_constante(
    client: TestClient,
    issued: dict,
    csrf: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    compared = []
    real_compare = auth_module.hmac.compare_digest

    def spy(a, b):
        compared.append((len(a), len(b)))
        return real_compare(a, b)

    monkeypatch.setattr(auth_module.hmac, "compare_digest", spy)
    path = f"/api/v1/jobs/{uuid.uuid4()}"

    # Chave sem linha e chave revogada comparam um SHA-256 inteiro, como a chave válida.
    assert_refused(call(client, "GET", path, None, bearer(unknown_key())))
    assert compared == [(64, 64)]
    assert client.post(f"/panel/api-keys/{issued['id']}/revoke", headers=csrf).status_code == 200
    compared.clear()
    assert_refused(call(client, "GET", path, None, bearer(issued["key"])))

    assert compared == [(64, 64)]


# --- chamada aceita --------------------------------------------------------------------


def test_chamada_aceita_atualiza_last_used_at(client: TestClient, issued: dict, session: Session):
    assert issued["last_used_at"] is None
    key_id = uuid.UUID(issued["id"])

    response = call(client, "GET", f"/api/v1/jobs/{uuid.uuid4()}", None, bearer(issued["key"]))

    # Passou pela autenticação: o 404 é do job, não da chave.
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    session.rollback()
    assert session.get(ApiKey, key_id).last_used_at is not None


def test_esquema_bearer_aceito_sem_diferenciar_maiusculas(client: TestClient, issued: dict):
    path = f"/api/v1/jobs/{uuid.uuid4()}"
    for scheme in ("Bearer", "bearer", "BEARER"):
        headers = {"Authorization": f"{scheme} {issued['key']}"}
        assert call(client, "GET", path, None, headers).status_code == 404


# --- nada de segredo em log -----------------------------------------------------------


def test_segredo_da_chave_nunca_aparece_em_log(
    client: TestClient,
    issued: dict,
    csrf: dict[str, str],
    seeded_catalog: DevCatalog,
    caplog: pytest.LogCaptureFixture,
):
    key = issued["key"]
    secret = key[API_KEY_VISIBLE_CHARS:]
    caplog.set_level(logging.DEBUG)

    accepted = call(client, "POST", "/api/v1/jobs", job_body(seeded_catalog), bearer(key))
    assert accepted.status_code == 202
    for headers in refused_headers(key).values():
        call(client, "GET", f"/api/v1/jobs/{accepted.json()['id']}", None, headers)
    client.post(f"/panel/api-keys/{issued['id']}/revoke", headers=csrf)
    assert_refused(call(client, "GET", f"/api/v1/jobs/{uuid.uuid4()}", None, bearer(key)))

    assert caplog.records, "nenhum registro capturado; o teste não provaria nada"
    formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")
    for record in caplog.records:
        text = formatter.format(record) + repr(record.__dict__)
        assert secret not in text, record.name
