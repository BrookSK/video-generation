import hashlib
import io
import logging
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api import assets
from avatar_api.config import Settings
from avatar_api.models import AssetPrepareTask, Avatar, StoredFile, User
from avatar_api.storage import resolve_path, save_stream
from avatar_api.uploads import validate_image

SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def error_of(response) -> dict:
    error = dict(response.json()["error"])
    error.pop("request_id")
    return error


def count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def data_files(data_dir: Path) -> list[str]:
    return sorted(p.relative_to(data_dir).as_posix() for p in data_dir.rglob("*") if p.is_file())


def snapshot(session: Session, data_dir: Path) -> tuple:
    session.expire_all()
    return (
        count(session, Avatar),
        count(session, StoredFile),
        count(session, AssetPrepareTask),
        data_files(data_dir),
    )


def post_avatar(
    panel,
    data: bytes,
    *,
    name: str = "Ana",
    voice: str | None = "feminina",
    authorization: str | None = "true",
    filename: str = "foto.png",
    content_type: str = "image/png",
):
    form = {"name": name}
    if voice is not None:
        form["voice"] = voice
    if authorization is not None:
        form["authorization_confirmed"] = authorization
    return panel.post("/panel/avatars", data=form, files={"file": (filename, data, content_type)})


def panel_user_id(session: Session) -> uuid.UUID:
    return session.scalar(select(User.id).where(User.username == "painel"))


def activate(session: Session, avatar_id: str) -> None:
    session.execute(update(Avatar).where(Avatar.id == avatar_id).values(prepare_status="ativo"))
    session.commit()


# --- cadastro ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "extension", "content_type"),
    [("png", ".png", "image/png"), ("jpeg", ".jpg", "image/jpeg"), ("webp", ".webp", "image/webp")],
)
def test_cria_avatar_com_tarefa_e_declaracao_na_mesma_transacao(
    panel, session, settings: Settings, image_bytes, fmt, extension, content_type
):
    data = image_bytes(fmt)

    response = post_avatar(panel, data, name="  Ana  ", voice="feminina")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Ana"
    assert body["voice"] == "feminina"
    assert body["status"] == "preparando"
    assert body["archived_at"] is None
    assert body["authorized_at"] is not None
    avatar_id = uuid.UUID(body["id"])

    session.expire_all()
    avatar = session.get(Avatar, avatar_id)
    user_id = panel_user_id(session)
    assert avatar.prepare_status == "preparando"
    assert avatar.authorized_by_user_id == user_id
    assert avatar.authorized_at is not None
    assert avatar.created_by_user_id == user_id
    tasks = session.scalars(
        select(AssetPrepareTask).where(AssetPrepareTask.avatar_id == avatar_id)
    ).all()
    assert [task.status for task in tasks] == ["queued"]

    stored = session.get(StoredFile, avatar.source_file_id)
    assert stored.relative_path == f"assets/{avatar_id}/source{extension}"
    assert stored.content_type == content_type
    on_disk = resolve_path(settings.data_dir, stored).read_bytes()
    assert sha256(on_disk) == stored.sha256 == sha256(data)
    assert stored.size_bytes == len(data)
    assert data_files(settings.data_dir) == [stored.relative_path]


def test_tres_avatares_sem_limite(panel, session, image_bytes):
    for name in ("Ana", "Bruno", "Carla"):
        response = post_avatar(panel, image_bytes("png"), name=name, voice="masculina")
        assert response.status_code == 201, response.text

    listed = panel.get("/panel/avatars")

    assert listed.status_code == 200
    assert sorted(item["name"] for item in listed.json()) == ["Ana", "Bruno", "Carla"]
    assert {item["status"] for item in listed.json()} == {"preparando"}
    session.expire_all()
    assert count(session, Avatar) == 3
    assert count(session, AssetPrepareTask) == 3


@pytest.mark.parametrize("voice", [None, "", "robotica"], ids=["ausente", "vazia", "invalida"])
def test_recusa_sem_voz_sem_nenhuma_linha_nova(panel, session, settings, image_bytes, voice):
    before = snapshot(session, settings.data_dir)

    response = post_avatar(panel, image_bytes("png"), voice=voice)

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "VALIDATION_ERROR",
        "message": "Escolha a voz do avatar.",
        "field": "voice",
    }
    assert snapshot(session, settings.data_dir) == before


@pytest.mark.parametrize("authorization", [None, "false"], ids=["ausente", "desmarcada"])
def test_recusa_sem_declaracao_sem_nenhuma_linha_nova(
    panel, session, settings, image_bytes, authorization
):
    before = snapshot(session, settings.data_dir)

    response = post_avatar(panel, image_bytes("png"), authorization=authorization)

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "VALIDATION_ERROR",
        "message": "Confirme a autorização de uso da imagem.",
        "field": "authorization",
    }
    assert snapshot(session, settings.data_dir) == before


def test_recusa_svg_renomeado_sem_nenhuma_linha_nova(panel, session, settings):
    before = snapshot(session, settings.data_dir)

    response = post_avatar(panel, SVG, filename="foto.png", content_type="image/png")

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "UNSUPPORTED_FILE_TYPE",
        "message": "SVG não é aceito.",
        "field": "file",
    }
    assert snapshot(session, settings.data_dir) == before


@pytest.mark.parametrize(
    "name", ["", "   ", "a" * 81, "Ana\x00"], ids=["vazio", "espacos", "81", "nul"]
)
def test_recusa_nome_invalido(panel, session, settings, image_bytes, name):
    before = snapshot(session, settings.data_dir)

    response = post_avatar(panel, image_bytes("png"), name=name)

    assert response.status_code == 422
    assert error_of(response)["field"] == "name"
    assert snapshot(session, settings.data_dir) == before


def test_aceita_nome_de_80_caracteres(panel, image_bytes):
    response = post_avatar(panel, image_bytes("png"), name="a" * 80)

    assert response.status_code == 201, response.text


def test_cadastro_exige_sessao_e_csrf(panel, client, session, settings, image_bytes):
    before = snapshot(session, settings.data_dir)

    without_session = post_avatar(client, image_bytes("png"))
    panel.headers.pop("X-CSRF-Token")
    without_csrf = post_avatar(panel, image_bytes("png"))

    assert without_session.status_code == 401
    assert without_csrf.status_code == 403
    assert error_of(without_csrf)["code"] == "CSRF_INVALID"
    assert snapshot(session, settings.data_dir) == before


def test_falha_depois_de_gravar_desfaz_tudo(session, settings, image_bytes, tmp_path, monkeypatch):
    def broken_task(**_):
        raise RuntimeError("falha ao enfileirar")

    monkeypatch.setattr(assets, "AssetPrepareTask", broken_task)
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    image = validate_image(io.BytesIO(image_bytes("png")), "file", uploads_dir)
    user = User(username="alguem", password_hash="x")
    session.add(user)
    session.commit()
    before = snapshot(session, settings.data_dir)

    with pytest.raises(RuntimeError):
        assets.create_avatar(session, settings.data_dir, user.id, "Ana", "feminina", image)

    assert snapshot(session, settings.data_dir) == before


# --- gravação sem commit ------------------------------------------------------------------


def _save_uncommitted(session: Session, data_dir: Path, name: str) -> Path:
    data = name.encode()
    save_stream(
        session,
        data_dir,
        "assets/teste",
        name,
        io.BytesIO(data),
        sha256(data),
        "text/plain",
        commit=False,
    )
    return data_dir / "assets/teste" / name


def test_save_stream_sem_commit_apaga_arquivo_quando_o_chamador_desfaz(session, settings):
    path = _save_uncommitted(session, settings.data_dir, "a.txt")
    assert path.read_bytes() == b"a.txt"

    session.rollback()

    assert not path.exists()
    assert count(session, StoredFile) == 0


def test_save_stream_sem_commit_apaga_arquivo_quando_a_sessao_fecha(engine, settings):
    with Session(engine) as other:
        path = _save_uncommitted(other, settings.data_dir, "b.txt")
        assert path.exists()

    assert not path.exists()


def test_save_stream_sem_commit_mantem_arquivo_confirmado(session, settings):
    path = _save_uncommitted(session, settings.data_dir, "c.txt")
    session.commit()
    session.rollback()

    assert path.read_bytes() == b"c.txt"
    assert count(session, StoredFile) == 1


# --- listagem, arquivamento e arquivos ----------------------------------------------------


def test_arquivar_mantem_arquivos_e_sai_da_lista(panel, session, settings, image_bytes):
    avatar_id = post_avatar(panel, image_bytes("png")).json()["id"]
    activate(session, avatar_id)
    files_before = data_files(settings.data_dir)

    first = panel.post(f"/panel/avatars/{avatar_id}/archive")
    second = panel.post(f"/panel/avatars/{avatar_id}/archive")

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "arquivado"
    assert second.status_code == 200
    assert second.json()["archived_at"] == first.json()["archived_at"]
    assert panel.get("/panel/avatars").json() == []
    archived = panel.get("/panel/avatars", params={"include_archived": "true"}).json()
    assert [(item["id"], item["status"]) for item in archived] == [(avatar_id, "arquivado")]
    assert data_files(settings.data_dir) == files_before
    session.expire_all()
    assert count(session, StoredFile) == 1
    assert panel.get(f"/panel/avatars/{avatar_id}/files/source").status_code == 200


def test_arquivar_em_preparacao_recusado(panel, session, image_bytes):
    avatar_id = post_avatar(panel, image_bytes("png")).json()["id"]

    response = panel.post(f"/panel/avatars/{avatar_id}/archive")

    assert response.status_code == 409
    assert error_of(response)["code"] == "AVATAR_PREPARING"
    session.expire_all()
    assert session.get(Avatar, uuid.UUID(avatar_id)).archived_at is None


def test_lista_mostra_estado_derivado(panel, session, image_bytes):
    ids = [post_avatar(panel, image_bytes("png"), name=n).json()["id"] for n in "ABCD"]
    session.execute(update(Avatar).where(Avatar.id == ids[1]).values(prepare_status="ativo"))
    session.execute(
        update(Avatar)
        .where(Avatar.id == ids[2])
        .values(prepare_status="falha", prepare_error="Recorte falhou.")
    )
    session.execute(
        update(Avatar)
        .where(Avatar.id == ids[3])
        .values(prepare_status="ativo", archived_at=func.now())
    )
    session.commit()

    listed = panel.get("/panel/avatars", params={"include_archived": "true"}).json()

    by_name = {item["name"]: item for item in listed}
    assert {name: item["status"] for name, item in by_name.items()} == {
        "A": "preparando",
        "B": "ativo",
        "C": "falha",
        "D": "arquivado",
    }
    assert by_name["C"]["prepare_error"] == "Recorte falhou."
    assert panel.get(f"/panel/avatars/{ids[2]}").json()["status"] == "falha"


def test_arquivar_avatar_inexistente(panel):
    response = panel.post(f"/panel/avatars/{uuid.uuid4()}/archive")

    assert response.status_code == 404


def test_arquivo_de_origem_com_cache_privado(panel, image_bytes):
    data = image_bytes("png")
    avatar_id = post_avatar(panel, data).json()["id"]

    response = panel.get(f"/panel/avatars/{avatar_id}/files/source")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private"


def test_arquivos_ainda_nao_gerados_e_tipos_invalidos(panel, client, image_bytes):
    avatar_id = post_avatar(panel, image_bytes("png")).json()["id"]

    for kind in ("prepared", "preview-9x16", "preview-16x9"):
        assert panel.get(f"/panel/avatars/{avatar_id}/files/{kind}").status_code == 404
    assert panel.get(f"/panel/avatars/{avatar_id}/files/outro").status_code == 422
    assert client.get(f"/panel/avatars/{avatar_id}/files/source").status_code == 401


def test_nao_existe_edicao_de_avatar(panel, session, image_bytes):
    avatar_id = post_avatar(panel, image_bytes("png")).json()["id"]

    for method in ("PUT", "PATCH"):
        item = panel.request(method, f"/panel/avatars/{avatar_id}", json={"name": "Outro"})
        collection = panel.request(method, "/panel/avatars", json={"name": "Outro"})
        assert item.status_code == 405, method
        assert collection.status_code == 405, method
    session.expire_all()
    assert session.get(Avatar, uuid.UUID(avatar_id)).name == "Ana"


# --- erro de banco no log -----------------------------------------------------------------


SECRET = "texto-secreto-da-linha"
_BAD_INSERT = text(
    "INSERT INTO avatars (name, voice, source_file_id)"
    f" VALUES ('{SECRET}', 'invalida', gen_random_uuid())"
)


def test_erro_de_banco_registra_so_tipo_e_sqlstate(
    panel, session, image_bytes, monkeypatch, caplog: pytest.LogCaptureFixture
):
    # Controle: o texto do driver traz o valor da linha, então o log sem ele prova algo.
    with pytest.raises(IntegrityError) as control:
        session.execute(_BAD_INSERT)
    session.rollback()
    assert SECRET in str(control.value)

    def failing_create(db: Session, *_):
        db.execute(_BAD_INSERT)

    monkeypatch.setattr(assets, "create_avatar", failing_create)
    caplog.set_level(logging.DEBUG)

    response = post_avatar(panel, image_bytes("png"))

    assert response.status_code == 500
    assert error_of(response) == {
        "code": "INTERNAL_ERROR",
        "message": "Erro interno no servidor.",
    }
    assert "erro de banco de dados (CheckViolation, sqlstate 23514)" in caplog.text
    assert caplog.records, "nenhum registro capturado; o teste não provaria nada"
    assert SECRET not in caplog.text
    assert "Failing row" not in caplog.text
