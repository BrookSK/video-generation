"""Preparação do avatar pela fila: worker simulado baixa a origem, envia recorte e prévias
da tentativa vigente e conclui; falha definitiva ou worker perdido deixam o avatar em falha."""

import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from avatar_api import jobs
from avatar_api.config import Settings
from avatar_api.models import AssetPrepareTask, Avatar, StoredFile

WORKER = {"Authorization": "Bearer token-do-worker-de-teste"}
FILE_NAMES = {
    "prepared_file_id": "prepared.png",
    "preview_9x16_file_id": "preview-9x16.png",
    "preview_16x9_file_id": "preview-16x9.png",
}
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_error(response, status: int, code: str, field: str | None = None) -> None:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    if field is not None:
        assert error["field"] == field


def data_files(data_dir: Path) -> list[str]:
    return sorted(p.relative_to(data_dir).as_posix() for p in data_dir.rglob("*") if p.is_file())


def fresh(engine: Engine, model, item_id):
    with Session(engine) as reader:
        return reader.get(model, uuid.UUID(str(item_id)))


@pytest.fixture
def new_avatar(panel: TestClient, image_bytes):
    """Cadastra pelo painel um avatar em preparando, com a tarefa asset_prepare na fila."""

    def make(name: str = "Ana") -> tuple[uuid.UUID, bytes]:
        source = image_bytes("png", (80, 120))
        response = panel.post(
            "/panel/avatars",
            data={"name": name, "voice": "feminina", "authorization_confirmed": "true"},
            files={"file": ("foto.png", source, "image/png")},
        )
        assert response.status_code == 201, response.text
        return uuid.UUID(response.json()["id"]), source

    return make


def claim(client: TestClient, worker_id: str = "cpu-01") -> dict:
    response = client.post(
        "/internal/v1/claim",
        json={"worker_id": worker_id, "kinds": ["asset_prepare"]},
        headers=WORKER,
    )
    assert response.status_code == 200, response.text
    return response.json()


def upload(client, task_id, attempt_id, generation, name, data, digest=None):
    return client.put(
        f"/internal/v1/asset-tasks/{task_id}/attempts/{attempt_id}/files/{name}",
        files={"file": (name, data, "application/octet-stream")},
        data={"sha256": digest or sha(data), "lease_generation": str(generation)},
        headers=WORKER,
    )


def upload_all(client, image_bytes, claimed: dict) -> dict[str, str]:
    """Envia os três PNG da tentativa e devolve os ids pelo nome do campo do complete."""
    sizes = {"prepared.png": (40, 90), "preview-9x16.png": (54, 96), "preview-16x9.png": (96, 54)}
    ids = {}
    for field, name in FILE_NAMES.items():
        response = upload(
            client,
            claimed["id"],
            claimed["attempt_id"],
            claimed["lease_generation"],
            name,
            image_bytes("png", sizes[name], alpha=name == "prepared.png"),
        )
        assert response.status_code == 201, response.text
        ids[field] = response.json()["id"]
    return ids


def complete(client, claimed: dict, file_ids: dict[str, str], generation: int | None = None):
    return client.post(
        f"/internal/v1/asset-tasks/{claimed['id']}/complete",
        json={
            "attempt_id": claimed["attempt_id"],
            "lease_generation": generation or claimed["lease_generation"],
            **file_ids,
        },
        headers=WORKER,
    )


def fail(client, claimed: dict, retryable: bool, message: str = "Nenhuma pessoa na imagem."):
    return client.post(
        f"/internal/v1/asset-tasks/{claimed['id']}/fail",
        json={
            "attempt_id": claimed["attempt_id"],
            "lease_generation": claimed["lease_generation"],
            "error_code": "INVALID_SOURCE",
            "error_message": message,
            "retryable": retryable,
        },
        headers=WORKER,
    )


def expire_lease(engine: Engine, task_id) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(AssetPrepareTask)
            .where(AssetPrepareTask.id == task_id)
            .values(lease_until=func.now() - text("interval '1 second'"))
        )


def sweep(engine: Engine) -> jobs.SweepResult:
    with Session(engine) as session:
        return jobs.sweep_expired_leases(session)


def avatar_state(engine: Engine, avatar_id: uuid.UUID) -> tuple:
    avatar = fresh(engine, Avatar, avatar_id)
    return (
        avatar.prepare_status,
        avatar.prepare_error,
        avatar.prepared_file_id,
        avatar.preview_9x16_file_id,
        avatar.preview_16x9_file_id,
    )


# --- caminho feliz --------------------------------------------------------------------


def test_worker_baixa_origem_envia_tres_png_conclui_e_avatar_fica_ativo(
    panel: TestClient, new_avatar, image_bytes, engine: Engine, settings: Settings
):
    avatar_id, source = new_avatar()
    claimed = claim(panel)
    assert claimed["payload"]["avatar_id"] == str(avatar_id)

    downloaded = panel.get(
        f"/internal/v1/files/{claimed['payload']['source_file_id']}", headers=WORKER
    )

    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == source
    assert downloaded.headers["content-type"] == "image/png"

    file_ids = upload_all(panel, image_bytes, claimed)
    attempt_dir = f"assets/{avatar_id}/{claimed['attempt_id']}"
    for field, name in FILE_NAMES.items():
        stored = fresh(engine, StoredFile, uuid.UUID(file_ids[field]))
        assert stored.relative_path == f"{attempt_dir}/{name}"
        assert stored.attempt_id == uuid.UUID(claimed["attempt_id"])
        assert stored.content_type == "image/png"
    # Enviar não publica: o avatar só muda no complete.
    assert avatar_state(engine, avatar_id) == ("preparando", None, None, None, None)

    done = complete(panel, claimed, file_ids)

    assert done.status_code == 200, done.text
    assert done.json()["status"] == "ready"
    task = fresh(engine, AssetPrepareTask, uuid.UUID(claimed["id"]))
    assert (task.status, task.lease_until) == ("ready", None)
    assert avatar_state(engine, avatar_id) == (
        "ativo",
        None,
        *(uuid.UUID(file_ids[field]) for field in FILE_NAMES),
    )
    assert panel.get(f"/panel/avatars/{avatar_id}").json()["status"] == "ativo"
    preview = panel.get(f"/panel/avatars/{avatar_id}/files/preview-9x16")
    assert preview.status_code == 200
    assert preview.content == (settings.data_dir / attempt_dir / "preview-9x16.png").read_bytes()


def test_complete_repetido_pela_mesma_tentativa_devolve_200_sem_alterar(
    panel: TestClient, new_avatar, image_bytes, engine: Engine
):
    avatar_id, _ = new_avatar()
    claimed = claim(panel)
    file_ids = upload_all(panel, image_bytes, claimed)
    first = complete(panel, claimed, file_ids)
    before = (avatar_state(engine, avatar_id), fresh(engine, AssetPrepareTask, claimed["id"]))

    again = complete(panel, claimed, file_ids)

    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    after = (avatar_state(engine, avatar_id), fresh(engine, AssetPrepareTask, claimed["id"]))
    assert after[0] == before[0]
    assert after[1].finished_at == before[1].finished_at
    # Repetir com outros arquivos não é repetição: a tarefa já terminou.
    swapped = dict(file_ids, prepared_file_id=file_ids["preview_9x16_file_id"])
    assert_error(complete(panel, claimed, swapped), 409, "STALE_ATTEMPT")
    assert avatar_state(engine, avatar_id) == before[0]


def test_reenvio_do_mesmo_png_devolve_o_mesmo_arquivo_e_outro_conteudo_e_conflito(
    panel: TestClient, new_avatar, image_bytes
):
    new_avatar()
    claimed = claim(panel)
    data = image_bytes("png", (30, 30))
    args = (panel, claimed["id"], claimed["attempt_id"], 1, "prepared.png")

    first = upload(*args, data)
    again = upload(*args, data)
    other = upload(*args, image_bytes("png", (31, 31)))

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert_error(other, 409, "FILE_EXISTS")


# --- recusas --------------------------------------------------------------------------


@pytest.mark.parametrize("missing", list(FILE_NAMES))
def test_complete_sem_um_dos_tres_arquivos_e_recusado(
    panel: TestClient, new_avatar, image_bytes, engine: Engine, missing
):
    avatar_id, _ = new_avatar()
    claimed = claim(panel)
    file_ids = upload_all(panel, image_bytes, claimed)
    del file_ids[missing]

    assert_error(complete(panel, claimed, file_ids), 422, "INVALID_RESULT", missing)

    assert avatar_state(engine, avatar_id) == ("preparando", None, None, None, None)
    assert fresh(engine, AssetPrepareTask, claimed["id"]).status == "processing"


def test_complete_com_arquivo_de_outro_nome_ou_de_outra_tentativa_e_recusado(
    panel: TestClient, new_avatar, image_bytes, engine: Engine
):
    avatar_id, _ = new_avatar()
    first = claim(panel, "cpu-a")
    old_ids = upload_all(panel, image_bytes, first)
    assert fail(panel, first, retryable=True).json()["status"] == "queued"
    second = claim(panel, "cpu-b")
    new_ids = upload_all(panel, image_bytes, second)

    swapped = dict(new_ids, preview_9x16_file_id=new_ids["preview_16x9_file_id"])
    assert_error(complete(panel, second, swapped), 422, "INVALID_RESULT", "preview_9x16_file_id")
    borrowed = dict(new_ids, prepared_file_id=old_ids["prepared_file_id"])
    assert_error(complete(panel, second, borrowed), 422, "INVALID_RESULT", "prepared_file_id")
    unknown = dict(new_ids, preview_16x9_file_id=str(uuid.uuid4()))
    assert_error(complete(panel, second, unknown), 422, "INVALID_RESULT", "preview_16x9_file_id")

    assert avatar_state(engine, avatar_id) == ("preparando", None, None, None, None)
    assert complete(panel, second, new_ids).status_code == 200
    assert avatar_state(engine, avatar_id)[2] == uuid.UUID(new_ids["prepared_file_id"])


def test_complete_com_arquivo_sumido_do_volume_e_recusado(
    panel: TestClient, new_avatar, image_bytes, engine: Engine, settings: Settings
):
    avatar_id, _ = new_avatar()
    claimed = claim(panel)
    file_ids = upload_all(panel, image_bytes, claimed)
    stored = fresh(engine, StoredFile, uuid.UUID(file_ids["preview_16x9_file_id"]))
    (settings.data_dir / stored.relative_path).unlink()

    response = complete(panel, claimed, file_ids)

    assert_error(response, 422, "INVALID_RESULT", "preview_16x9_file_id")
    assert avatar_state(engine, avatar_id)[0] == "preparando"


@pytest.mark.parametrize(
    ("fmt", "code"),
    [
        ("jpeg", "UNSUPPORTED_FILE_TYPE"),
        ("svg", "UNSUPPORTED_FILE_TYPE"),
        ("lixo", "IMAGE_UNREADABLE"),
    ],
)
def test_envio_que_nao_e_png_e_recusado_sem_deixar_arquivo(
    panel: TestClient, new_avatar, image_bytes, session: Session, settings: Settings, fmt, code
):
    new_avatar()
    claimed = claim(panel)
    before = data_files(settings.data_dir)
    data = {"jpeg": image_bytes("jpeg"), "svg": SVG, "lixo": b"\x89PNG\r\n\x1a\nquebrado"}[fmt]

    response = upload(panel, claimed["id"], claimed["attempt_id"], 1, "prepared.png", data)

    assert_error(response, 422, code, "file")
    assert data_files(settings.data_dir) == before
    assert (
        session.scalar(
            select(func.count()).where(StoredFile.attempt_id == uuid.UUID(claimed["attempt_id"]))
        )
        == 0
    )


def test_envio_com_nome_fora_da_lista_ou_sha_errado_e_recusado(
    panel: TestClient, new_avatar, image_bytes, settings: Settings
):
    new_avatar()
    claimed = claim(panel)
    before = data_files(settings.data_dir)
    data = image_bytes("png")
    args = (panel, claimed["id"], claimed["attempt_id"], 1)

    assert_error(upload(*args, "source.png", data), 422, "VALIDATION_ERROR")
    assert_error(upload(*args, "final.mp4", data), 422, "VALIDATION_ERROR")
    assert_error(upload(*args, "prepared.png", data, digest="0" * 64), 422, "CHECKSUM_MISMATCH")
    assert data_files(settings.data_dir) == before


def test_download_de_arquivo_inexistente_devolve_404(
    panel: TestClient, new_avatar, engine: Engine, settings: Settings
):
    avatar_id, _ = new_avatar()
    assert_error(panel.get(f"/internal/v1/files/{uuid.uuid4()}", headers=WORKER), 404, "NOT_FOUND")

    source = fresh(engine, StoredFile, fresh(engine, Avatar, avatar_id).source_file_id)
    (settings.data_dir / source.relative_path).unlink()
    response = panel.get(f"/internal/v1/files/{source.id}", headers=WORKER)

    assert_error(response, 404, "NOT_FOUND")


def test_rotas_novas_exigem_token_do_worker(panel: TestClient):
    task_id = uuid.uuid4()
    calls = [
        panel.get(f"/internal/v1/files/{uuid.uuid4()}"),
        panel.put(
            f"/internal/v1/asset-tasks/{task_id}/attempts/{uuid.uuid4()}/files/prepared.png",
            files={"file": ("f", b"x")},
            data={"sha256": sha(b"x"), "lease_generation": "1"},
        ),
    ]
    for response in calls:
        assert_error(response, 401, "UNAUTHORIZED")


# --- tentativa obsoleta ---------------------------------------------------------------


def test_tentativa_obsoleta_recebe_409_e_o_avatar_continua_como_estava(
    panel: TestClient, new_avatar, image_bytes, engine: Engine, settings: Settings
):
    avatar_id, _ = new_avatar()
    old = claim(panel, "cpu-a")
    old_ids = upload_all(panel, image_bytes, old)
    expire_lease(engine, old["id"])
    sweep(engine)
    assert avatar_state(engine, avatar_id)[0] == "preparando"
    current = claim(panel, "cpu-b")
    before = data_files(settings.data_dir)

    late_upload = upload(
        panel, old["id"], old["attempt_id"], 1, "prepared.png", image_bytes("png", (33, 33))
    )
    late_complete = complete(panel, old, old_ids)
    late_fail = fail(panel, old, retryable=False)

    for response in (late_upload, late_complete, late_fail):
        assert_error(response, 409, "STALE_ATTEMPT")
    assert data_files(settings.data_dir) == before
    assert avatar_state(engine, avatar_id) == ("preparando", None, None, None, None)
    task = fresh(engine, AssetPrepareTask, current["id"])
    assert (task.status, task.current_attempt_id) == (
        "processing",
        uuid.UUID(current["attempt_id"]),
    )


# --- falhas ---------------------------------------------------------------------------


def test_falha_recuperavel_devolve_a_tarefa_a_fila_e_mantem_preparando(
    panel: TestClient, new_avatar, engine: Engine
):
    avatar_id, _ = new_avatar()
    claimed = claim(panel)

    response = fail(panel, claimed, retryable=True, message="Falha passageira.")

    assert response.json()["status"] == "queued"
    assert avatar_state(engine, avatar_id) == ("preparando", None, None, None, None)
    assert panel.get(f"/panel/avatars/{avatar_id}").json()["status"] == "preparando"


def test_falha_definitiva_deixa_o_avatar_em_falha_com_o_motivo(
    panel: TestClient, new_avatar, engine: Engine
):
    avatar_id, _ = new_avatar()
    claimed = claim(panel)

    response = fail(panel, claimed, retryable=False, message="Nenhuma pessoa encontrada na imagem.")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert avatar_state(engine, avatar_id) == (
        "falha",
        "Nenhuma pessoa encontrada na imagem.",
        None,
        None,
        None,
    )
    body = panel.get(f"/panel/avatars/{avatar_id}").json()
    assert (body["status"], body["prepare_error"]) == (
        "falha",
        "Nenhuma pessoa encontrada na imagem.",
    )


def test_worker_perdido_na_ultima_tentativa_deixa_o_avatar_em_falha(
    panel: TestClient, new_avatar, engine: Engine
):
    avatar_id, _ = new_avatar()
    for _ in range(jobs.MAX_ATTEMPTS - 1):
        task_id = claim(panel)["id"]
        expire_lease(engine, task_id)
        assert sweep(engine) == jobs.SweepResult(requeued=1, lost=0)
        assert avatar_state(engine, avatar_id)[0] == "preparando"
    claim(panel)
    expire_lease(engine, task_id)

    assert sweep(engine) == jobs.SweepResult(requeued=0, lost=1)

    task = fresh(engine, AssetPrepareTask, uuid.UUID(task_id))
    assert (task.status, task.error_code) == ("failed", jobs.WORKER_LOST)
    assert avatar_state(engine, avatar_id) == (
        "falha",
        jobs.WORKER_LOST_MESSAGE,
        None,
        None,
        None,
    )
