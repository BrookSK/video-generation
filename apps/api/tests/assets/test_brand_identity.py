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
