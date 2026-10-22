import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api.config import Settings
from avatar_api.models import BrandIdentity, StoredFile
from avatar_api.storage import resolve_path

SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'


def error_of(response) -> dict:
    error = dict(response.json()["error"])
    error.pop("request_id")
    return error


def put_identity(
    panel,
    logo: bytes | None,
    *,
    background: str = "#0B2545",
    accent: str = "#F2A541",
    filename: str = "logo.png",
    content_type: str = "image/png",
):
    files = {"logo": (filename, logo, content_type)} if logo is not None else None
    return panel.put(
        "/panel/brand-identity",
        data={"background_color": background, "accent_color": accent},
        files=files,
    )


def stored_count(session: Session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(StoredFile))


def test_sem_cadastro_devolve_campos_nulos(panel):
    response = panel.get("/panel/brand-identity")

    assert response.status_code == 200
    assert response.json() == {
        "logo_url": None,
        "music_url": None,
        "background_color": None,
        "accent_color": None,
        "updated_at": None,
        "updated_by": None,
    }
    assert panel.get("/panel/brand-identity/logo").status_code == 404


def test_cadastro_grava_logo_cores_autor_e_data(panel, image_bytes):
    logo = image_bytes("png", (120, 40), alpha=True)

    response = put_identity(panel, logo)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["background_color"] == "#0B2545"
    assert body["accent_color"] == "#F2A541"
    assert body["updated_by"] == "painel"
    assert body["updated_at"] is not None
    assert body["logo_url"].startswith("/panel/brand-identity/logo")
    assert body["music_url"] is None
    assert panel.get("/panel/brand-identity").json() == body
    served = panel.get(body["logo_url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"] == "private"
    assert served.content == logo


def test_jpeg_aceito(panel, image_bytes):
    response = put_identity(
        panel, image_bytes("jpeg"), filename="logo.jpg", content_type="image/jpeg"
    )

    assert response.status_code == 200, response.text
    assert panel.get("/panel/brand-identity/logo").headers["content-type"] == "image/jpeg"


def test_troca_de_logo_preserva_o_arquivo_anterior(panel, session, settings: Settings, image_bytes):
    first = put_identity(panel, image_bytes("png", (64, 48))).json()
    old_logo_id = session.get(BrandIdentity, 1).logo_file_id

    second = put_identity(panel, image_bytes("png", (80, 20)), background="#112233").json()

    session.expire_all()
    identity = session.get(BrandIdentity, 1)
    assert identity.logo_file_id != old_logo_id
    assert identity.background_color == "#112233"
    assert second["logo_url"] != first["logo_url"]
    old_file = session.get(StoredFile, old_logo_id)
    assert resolve_path(settings.data_dir, old_file).is_file()
    assert session.scalar(select(func.count()).select_from(BrandIdentity)) == 1


def test_troca_so_de_cor_mantem_o_logo(panel, session, image_bytes):
    put_identity(panel, image_bytes("png"))
    logo_id = session.get(BrandIdentity, 1).logo_file_id

    response = put_identity(panel, None, accent="#ABCDEF")

    assert response.status_code == 200, response.text
    session.expire_all()
    identity = session.get(BrandIdentity, 1)
    assert (identity.logo_file_id, identity.accent_color) == (logo_id, "#ABCDEF")


def test_primeiro_cadastro_exige_logo(panel, session):
    response = put_identity(panel, None)

    assert response.status_code == 422
    assert error_of(response)["field"] == "logo"
    assert session.get(BrandIdentity, 1) is None


@pytest.mark.parametrize(
    ("kind", "message"),
    [("webp", "Envie o logo em PNG ou JPEG."), ("svg", "SVG não é aceito.")],
)
def test_logo_webp_ou_svg_recusado_e_identidade_anterior_vale(
    panel, session, image_bytes, kind, message
):
    put_identity(panel, image_bytes("png"))
    before = panel.get("/panel/brand-identity").json()
    files_before = stored_count(session)
    data = image_bytes("webp") if kind == "webp" else SVG

    response = put_identity(panel, data, background="#000000", filename=f"logo.{kind}")

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "UNSUPPORTED_FILE_TYPE",
        "message": message,
        "field": "logo",
    }
    assert panel.get("/panel/brand-identity").json() == before
    assert stored_count(session) == files_before


@pytest.mark.parametrize("field", ["background_color", "accent_color"])
@pytest.mark.parametrize("color", ["azul", "#12345", "#GGGGGG", "123456"])
def test_cor_invalida_recusada_no_campo(panel, session, image_bytes, field, color):
    colors = {"background": "#0B2545", "accent": "#F2A541"}
    colors[field.removesuffix("_color")] = color

    response = put_identity(panel, image_bytes("png"), **colors)

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "VALIDATION_ERROR",
        "message": "Use uma cor no formato #RRGGBB.",
        "field": field,
    }
    assert session.get(BrandIdentity, 1) is None
    assert stored_count(session) == 0


def test_identidade_exige_sessao_e_csrf(panel, client, image_bytes):
    assert client.get("/panel/brand-identity").status_code == 401
    assert client.get("/panel/brand-identity/logo").status_code == 401
    panel.headers.pop("X-CSRF-Token")

    assert put_identity(panel, image_bytes("png")).status_code == 403


# --- trilha de fundo --------------------------------------------------------------------

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 64
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64
M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x02\x00" + b"\x00" * 64
OGG = b"OggS\x00\x02" + b"\x00" * 64
FLAC = b"fLaC\x00\x00\x00\x22" + b"\x00" * 64


def put_music(panel, content: bytes, filename: str = "trilha.mp3"):
    return panel.put(
        "/panel/brand-identity/music", files={"music": (filename, content, "audio/mpeg")}
    )


@pytest.mark.parametrize(
    ("content", "filename", "content_type"),
    [
        (MP3, "trilha.mp3", "audio/mpeg"),
        (WAV, "trilha.wav", "audio/wav"),
        (M4A, "trilha.m4a", "audio/mp4"),
        (OGG, "trilha.ogg", "audio/ogg"),
    ],
)
def test_trilha_aceita_e_servida(panel, session, image_bytes, content, filename, content_type):
    put_identity(panel, image_bytes("png"))

    response = put_music(panel, content, filename)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["music_url"].startswith("/panel/brand-identity/music?v=")
    served = panel.get(body["music_url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == content_type
    assert served.headers["cache-control"] == "private"
    assert served.content == content
    session.expire_all()
    identity = session.get(BrandIdentity, 1)
    assert session.get(StoredFile, identity.music_file_id).name.startswith("trilha.")


def test_troca_de_trilha_preserva_o_arquivo_anterior(panel, session, settings, image_bytes):
    put_identity(panel, image_bytes("png"))
    first = put_music(panel, MP3).json()
    session.expire_all()
    old_id = session.get(BrandIdentity, 1).music_file_id

    second = put_music(panel, OGG, "nova.ogg").json()

    session.expire_all()
    identity = session.get(BrandIdentity, 1)
    assert identity.music_file_id != old_id
    assert second["music_url"] != first["music_url"]
    assert resolve_path(settings.data_dir, session.get(StoredFile, old_id)).is_file()


TOO_BIG = 20 * 1024 * 1024 + 1


@pytest.mark.parametrize(
    ("kind", "code", "message"),
    [
        ("flac", "UNSUPPORTED_FILE_TYPE", "Envie a trilha em MP3, WAV, M4A ou OGG."),
        ("texto", "UNSUPPORTED_FILE_TYPE", "Envie a trilha em MP3, WAV, M4A ou OGG."),
        ("grande", "FILE_TOO_LARGE", "A trilha passa do limite de 20 MB."),
        ("vazio", "FILE_EMPTY", "O arquivo está vazio."),
    ],
)
def test_trilha_fora_do_formato_ou_do_tamanho_recusada_no_campo(
    panel, session, image_bytes, kind, code, message
):
    content = {
        "flac": FLAC,
        "texto": b"nao e audio" * 10,
        "grande": MP3 + b"\x00" * (TOO_BIG - len(MP3)),
        "vazio": b"",
    }[kind]
    put_identity(panel, image_bytes("png"))
    put_music(panel, MP3)
    before = panel.get("/panel/brand-identity").json()
    files_before = stored_count(session)

    response = put_music(panel, content, "trilha.flac")

    assert response.status_code == 422
    assert error_of(response) == {"code": code, "message": message, "field": "music"}
    assert panel.get("/panel/brand-identity").json() == before
    assert stored_count(session) == files_before


def test_trilha_sem_identidade_e_recusada(panel, session):
    response = put_music(panel, MP3)

    assert response.status_code == 422
    assert error_of(response)["field"] == "music"
    assert stored_count(session) == 0


def test_remover_trilha_mantem_o_arquivo(panel, session, settings, image_bytes):
    put_identity(panel, image_bytes("png"))
    put_music(panel, MP3)
    session.expire_all()
    music_id = session.get(BrandIdentity, 1).music_file_id

    response = panel.delete("/panel/brand-identity/music")

    assert response.status_code == 200
    assert response.json()["music_url"] is None
    assert response.json()["logo_url"] is not None
    assert panel.get("/panel/brand-identity/music").status_code == 404
    assert resolve_path(settings.data_dir, session.get(StoredFile, music_id)).is_file()


def test_trilha_exige_sessao_e_csrf(panel, client, image_bytes):
    put_identity(panel, image_bytes("png"))
    assert client.get("/panel/brand-identity/music").status_code == 401
    panel.headers.pop("X-CSRF-Token")

    assert put_music(panel, MP3).status_code == 403
    assert panel.delete("/panel/brand-identity/music").status_code == 403
