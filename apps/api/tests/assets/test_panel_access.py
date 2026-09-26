import hashlib
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api.config import Settings
from avatar_api.main import create_app
from avatar_api.models import ApiKey, User, UserSession

PANEL_USERNAME = "painel"
PASSWORD = "senha-de-outra-pessoa"


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def error_of(response) -> dict:
    error = dict(response.json()["error"])
    error.pop("request_id")
    return error


@pytest.fixture
def other_client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        yield client


def login(client: TestClient, username: str, password: str = PASSWORD):
    return client.post("/panel/auth/login", json={"username": username, "password": password})


def add_person(panel: TestClient, username: str = "maria", display_name: str = "Maria Souza"):
    return panel.post(
        "/panel/users",
        json={"username": username, "display_name": display_name, "password": PASSWORD},
    )


def panel_user(session: Session) -> User:
    return session.scalar(select(User).where(User.username == PANEL_USERNAME))


# --- sessão atual -----------------------------------------------------------------------


def test_auth_me_sem_sessao_recusa(client):
    response = client.get("/panel/auth/me")
    assert response.status_code == 401
    assert error_of(response)["code"] == "UNAUTHORIZED"


def test_auth_me_emite_csrf_novo_e_invalida_o_anterior(panel, session):
    old_csrf = panel.headers["X-CSRF-Token"]

    response = panel.get("/panel/auth/me")
    assert response.status_code == 200
    body = response.json()
    user = panel_user(session)
    assert body["user"] == {"id": str(user.id), "username": PANEL_USERNAME, "display_name": None}
    new_csrf = body["csrf_token"]
    assert new_csrf != old_csrf

    row = session.scalar(select(UserSession).where(UserSession.user_id == user.id))
    session.refresh(row)
    assert row.csrf_hash == sha256(new_csrf)
    assert new_csrf not in row.csrf_hash
    assert body["expires_at"] == row.expires_at.isoformat().replace("+00:00", "Z")

    stale = panel.post("/panel/api-keys", json={"description": "ERP"})
    assert stale.status_code == 403
    assert error_of(stale)["code"] == "CSRF_INVALID"

    panel.headers["X-CSRF-Token"] = new_csrf
    assert panel.post("/panel/api-keys", json={"description": "ERP"}).status_code == 201


def test_login_devolve_display_name(panel, other_client):
    assert add_person(panel).status_code == 201
    response = login(other_client, "maria")
    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Maria Souza"


# --- pessoas ----------------------------------------------------------------------------


def test_rotas_de_pessoas_exigem_sessao_e_csrf(client, panel):
    assert client.get("/panel/users").status_code == 401
    del panel.headers["X-CSRF-Token"]
    response = add_person(panel)
    assert response.status_code == 403
    assert error_of(response)["code"] == "CSRF_INVALID"


def test_cria_e_lista_pessoa_com_nome(panel, session, other_client):
    response = add_person(panel, "  maria  ", "  Maria Souza  ")
    assert response.status_code == 201
    created = response.json()
    assert created["username"] == "maria"
    assert created["display_name"] == "Maria Souza"
    assert created["disabled_at"] is None
    assert PASSWORD not in response.text

    user = session.get(User, uuid.UUID(created["id"]))
    assert user.display_name == "Maria Souza"
    assert user.password_hash.startswith("$argon2id$")

    listed = panel.get("/panel/users")
    assert listed.status_code == 200
    assert [(u["username"], u["display_name"]) for u in listed.json()] == [
        (PANEL_USERNAME, None),
        ("maria", "Maria Souza"),
    ]
    assert set(listed.json()[1]) == {"id", "username", "display_name", "created_at", "disabled_at"}
    assert login(other_client, "maria").status_code == 200


def test_senha_curta_e_username_repetido_viram_422_com_campo(panel, session):
    short = panel.post(
        "/panel/users",
        json={"username": "joao", "display_name": "João", "password": "curta123"},
    )
    assert short.status_code == 422
    assert error_of(short) == {
        "code": "VALIDATION_ERROR",
        "message": "A senha precisa ter pelo menos 12 caracteres.",
        "field": "password",
    }

    repeated = add_person(panel, PANEL_USERNAME, "Outro")
    assert repeated.status_code == 422
    assert error_of(repeated) == {
        "code": "VALIDATION_ERROR",
        "message": f"Já existe um usuário com o nome {PANEL_USERNAME}.",
        "field": "username",
    }
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_nome_de_exibicao_em_branco_vira_422(panel, session):
    response = add_person(panel, "maria", "   ")
    assert response.status_code == 422
    assert error_of(response)["field"] == "display_name"
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_remover_pessoa_encerra_todas_as_sessoes_dela(panel, session, settings, other_client):
    person_id = add_person(panel).json()["id"]
    assert login(other_client, "maria").status_code == 200
    with TestClient(create_app(settings), base_url="https://testserver") as second:
        assert login(second, "maria").status_code == 200
    open_sessions = select(func.count()).where(
        UserSession.user_id == uuid.UUID(person_id), UserSession.revoked_at.is_(None)
    )
    assert session.scalar(open_sessions) == 2

    response = panel.post(f"/panel/users/{person_id}/disable")
    assert response.status_code == 200
    disabled_at = response.json()["disabled_at"]
    assert disabled_at is not None

    assert session.scalar(open_sessions) == 0
    refused = other_client.get("/panel/auth/me")
    assert refused.status_code == 401
    assert login(other_client, "maria").status_code == 401

    again = panel.post(f"/panel/users/{person_id}/disable")
    assert again.status_code == 200
    assert again.json()["disabled_at"] == disabled_at


def test_ninguem_remove_o_proprio_acesso(panel, session):
    user = panel_user(session)
    response = panel.post(f"/panel/users/{user.id}/disable")
    assert response.status_code == 409
    assert error_of(response) == {
        "code": "CANNOT_DISABLE_SELF",
        "message": "Você não pode remover o próprio acesso.",
    }
    session.refresh(user)
    assert user.disabled_at is None
    assert panel.get("/panel/auth/me").status_code == 200


def test_remover_pessoa_inexistente_responde_404(panel):
    response = panel.post(f"/panel/users/{uuid.uuid4()}/disable")
    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"


# --- chaves pela rota do painel ----------------------------------------------------------


def test_chave_criada_e_revogada_pela_rota_do_painel(panel, session):
    created = panel.post("/panel/api-keys", json={"description": "ERP"})
    assert created.status_code == 201
    key_id = created.json()["id"]

    revoked = panel.post(f"/panel/api-keys/{key_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert session.get(ApiKey, uuid.UUID(key_id)).revoked_at is not None


# --- NUL --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        ("/panel/auth/login", {"username": "pai\x00nel", "password": PASSWORD}, "username"),
        ("/panel/auth/login", {"username": "painel", "password": "senha\x00longa"}, "password"),
        ("/panel/api-keys", {"description": "ERP\x00"}, "description"),
        (
            "/panel/users",
            {"username": "ma\x00ria", "display_name": "Maria", "password": PASSWORD},
            "username",
        ),
        (
            "/panel/users",
            {"username": "maria", "display_name": "Ma\x00ria", "password": PASSWORD},
            "display_name",
        ),
        (
            "/panel/users",
            {"username": "maria", "display_name": "Maria", "password": "senha\x00bem-longa"},
            "password",
        ),
    ],
)
def test_nul_no_texto_do_painel_vira_422(panel, session, path, body, field):
    response = panel.post(path, json=body)
    assert response.status_code == 422
    assert error_of(response) == {
        "code": "VALIDATION_ERROR",
        "message": "Dados inválidos na requisição.",
        "field": field,
    }
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.scalar(select(func.count()).select_from(ApiKey)) == 0
