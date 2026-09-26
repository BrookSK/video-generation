"""Listagem pública de avatares e cenários: só itens ativos, sem arquivos nem autorização,
prévia por formato e arquivamento que bloqueia job novo sem apagar nada."""

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from avatar_api.auth import issue_api_key
from avatar_api.config import Settings
from avatar_api.devseed import DevCatalog
from avatar_api.models import Avatar, Scene, StoredFile, User, VideoJob

WORKER = {"Authorization": "Bearer token-do-worker-de-teste"}
COMPOSITION = {
    "9:16": {"scale": 0.85, "x": 0.5, "y": 1.0},
    "16:9": {"scale": 0.95, "x": 0.35, "y": 1.1},
}
PREVIEW_SIZES = {"prepared": (40, 90), "preview-9x16": (54, 96), "preview-16x9": (96, 54)}
FORBIDDEN_KEY_PARTS = ("file_id", "path", "authorized")


def data_files(data_dir: Path) -> list[str]:
    return sorted(p.relative_to(data_dir).as_posix() for p in data_dir.rglob("*") if p.is_file())


def all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in all_keys(item)}
    return set()


@pytest.fixture
def auth(panel: TestClient, session: Session) -> dict[str, str]:
    user_id = session.scalar(select(User.id).where(User.username == "painel"))
    return {"Authorization": f"Bearer {issue_api_key(session, user_id, 'ERP').key}"}


@pytest.fixture
def new_avatar(panel: TestClient, image_bytes):
    """Avatar cadastrado pelo painel, em preparando com a tarefa na fila."""

    def make(name: str) -> uuid.UUID:
        response = panel.post(
            "/panel/avatars",
            data={"name": name, "voice": "masculina", "authorization_confirmed": "true"},
            files={"file": ("foto.png", image_bytes("png", (80, 120)), "image/png")},
        )
        assert response.status_code == 201, response.text
        return uuid.UUID(response.json()["id"])

    return make


@pytest.fixture
def active_avatar(panel: TestClient, new_avatar, image_bytes):
    """Avatar cadastrado pelo painel e preparado por worker simulado; devolve id e prévias."""

    def make(name: str) -> tuple[uuid.UUID, dict[str, bytes]]:
        avatar_id = new_avatar(name)
        claimed = panel.post(
            "/internal/v1/claim",
            json={"worker_id": "cpu-01", "kinds": ["asset_prepare"]},
            headers=WORKER,
        ).json()
        base = f"/internal/v1/asset-tasks/{claimed['id']}"
        contents, file_ids = {}, {}
        for kind, size in PREVIEW_SIZES.items():
            data = image_bytes("png", size, alpha=kind == "prepared")
            response = panel.put(
                f"{base}/attempts/{claimed['attempt_id']}/files/{kind}.png",
                files={"file": (f"{kind}.png", data, "application/octet-stream")},
                data={
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "lease_generation": str(claimed["lease_generation"]),
                },
                headers=WORKER,
            )
            assert response.status_code == 201, response.text
            contents[kind] = data
            file_ids[f"{kind.replace('-', '_')}_file_id"] = response.json()["id"]
        done = panel.post(
            f"{base}/complete",
            json={
                "attempt_id": claimed["attempt_id"],
                "lease_generation": claimed["lease_generation"],
                **file_ids,
            },
            headers=WORKER,
        )
        assert done.status_code == 200, done.text
        return avatar_id, contents

    return make


@pytest.fixture
def new_scene(panel: TestClient):
    def make(name: str) -> uuid.UUID:
        response = panel.post(
            "/panel/scenes",
            data={
                "name": name,
                "background_color": "#1F2937",
                "composition": json.dumps(COMPOSITION),
            },
        )
        assert response.status_code == 201, response.text
        return uuid.UUID(response.json()["id"])

    return make


def listed(panel: TestClient, auth: dict[str, str], resource: str) -> list[dict]:
    response = panel.get(f"/api/v1/{resource}", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"items"}
    return body["items"]


# --- autenticação -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/avatars",
        "/api/v1/scenes",
        f"/api/v1/avatars/{uuid.uuid4()}/preview",
        f"/api/v1/scenes/{uuid.uuid4()}/preview",
    ],
)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer chave-errada"}])
def test_rotas_publicas_de_assets_exigem_chave(panel: TestClient, path, headers):
    # O cookie de sessão do painel não serve de credencial para /api/v1.
    response = panel.get(path, headers=headers)

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# --- listagem ---------------------------------------------------------------------------


def test_listas_trazem_so_ativos_ordenados_por_nome_sem_arquivos_nem_autorizacao(
    panel: TestClient,
    auth,
    seeded_catalog: DevCatalog,
    active_avatar,
    new_avatar,
    new_scene,
    engine: Engine,
):
    bruno, _ = active_avatar("Bruno")
    ana, _ = active_avatar("Ana")
    failed, _ = active_avatar("Com falha")
    archived_avatar, _ = active_avatar("Arquivado")
    # Por último: o claim do worker simulado pega a tarefa mais antiga da fila.
    preparing = new_avatar("Em preparação")
    with engine.begin() as connection:
        connection.execute(
            update(Avatar)
            .where(Avatar.id == failed)
            .values(prepare_status="falha", prepare_error="Nenhuma pessoa na imagem.")
        )
    assert panel.post(f"/panel/avatars/{archived_avatar}/archive").status_code == 200
    praia = new_scene("Praia")
    escritorio = new_scene("Escritório")
    archived_scene = new_scene("Antigo")
    assert panel.post(f"/panel/scenes/{archived_scene}/archive").status_code == 200

    avatars = listed(panel, auth, "avatars")
    scenes = listed(panel, auth, "scenes")

    assert [item["name"] for item in avatars] == ["Ana", "Avatar de desenvolvimento", "Bruno"]
    assert [item["id"] for item in avatars] == [
        str(ana),
        str(seeded_catalog.avatar_id),
        str(bruno),
    ]
    assert str(preparing) not in {item["id"] for item in avatars}
    for item in avatars:
        assert set(item) == {"id", "name", "voice", "preview_url", "created_at"}
    assert avatars[0]["voice"] == "masculina"
    assert avatars[0]["preview_url"] == f"/api/v1/avatars/{ana}/preview"
    # O avatar semeado não tem prévia: preview_url nulo em vez de rota que daria 404.
    assert avatars[1]["preview_url"] is None

    assert [item["id"] for item in scenes] == [
        str(seeded_catalog.scene_id),
        str(escritorio),
        str(praia),
    ]
    for item in scenes:
        assert set(item) == {"id", "name", "preview_url", "created_at"}
    assert scenes[0]["preview_url"] is None
    assert scenes[1]["preview_url"] == f"/api/v1/scenes/{escritorio}/preview"

    for key in all_keys(avatars) | all_keys(scenes):
        assert not any(part in key for part in FORBIDDEN_KEY_PARTS), key


def test_listas_sem_limite_de_quantidade(panel: TestClient, auth, active_avatar, new_scene):
    for index in range(3):
        active_avatar(f"Avatar {index}")
    for index in range(5):
        new_scene(f"Cenário {index}")

    assert len(listed(panel, auth, "avatars")) == 3
    assert len(listed(panel, auth, "scenes")) == 5


# --- prévia -----------------------------------------------------------------------------


def test_previa_do_avatar_sai_em_9x16_por_padrao_e_em_16x9_quando_pedida(
    panel: TestClient, auth, active_avatar
):
    avatar_id, contents = active_avatar("Ana")

    default = panel.get(f"/api/v1/avatars/{avatar_id}/preview", headers=auth)
    vertical = panel.get(
        f"/api/v1/avatars/{avatar_id}/preview", params={"aspect_ratio": "9:16"}, headers=auth
    )
    horizontal = panel.get(
        f"/api/v1/avatars/{avatar_id}/preview", params={"aspect_ratio": "16:9"}, headers=auth
    )

    for response in (default, vertical, horizontal):
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/png"
    assert default.content == vertical.content == contents["preview-9x16"]
    assert horizontal.content == contents["preview-16x9"]


def test_previa_do_cenario_sai_nos_dois_formatos(panel: TestClient, auth, new_scene):
    scene_id = new_scene("Estúdio")

    for ratio, kind in (("9:16", "preview-9x16"), ("16:9", "preview-16x9")):
        public = panel.get(
            f"/api/v1/scenes/{scene_id}/preview", params={"aspect_ratio": ratio}, headers=auth
        )
        assert public.status_code == 200, public.text
        assert public.headers["content-type"] == "image/png"
        assert public.content == panel.get(f"/panel/scenes/{scene_id}/files/{kind}").content
    default = panel.get(f"/api/v1/scenes/{scene_id}/preview", headers=auth)
    assert default.content == panel.get(f"/panel/scenes/{scene_id}/files/preview-9x16").content


def test_previa_de_item_arquivado_inativo_inexistente_ou_sem_previa_da_404(
    panel: TestClient, auth, seeded_catalog: DevCatalog, active_avatar, new_avatar, new_scene
):
    archived_avatar, _ = active_avatar("Arquivado")
    assert panel.post(f"/panel/avatars/{archived_avatar}/archive").status_code == 200
    preparing = new_avatar("Em preparação")
    archived_scene = new_scene("Antigo")
    assert panel.post(f"/panel/scenes/{archived_scene}/archive").status_code == 200

    for path in (
        f"/api/v1/avatars/{archived_avatar}/preview",
        f"/api/v1/avatars/{preparing}/preview",
        f"/api/v1/avatars/{uuid.uuid4()}/preview",
        f"/api/v1/avatars/{seeded_catalog.avatar_id}/preview",
        f"/api/v1/scenes/{archived_scene}/preview",
        f"/api/v1/scenes/{uuid.uuid4()}/preview",
        f"/api/v1/scenes/{seeded_catalog.scene_id}/preview",
    ):
        for ratio in ("9:16", "16:9"):
            response = panel.get(path, params={"aspect_ratio": ratio}, headers=auth)
            assert response.status_code == 404, (path, response.text)
            assert response.json()["error"]["code"] == "NOT_FOUND"


def test_previa_recusa_formato_desconhecido(panel: TestClient, auth, new_scene):
    scene_id = new_scene("Estúdio")

    response = panel.get(
        f"/api/v1/scenes/{scene_id}/preview", params={"aspect_ratio": "1:1"}, headers=auth
    )

    assert response.status_code == 422, response.text


# --- arquivamento e job -----------------------------------------------------------------


def test_job_com_asset_arquivado_recebe_422_e_nada_e_apagado(
    panel: TestClient,
    auth,
    seeded_catalog: DevCatalog,
    active_avatar,
    new_scene,
    session: Session,
    settings: Settings,
):
    avatar_id, _ = active_avatar("Ana")
    scene_id = new_scene("Estúdio")
    job = {"script_text": "Olá.", "avatar_id": str(avatar_id), "scene_id": str(scene_id)}
    accepted = panel.post("/api/v1/jobs", json=job, headers=auth)
    assert accepted.status_code == 202, accepted.text
    assert panel.post(f"/panel/avatars/{avatar_id}/archive").status_code == 200
    assert panel.post(f"/panel/scenes/{scene_id}/archive").status_code == 200
    session.expire_all()
    files_before = data_files(settings.data_dir)
    stored_before = session.scalar(select(func.count()).select_from(StoredFile))

    with_archived_avatar = panel.post(
        "/api/v1/jobs", json={**job, "scene_id": str(seeded_catalog.scene_id)}, headers=auth
    )
    with_archived_scene = panel.post(
        "/api/v1/jobs", json={**job, "avatar_id": str(seeded_catalog.avatar_id)}, headers=auth
    )

    assert with_archived_avatar.status_code == 422, with_archived_avatar.text
    assert with_archived_avatar.json()["error"]["code"] == "AVATAR_UNAVAILABLE"
    assert with_archived_scene.status_code == 422, with_archived_scene.text
    assert with_archived_scene.json()["error"]["code"] == "SCENE_UNAVAILABLE"
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(VideoJob)) == 1
    assert session.get(Avatar, avatar_id).archived_at is not None
    assert session.get(Scene, scene_id).archived_at is not None
    assert session.scalar(select(func.count()).select_from(StoredFile)) == stored_before
    assert data_files(settings.data_dir) == files_before
    assert any(path.startswith(f"assets/{avatar_id}/") for path in files_before)
    assert any(path.startswith(f"assets/{scene_id}/") for path in files_before)
    assert str(avatar_id) not in {item["id"] for item in listed(panel, auth, "avatars")}
    assert str(scene_id) not in {item["id"] for item in listed(panel, auth, "scenes")}
