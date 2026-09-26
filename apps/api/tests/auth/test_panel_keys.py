import hashlib
import logging
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from avatar_api import cli
from avatar_api.auth import CurrentApiKey, create_user
from avatar_api.config import Settings
from avatar_api.main import create_app
from avatar_api.models import ApiKey, User, UserSession

PASSWORD = "senha-de-teste-bem-longa"
AVATAR_API = Path(sys.executable).parent / "avatar-api"
KEY_PATTERN = re.compile(r"avk_[A-Za-z0-9_-]{43}")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def app(settings: Settings):
    app = create_app(settings)

    @app.get("/api/v1/_probe")
    def probe(key: CurrentApiKey):
        return {"prefix": key.prefix}

    return app


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    # O cookie de sessão é Secure: o cliente precisa falar HTTPS para reenviá-lo.
    with TestClient(app, base_url="https://testserver") as client:
        yield client


@pytest.fixture
def admin(session: Session) -> User:
    return create_user(session, "admin", PASSWORD)


def login(client: TestClient, username: str = "admin", password: str = PASSWORD):
    return client.post("/panel/auth/login", json={"username": username, "password": password})


@pytest.fixture
def csrf(client: TestClient, admin: User) -> dict[str, str]:
    response = login(client)
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def issue_key(client: TestClient, csrf: dict[str, str], description: str = "ERP") -> dict:
    response = client.post("/panel/api-keys", json={"description": description}, headers=csrf)
    assert response.status_code == 201
    return response.json()


def error_without_request_id(response) -> dict:
    error = dict(response.json()["error"])
    error.pop("request_id")
    return error


# --- CLI ------------------------------------------------------------------------------


def run_cli(database_url: str, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(AVATAR_API), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": database_url},
        timeout=60,
    )


def test_cli_cria_usuario_com_argon2id_sem_imprimir_senha(database_url, session):
    result = run_cli(
        database_url,
        "users",
        "create",
        "--username",
        "admin",
        "--password-stdin",
        stdin=PASSWORD + "\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Usuário admin criado."
    assert PASSWORD not in result.stdout + result.stderr

    user = session.scalar(select(User).where(User.username == "admin"))
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_cli_recusa_username_duplicado_com_codigo_1(database_url, admin):
    result = run_cli(
        database_url,
        "users",
        "create",
        "--username",
        "admin",
        "--password-stdin",
        stdin=PASSWORD + "\n",
    )
    assert result.returncode == 1
    assert "Já existe um usuário com o nome admin." in result.stderr
    assert PASSWORD not in result.stdout + result.stderr


def test_cli_recusa_senha_curta(database_url, session):
    result = run_cli(
        database_url,
        "users",
        "create",
        "--username",
        "curta",
        "--password-stdin",
        stdin="curta123\n",
    )
    assert result.returncode == 1
    assert "pelo menos 12 caracteres" in result.stderr
    assert session.scalar(select(User).where(User.username == "curta")) is None


def test_cli_le_senha_por_getpass(database_url, session, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: PASSWORD)
    assert cli.main(["users", "create", "--username", "operador"]) == 0
    out = capsys.readouterr()
    assert "Usuário operador criado." in out.out
    assert PASSWORD not in out.out + out.err
    assert session.scalar(select(User).where(User.username == "operador")) is not None


def test_cli_recusa_confirmacao_divergente(database_url, session, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", database_url)
    answers = iter([PASSWORD, PASSWORD + "x"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(answers))
    assert cli.main(["users", "create", "--username", "operador"]) == 1
    assert "não conferem" in capsys.readouterr().err
    assert session.scalar(select(User).where(User.username == "operador")) is None


# --- login, sessão e CSRF -------------------------------------------------------------


def test_login_com_senha_errada_desconhecido_ou_desativado_e_generico(client, admin, session):
    wrong = login(client, password="senha-errada-longa")
    unknown = login(client, username="ninguem")
    session.execute(update(User).where(User.id == admin.id).values(disabled_at=text("now()")))
    session.commit()
    disabled = login(client)

    for response in (wrong, unknown, disabled):
        assert response.status_code == 401
        assert "set-cookie" not in response.headers
    assert error_without_request_id(wrong) == {
        "code": "INVALID_CREDENTIALS",
        "message": "Usuário ou senha inválidos.",
    }
    assert error_without_request_id(unknown) == error_without_request_id(wrong)
    assert error_without_request_id(disabled) == error_without_request_id(wrong)
    assert session.scalar(select(UserSession.id)) is None


def test_login_certo_define_cookie_seguro_e_guarda_so_hashes(client, admin, session, settings):
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {"id": str(admin.id), "username": "admin", "display_name": None}

    cookie = response.headers["set-cookie"]
    token = re.match(r"avatar_session=([^;]+);", cookie).group(1)
    flags = {part.strip().lower() for part in cookie.split(";")[1:]}
    assert {"httponly", "secure", "samesite=lax", "path=/panel"} <= flags
    assert f"max-age={settings.session_ttl_hours * 3600}" in flags

    row = session.scalar(select(UserSession))
    assert row.token_hash == sha256(token)
    assert row.csrf_hash == sha256(body["csrf_token"])
    assert token not in (row.token_hash, row.csrf_hash)
    assert row.expires_at - row.created_at == timedelta(hours=settings.session_ttl_hours)


def test_rotas_do_painel_sem_sessao_devolvem_401(client):
    assert client.get("/panel/api-keys").json()["error"]["code"] == "UNAUTHORIZED"
    response = client.post("/panel/api-keys", json={"description": "x"})
    assert response.status_code == 401
    assert client.post("/panel/auth/logout").status_code == 401


def test_mutacao_sem_ou_com_csrf_errado_devolve_403(client, csrf, session):
    missing = client.post("/panel/api-keys", json={"description": "ERP"})
    wrong = client.post(
        "/panel/api-keys", json={"description": "ERP"}, headers={"X-CSRF-Token": "falso"}
    )
    for response in (missing, wrong):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_INVALID"
    assert session.scalar(select(ApiKey.id)) is None
    # Leitura não exige o cabeçalho.
    assert client.get("/panel/api-keys").status_code == 200


def test_sessao_expirada_e_recusada(client, csrf, session):
    session.execute(update(UserSession).values(expires_at=text("now() - interval '1 second'")))
    session.commit()
    assert client.get("/panel/api-keys").status_code == 401


def test_logout_revoga_a_sessao(client, csrf, session):
    assert client.post("/panel/auth/logout").status_code == 403
    cookie = client.cookies.get("avatar_session")

    response = client.post("/panel/auth/logout", headers=csrf)
    assert response.status_code == 204
    assert 'avatar_session=""' in response.headers["set-cookie"]
    assert session.scalar(select(UserSession.revoked_at)) is not None

    client.cookies.set("avatar_session", cookie, domain="testserver", path="/panel")
    assert client.get("/panel/api-keys").status_code == 401


# --- chaves de API --------------------------------------------------------------------


def test_chave_emitida_aparece_uma_vez_e_banco_guarda_so_prefixo_e_hash(
    client, csrf, admin, session
):
    issued = issue_key(client, csrf, "  Sistema ERP  ")
    key = issued["key"]
    assert KEY_PATTERN.fullmatch(key)
    assert issued["prefix"] == key[:12]
    assert issued["description"] == "Sistema ERP"
    assert issued["created_by_username"] == "admin"
    assert issued["created_by_user_id"] == str(admin.id)
    assert issued["revoked_at"] is None
    assert "key_hash" not in issued

    listing = client.get("/panel/api-keys")
    assert listing.status_code == 200
    assert key not in listing.text
    assert sha256(key) not in listing.text
    [item] = listing.json()
    assert "key" not in item and "key_hash" not in item
    assert item["prefix"] == key[:12]

    revoked = client.post(f"/panel/api-keys/{issued['id']}/revoke", headers=csrf)
    assert revoked.status_code == 200
    assert key not in revoked.text

    rows = session.execute(text("SELECT * FROM api_keys")).mappings().all()
    assert len(rows) == 1
    assert rows[0]["prefix"] == key[:12]
    assert rows[0]["key_hash"] == sha256(key)
    assert all(key not in str(value) for value in rows[0].values())


def test_descricao_vazia_e_recusada(client, csrf):
    response = client.post("/panel/api-keys", json={"description": "   "}, headers=csrf)
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "description"


def test_revogacao_e_idempotente_e_exige_csrf(client, csrf):
    issued = issue_key(client, csrf)
    url = f"/panel/api-keys/{issued['id']}/revoke"

    assert client.post(url).status_code == 403
    assert client.get("/panel/api-keys").json()[0]["revoked_at"] is None

    first = client.post(url, headers=csrf)
    second = client.post(url, headers=csrf)
    assert first.status_code == second.status_code == 200
    assert first.json()["revoked_at"] is not None
    assert second.json()["revoked_at"] == first.json()["revoked_at"]

    missing = client.post(f"/panel/api-keys/{uuid.uuid4()}/revoke", headers=csrf)
    assert missing.status_code == 404


def test_listagem_mostra_chaves_de_todos_os_emissores(client, csrf, session):
    other = create_user(session, "operador", PASSWORD)
    session.add(
        ApiKey(
            prefix="avk_outraaaa",
            key_hash=sha256("x"),
            description="BI",
            created_by_user_id=other.id,
        )
    )
    session.commit()
    issue_key(client, csrf)
    listing = client.get("/panel/api-keys").json()
    assert {item["created_by_username"] for item in listing} == {"admin", "operador"}


# --- require_api_key ------------------------------------------------------------------


def test_require_api_key_recusa_tudo_com_o_mesmo_401(client, csrf):
    revoked_key = issue_key(client, csrf, "revogada")
    client.post(f"/panel/api-keys/{revoked_key['id']}/revoke", headers=csrf)
    valid = issue_key(client, csrf)["key"]
    unknown = "avk_" + "A" * 43

    responses = [
        client.get("/api/v1/_probe"),
        client.get("/api/v1/_probe", headers={"Authorization": f"Basic {valid}"}),
        client.get("/api/v1/_probe", headers={"Authorization": "Bearer avk_curta"}),
        client.get("/api/v1/_probe", headers={"Authorization": valid}),
        client.get("/api/v1/_probe", headers={"Authorization": f"Bearer {unknown}"}),
        client.get("/api/v1/_probe", headers={"Authorization": f"Bearer {valid[:-1]}B"}),
        client.get("/api/v1/_probe", headers={"Authorization": f"Bearer {revoked_key['key']}"}),
        client.get("/api/v1/_probe", params={"api_key": valid}),
    ]
    expected = {"code": "UNAUTHORIZED", "message": "Chave de API ausente ou inválida."}
    for response in responses:
        assert response.status_code == 401
        assert error_without_request_id(response) == expected


def test_chave_valida_passa_registra_uso_e_revogada_cai_na_chamada_seguinte(client, csrf, session):
    issued = issue_key(client, csrf)
    auth = {"Authorization": f"Bearer {issued['key']}"}

    response = client.get("/api/v1/_probe", headers=auth)
    assert response.status_code == 200
    assert response.json() == {"prefix": issued["prefix"]}
    assert session.scalar(select(ApiKey.last_used_at)) is not None

    client.post(f"/panel/api-keys/{issued['id']}/revoke", headers=csrf)
    assert client.get("/api/v1/_probe", headers=auth).status_code == 401


def test_nenhum_segredo_vai_para_o_log(client, admin, caplog):
    caplog.set_level(logging.DEBUG)
    response = login(client)
    csrf_token = response.json()["csrf_token"]
    session_token = client.cookies.get("avatar_session")
    issued = issue_key(client, {"X-CSRF-Token": csrf_token})
    client.get("/api/v1/_probe", headers={"Authorization": f"Bearer {issued['key']}"})
    client.post(f"/panel/api-keys/{issued['id']}/revoke", headers={"X-CSRF-Token": csrf_token})
    login(client, password="senha-errada-longa")

    for secret in (PASSWORD, csrf_token, session_token, issued["key"]):
        assert secret not in caplog.text
