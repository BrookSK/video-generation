import io
import json
import uuid
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api import assets
from avatar_api.config import Settings
from avatar_api.models import Scene, StoredFile, User
from avatar_api.storage import resolve_path
from avatar_api.uploads import validate_image

SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'

COMPOSITION = {
    "9:16": {"scale": 0.85, "x": 0.5, "y": 1.0},
    "16:9": {"scale": 0.95, "x": 0.35, "y": 1.1},
}


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
    return count(session, Scene), count(session, StoredFile), data_files(data_dir)


def post_scene(
    panel,
    *,
    name: str = "Estúdio",
    color: str | None = "#1F2937",
    image: bytes | None = None,
    composition=COMPOSITION,
    filename: str = "fundo.png",
    content_type: str = "image/png",
):
    form = {"name": name}
    if composition is not None:
        form["composition"] = (
            composition if isinstance(composition, str) else json.dumps(composition)
        )
    if color is not None:
        form["background_color"] = color
    files = {"file": (filename, image, content_type)} if image is not None else None
    return panel.post("/panel/scenes", data=form, files=files)


def striped_background() -> bytes:
    """Imagem 200x100 azul com faixa vermelha central em x de 60 a 139."""
    image = Image.new("RGB", (200, 100), (0, 0, 255))
    image.paste((255, 0, 0), (60, 0, 140, 100))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def open_png(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    return image.convert("RGB")


def near(pixel: tuple[int, int, int], expected: tuple[int, int, int]) -> bool:
    return all(abs(a - b) <= 8 for a, b in zip(pixel, expected, strict=True))


# --- cadastro ---------------------------------------------------------------------------


def test_cenario_por_cor_fica_ativo_com_previas(panel, session, settings: Settings):
    response = post_scene(panel, name="  Estúdio  ", color="#1F2937")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Estúdio"
    assert body["background_color"] == "#1F2937"
    assert body["status"] == "ativo"
    assert body["archived_at"] is None
    assert body["composition"] == COMPOSITION
    scene_id = uuid.UUID(body["id"])

    session.expire_all()
    scene = session.get(Scene, scene_id)
    assert scene.background_file_id is None
    assert scene.created_by_user_id == session.scalar(
        select(User.id).where(User.username == "painel")
    )
    assert data_files(settings.data_dir) == [
        f"assets/{scene_id}/preview-16x9.png",
        f"assets/{scene_id}/preview-9x16.png",
    ]
    for kind, size in (("preview-9x16", (540, 960)), ("preview-16x9", (960, 540))):
        preview = panel.get(f"/panel/scenes/{scene_id}/files/{kind}")
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.headers["cache-control"] == "private"
        image = open_png(preview.content)
        assert image.size == size
        assert image.getcolors() == [(size[0] * size[1], (0x1F, 0x29, 0x37))]
    assert panel.get(f"/panel/scenes/{scene_id}/files/background").status_code == 404


@pytest.mark.parametrize(
    ("fmt", "extension", "content_type"),
    [("png", ".png", "image/png"), ("jpeg", ".jpg", "image/jpeg"), ("webp", ".webp", "image/webp")],
)
def test_cenario_por_imagem_grava_fundo_e_previas(
    panel, session, settings: Settings, image_bytes, fmt, extension, content_type
):
    data = image_bytes(fmt, size=(320, 180))

    response = post_scene(panel, color=None, image=data, content_type=content_type)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["background_color"] is None
    assert body["status"] == "ativo"
    scene_id = body["id"]
    session.expire_all()
    scene = session.get(Scene, uuid.UUID(scene_id))
    background = session.get(StoredFile, scene.background_file_id)
    assert background.relative_path == f"assets/{scene_id}/background{extension}"
    assert background.content_type == content_type
    assert resolve_path(settings.data_dir, background).read_bytes() == data
    assert panel.get(f"/panel/scenes/{scene_id}/files/background").content == data
    assert data_files(settings.data_dir) == sorted(
        [
            f"assets/{scene_id}/background{extension}",
            f"assets/{scene_id}/preview-16x9.png",
            f"assets/{scene_id}/preview-9x16.png",
        ]
    )


def test_previas_de_imagem_por_cover_centralizado(panel):
    scene_id = post_scene(panel, color=None, image=striped_background()).json()["id"]

    vertical = open_png(panel.get(f"/panel/scenes/{scene_id}/files/preview-9x16").content)
    horizontal = open_png(panel.get(f"/panel/scenes/{scene_id}/files/preview-16x9").content)

    # 9:16 de uma imagem 2:1: a altura cobre o canvas e só a faixa central sobra.
    assert vertical.size == (540, 960)
    for point in ((2, 2), (537, 957), (270, 480)):
        assert near(vertical.getpixel(point), (255, 0, 0)), point
    # 16:9: a altura ainda manda, e as bordas laterais azuis aparecem, sem distorção.
    assert horizontal.size == (960, 540)
    assert near(horizontal.getpixel((480, 270)), (255, 0, 0))
    assert near(horizontal.getpixel((5, 270)), (0, 0, 255))
    assert near(horizontal.getpixel((954, 270)), (0, 0, 255))


def test_enquadramento_lido_de_volta_e_identico(panel):
    composition = {
        "9:16": {"scale": 0.3, "x": 0.0, "y": 0.5},
        "16:9": {"scale": 1.2, "x": 1, "y": 1.2},
    }
    created = post_scene(panel, composition=composition)
    assert created.status_code == 201, created.text

    listed = panel.get("/panel/scenes").json()

    assert [item["composition"] for item in listed] == [composition]
    for ratio in ("9:16", "16:9"):
        assert listed[0]["composition"][ratio] == composition[ratio], ratio


def test_cinco_cenarios_sem_limite(panel, session):
    for index in range(5):
        response = post_scene(panel, name=f"Cenário {index}")
        assert response.status_code == 201, response.text

    listed = panel.get("/panel/scenes").json()

    assert sorted(item["name"] for item in listed) == [f"Cenário {i}" for i in range(5)]
    assert {item["status"] for item in listed} == {"ativo"}
    session.expire_all()
    assert count(session, Scene) == 5


# --- recusas ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("color", "with_image"),
    [("#000000", True), (None, False), ("", False)],
    ids=["dois-fundos", "sem-fundo", "cor-vazia"],
)
def test_recusa_fundo_duplo_ou_ausente(panel, session, settings, image_bytes, color, with_image):
    before = snapshot(session, settings.data_dir)

    image = image_bytes("png") if with_image else None
    response = post_scene(panel, color=color, image=image)

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "VALIDATION_ERROR",
        "message": "Escolha uma imagem ou uma cor de fundo.",
        "field": "background",
    }
    assert snapshot(session, settings.data_dir) == before


@pytest.mark.parametrize("color", ["#12345", "#1234567", "#GGGGGG", "red", "123456"])
def test_recusa_cor_invalida(panel, session, settings, color):
    before = snapshot(session, settings.data_dir)

    response = post_scene(panel, color=color)

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "VALIDATION_ERROR",
        "message": "Use uma cor no formato #RRGGBB.",
        "field": "background_color",
    }
    assert snapshot(session, settings.data_dir) == before


def _with(ratio: str, key: str, value) -> dict:
    composition = json.loads(json.dumps(COMPOSITION))
    composition[ratio][key] = value
    return composition


@pytest.mark.parametrize(
    ("composition", "message"),
    [
        (
            _with("9:16", "scale", 0.29),
            "Enquadramento 9:16: escala 0,29 fora da faixa de 0,3 a 1,2.",
        ),
        (
            _with("16:9", "scale", 1.5),
            "Enquadramento 16:9: escala 1,5 fora da faixa de 0,3 a 1,2.",
        ),
        (
            _with("16:9", "x", -0.1),
            "Enquadramento 16:9: posição horizontal -0,1 fora da faixa de 0 a 1.",
        ),
        (
            _with("9:16", "x", 1.01),
            "Enquadramento 9:16: posição horizontal 1,01 fora da faixa de 0 a 1.",
        ),
        (_with("9:16", "y", 0.4), "Enquadramento 9:16: base 0,4 fora da faixa de 0,5 a 1,2."),
        (_with("16:9", "y", 1.3), "Enquadramento 16:9: base 1,3 fora da faixa de 0,5 a 1,2."),
        (_with("9:16", "scale", "0.5"), "Enquadramento 9:16: escala precisa ser um número."),
        (_with("16:9", "y", True), "Enquadramento 16:9: base precisa ser um número."),
        (
            {"9:16": COMPOSITION["9:16"]},
            "Informe o enquadramento de 9:16 e de 16:9.",
        ),
        (
            {**COMPOSITION, "1:1": COMPOSITION["9:16"]},
            "Informe o enquadramento de 9:16 e de 16:9.",
        ),
        ([], "Informe o enquadramento de 9:16 e de 16:9."),
        (
            {"9:16": {"scale": 0.8, "x": 0.5}, "16:9": COMPOSITION["16:9"]},
            "Enquadramento 9:16: informe escala, posição e base.",
        ),
        ("{nao e json", "Enquadramento inválido."),
        (
            '{"9:16": {"scale": NaN, "x": 0.5, "y": 1}, "16:9": {"scale": 1, "x": 0.5, "y": 1}}',
            "Enquadramento 9:16: escala nan fora da faixa de 0,3 a 1,2.",
        ),
    ],
)
def test_recusa_enquadramento_invalido(panel, session, settings, composition, message):
    before = snapshot(session, settings.data_dir)

    response = post_scene(panel, composition=composition)

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "VALIDATION_ERROR",
        "message": message,
        "field": "composition",
    }
    assert snapshot(session, settings.data_dir) == before


def test_recusa_sem_enquadramento(panel, session, settings):
    before = snapshot(session, settings.data_dir)

    response = post_scene(panel, composition=None)

    assert response.status_code == 422
    assert error_of(response)["field"] == "composition"
    assert snapshot(session, settings.data_dir) == before


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (SVG, "SVG não é aceito."),
        (b"MZ\x90\x00executavel", "Arquivo executável não é aceito."),
        (b"PK\x03\x04compactado", "Arquivo compactado não é aceito."),
    ],
    ids=["svg", "executavel", "zip"],
)
def test_recusa_arquivo_invalido_sem_nenhuma_linha_nova(panel, session, settings, data, message):
    before = snapshot(session, settings.data_dir)

    response = post_scene(panel, color=None, image=data)

    assert response.status_code == 422
    assert error_of(response) == {
        "code": "UNSUPPORTED_FILE_TYPE",
        "message": message,
        "field": "file",
    }
    assert snapshot(session, settings.data_dir) == before


@pytest.mark.parametrize(
    "name", ["", "   ", "a" * 81, "Estúdio\x00"], ids=["vazio", "espacos", "81", "nul"]
)
def test_recusa_nome_invalido(panel, session, settings, name):
    before = snapshot(session, settings.data_dir)

    response = post_scene(panel, name=name)

    assert response.status_code == 422
    assert error_of(response)["field"] == "name"
    assert snapshot(session, settings.data_dir) == before


def test_cadastro_exige_sessao_e_csrf(panel, client, session, settings):
    before = snapshot(session, settings.data_dir)

    without_session = post_scene(client)
    panel.headers.pop("X-CSRF-Token")
    without_csrf = post_scene(panel)

    assert without_session.status_code == 401
    assert without_csrf.status_code == 403
    assert snapshot(session, settings.data_dir) == before


def test_falha_depois_de_gravar_desfaz_tudo(session, settings, image_bytes, tmp_path, monkeypatch):
    def broken_scene(**_):
        raise RuntimeError("falha ao gravar o cenário")

    monkeypatch.setattr(assets, "Scene", broken_scene)
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    image = validate_image(io.BytesIO(image_bytes("png")), "file", uploads_dir)
    user = User(username="alguem", password_hash="x")
    session.add(user)
    session.commit()
    before = snapshot(session, settings.data_dir)

    with pytest.raises(RuntimeError):
        assets.create_scene(
            session, settings.data_dir, user.id, "Estúdio", COMPOSITION, image=image
        )

    assert snapshot(session, settings.data_dir) == before


# --- listagem, arquivamento e arquivos ----------------------------------------------------


def test_arquivar_mantem_arquivos_e_sai_da_lista(panel, session, settings, image_bytes):
    scene_id = post_scene(panel, color=None, image=image_bytes("png")).json()["id"]
    kept_id = post_scene(panel, name="Outro").json()["id"]
    files_before = data_files(settings.data_dir)

    first = panel.post(f"/panel/scenes/{scene_id}/archive")
    second = panel.post(f"/panel/scenes/{scene_id}/archive")

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "arquivado"
    assert second.status_code == 200
    assert second.json()["archived_at"] == first.json()["archived_at"]
    assert [item["id"] for item in panel.get("/panel/scenes").json()] == [kept_id]
    listed = panel.get("/panel/scenes", params={"include_archived": "true"}).json()
    assert {item["id"]: item["status"] for item in listed} == {
        scene_id: "arquivado",
        kept_id: "ativo",
    }
    assert data_files(settings.data_dir) == files_before
    session.expire_all()
    assert count(session, StoredFile) == 5
    for kind in ("background", "preview-9x16", "preview-16x9"):
        assert panel.get(f"/panel/scenes/{scene_id}/files/{kind}").status_code == 200


def test_arquivar_cenario_inexistente(panel):
    response = panel.post(f"/panel/scenes/{uuid.uuid4()}/archive")

    assert response.status_code == 404


def test_arquivos_exigem_sessao_e_tipo_valido(panel, client):
    scene_id = post_scene(panel).json()["id"]

    assert panel.get(f"/panel/scenes/{scene_id}/files/outro").status_code == 422
    assert panel.get(f"/panel/scenes/{uuid.uuid4()}/files/preview-9x16").status_code == 404
    assert client.get(f"/panel/scenes/{scene_id}/files/preview-9x16").status_code == 401
    assert client.get("/panel/scenes").status_code == 401


def test_nao_existe_edicao_de_cenario(panel, session):
    scene_id = post_scene(panel).json()["id"]

    for method in ("PUT", "PATCH"):
        item = panel.request(method, f"/panel/scenes/{scene_id}", json={"name": "Outro"})
        collection = panel.request(method, "/panel/scenes", json={"name": "Outro"})
        assert item.status_code in (404, 405), method
        assert collection.status_code == 405, method
    session.expire_all()
    scene = session.get(Scene, uuid.UUID(scene_id))
    assert scene.name == "Estúdio"
    assert scene.composition == COMPOSITION
