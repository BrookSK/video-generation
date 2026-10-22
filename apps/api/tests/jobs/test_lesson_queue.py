import hashlib
import json
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from conftest import lesson_body, logo_png, put_identity
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from avatar_api import jobs
from avatar_api.config import Settings
from avatar_api.db import create_db_engine
from avatar_api.devseed import DevCatalog
from avatar_api.models import BrandIdentity, Lesson, LessonAssembleTask, VideoJob

WORKER = {"Authorization": "Bearer token-do-worker-de-teste"}
VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"cena" * 256
LESSON_VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"aula-montada" * 256


@pytest.fixture
def worker_engine(database_url: str) -> Iterator[Engine]:
    engine = create_db_engine(database_url)
    yield engine
    engine.dispose()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def claim(client: TestClient, kinds: list[str], worker_id: str = "worker-a"):
    return client.post(
        "/internal/v1/claim", json={"worker_id": worker_id, "kinds": kinds}, headers=WORKER
    )


def upload(client, path: str, item_id, attempt_id, generation, name="final.mp4", data=VIDEO):
    return client.put(
        f"/internal/v1/{path}/{item_id}/attempts/{attempt_id}/files/{name}",
        files={"file": (name, data, "application/octet-stream")},
        data={"sha256": sha(data), "lease_generation": str(generation)},
        headers=WORKER,
    )


def ref(claimed: dict) -> dict:
    return {"attempt_id": claimed["attempt_id"], "lease_generation": claimed["lease_generation"]}


def finish_scene(client: TestClient, claimed: dict) -> dict:
    stored = upload(
        client, "jobs", claimed["id"], claimed["attempt_id"], claimed["lease_generation"]
    )
    assert stored.status_code == 201, stored.text
    response = client.post(
        f"/internal/v1/jobs/{claimed['id']}/complete",
        json={**ref(claimed), "result_file_id": stored.json()["id"]},
        headers=WORKER,
    )
    assert response.status_code == 200, response.text
    return response.json()


def claim_scene(client: TestClient) -> dict:
    response = claim(client, ["video"], worker_id="gpu")
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "video"
    return response.json()


def finish_all_scenes(client: TestClient) -> None:
    while (response := claim(client, ["video"], worker_id="gpu")).status_code == 200:
        finish_scene(client, response.json())
    assert response.status_code == 204


def create_lesson(client: TestClient, catalog: DevCatalog, **overrides) -> str:
    response = client.post("/panel/lessons", json=lesson_body(catalog, **overrides))
    assert response.status_code == 202, response.text
    return response.json()["id"]


def fresh_lesson(engine: Engine, lesson_id) -> Lesson:
    with Session(engine) as db:
        return db.get(Lesson, uuid.UUID(str(lesson_id)))


def task_count(engine: Engine) -> int:
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(LessonAssembleTask))


def claim_assembly(client: TestClient) -> dict:
    response = claim(client, ["lesson_assemble"], worker_id="cpu")
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "lesson_assemble"
    return response.json()


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- cenas -> montagem ------------------------------------------------------------------


def test_payload_da_cena_leva_o_plano_e_o_avulso_fica_em_medio(
    lesson_panel, brand, seeded_catalog
):
    create_lesson(
        lesson_panel,
        seeded_catalog,
        scenes=[{"script_text": "Só close.", "shot": "close"}] * 2,
    )
    single = lesson_panel.post(
        "/panel/jobs",
        json={
            "script_text": "Avulso.",
            "avatar_id": str(seeded_catalog.avatar_id),
            "scene_id": str(seeded_catalog.scene_id),
        },
    )
    assert single.status_code == 202, single.text

    shots = {}
    for _ in range(3):
        claimed = claim_scene(lesson_panel)
        shots[claimed["id"]] = claimed["payload"]["shot"]

    assert shots.pop(single.json()["id"]) == "medio"
    assert list(shots.values()) == ["close", "close"]


def test_ultima_cena_pronta_enfileira_uma_montagem_e_aula_vai_a_assembling(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    finish_scene(lesson_panel, claim_scene(lesson_panel))
    finish_scene(lesson_panel, claim_scene(lesson_panel))
    assert fresh_lesson(worker_engine, lesson_id).status == "queued"
    assert task_count(worker_engine) == 0

    finish_scene(lesson_panel, claim_scene(lesson_panel))

    assert fresh_lesson(worker_engine, lesson_id).status == "assembling"
    assert task_count(worker_engine) == 1
    lesson = lesson_panel.get(f"/panel/lessons/{lesson_id}").json()
    assert lesson["status"] == "assembling"
    assert [scene["status"] for scene in lesson["scenes"]] == ["ready"] * 3


def test_claim_de_outros_tipos_nao_pega_a_montagem(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    create_lesson(lesson_panel, seeded_catalog)
    finish_all_scenes(lesson_panel)
    assert task_count(worker_engine) == 1

    response = claim(lesson_panel, ["video", "asset_prepare"])

    assert response.status_code == 204
    claimed = claim_assembly(lesson_panel)
    assert claimed["payload"]["lesson_id"]


def _lock_waiters(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE wait_event_type = 'Lock' AND datname = current_database()"
            )
        ).scalar()


def test_duas_conclusoes_concorrentes_geram_uma_so_montagem(
    lesson_panel, brand, seeded_catalog, worker_engine, settings: Settings
):
    lesson_id = create_lesson(
        lesson_panel, seeded_catalog, scenes=[{"script_text": "A."}, {"script_text": "B."}]
    )
    ready = []
    for _ in range(2):
        claimed = claim_scene(lesson_panel)
        stored = upload(
            lesson_panel, "jobs", claimed["id"], claimed["attempt_id"], claimed["lease_generation"]
        )
        ready.append((claimed, stored.json()["id"]))

    # A aula travada por fora força as duas conclusões a gravar a cena antes de contar.
    blocker = Session(worker_engine)
    blocker.scalar(select(Lesson).where(Lesson.id == uuid.UUID(lesson_id)).with_for_update())
    errors = []

    def complete(claimed: dict, file_id: str) -> None:
        try:
            with Session(worker_engine) as db:
                jobs.complete_item(
                    db,
                    "video",
                    uuid.UUID(claimed["id"]),
                    uuid.UUID(claimed["attempt_id"]),
                    claimed["lease_generation"],
                    settings.data_dir,
                    result_file_id=uuid.UUID(file_id),
                )
        except Exception as exc:  # pragma: no cover - diagnóstico do teste
            errors.append(exc)

    threads = [threading.Thread(target=complete, args=item) for item in ready]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 10
    while _lock_waiters(worker_engine) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _lock_waiters(worker_engine) == 2
    blocker.rollback()
    blocker.close()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert task_count(worker_engine) == 1
    assert fresh_lesson(worker_engine, lesson_id).status == "assembling"


# --- falhas de cena ---------------------------------------------------------------------


def test_falha_definitiva_de_cena_deixa_aula_em_falha_sem_montagem(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    with Session(worker_engine) as db:
        second = db.scalar(
            select(VideoJob.id).where(
                VideoJob.lesson_id == uuid.UUID(lesson_id), VideoJob.lesson_position == 2
            )
        )
    while True:
        claimed = claim_scene(lesson_panel)
        if claimed["id"] == str(second):
            break
        finish_scene(lesson_panel, claimed)

    response = lesson_panel.post(
        f"/internal/v1/jobs/{second}/fail",
        json={
            **ref(claimed),
            "error_code": "RENDER_FAILED",
            "error_message": "Falha no render.",
            "retryable": False,
        },
        headers=WORKER,
    )
    assert response.status_code == 200, response.text
    finish_all_scenes(lesson_panel)

    lesson = fresh_lesson(worker_engine, lesson_id)
    assert lesson.status == "failed"
    assert lesson.error_code == "SCENE_FAILED"
    assert lesson.error_message == "A cena 2 falhou: Falha no render."
    assert task_count(worker_engine) == 0
    shown = lesson_panel.get(f"/panel/lessons/{lesson_id}").json()
    assert shown["error"] == {
        "code": "SCENE_FAILED",
        "message": "A cena 2 falhou: Falha no render.",
    }
    assert shown["scenes"][1]["error"]["code"] == "RENDER_FAILED"
    assert_error(lesson_panel.get(f"/panel/lessons/{lesson_id}/download"), 409, "LESSON_FAILED")


def test_falha_temporaria_de_cena_nao_derruba_a_aula(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    claimed = claim_scene(lesson_panel)

    response = lesson_panel.post(
        f"/internal/v1/jobs/{claimed['id']}/fail",
        json={**ref(claimed), "error_code": "TRANSIENT", "error_message": "x", "retryable": True},
        headers=WORKER,
    )

    assert response.json()["status"] == "queued"
    assert fresh_lesson(worker_engine, lesson_id).status == "queued"


def test_worker_lost_na_cena_deixa_aula_em_falha(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    claimed = claim_scene(lesson_panel)
    with Session(worker_engine) as db:
        db.execute(
            update(VideoJob)
            .where(VideoJob.id == uuid.UUID(claimed["id"]))
            .values(attempt=jobs.MAX_ATTEMPTS, lease_until=func.now() - text("interval '1 s'"))
        )
        db.commit()
        position = db.get(VideoJob, uuid.UUID(claimed["id"])).lesson_position

    with Session(worker_engine) as db:
        result = jobs.sweep_expired_leases(db)

    assert result.lost == 1
    lesson = fresh_lesson(worker_engine, lesson_id)
    assert lesson.status == "failed"
    assert lesson.error_message == f"A cena {position} falhou: {jobs.WORKER_LOST_MESSAGE}"


# --- montagem: payload, publicação e tentativa obsoleta ----------------------------------


def test_payload_congelado_depois_de_trocar_a_identidade(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    with Session(worker_engine) as db:
        old_logo = db.get(BrandIdentity, 1).logo_file_id
    put_identity(lesson_panel, logo_png((1, 2, 3)), "#000000", "#FFFFFF")
    finish_all_scenes(lesson_panel)

    payload = claim_assembly(lesson_panel)["payload"]

    with Session(worker_engine) as db:
        results = dict(
            db.execute(
                select(VideoJob.lesson_position, VideoJob.result_file_id).where(
                    VideoJob.lesson_id == uuid.UUID(lesson_id)
                )
            ).all()
        )
    assert payload == {
        "lesson_id": lesson_id,
        "aspect_ratio": "16:9",
        "logo_file_id": str(old_logo),
        "background_color": "#0B2545",
        "accent_color": "#F2A541",
        "scenes": [
            {"position": 1, "shot": "medio", "file_id": str(results[1])},
            {"position": 2, "shot": "close", "file_id": str(results[2])},
            {"position": 3, "shot": "medio", "file_id": str(results[3])},
        ],
    }
    logo = lesson_panel.get(f"/internal/v1/files/{old_logo}", headers=WORKER)
    assert logo.status_code == 200
    assert logo.content == logo_png()


def test_montagem_publica_final_e_painel_entrega_o_mp4(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    finish_all_scenes(lesson_panel)
    task = claim_assembly(lesson_panel)
    heartbeat = lesson_panel.post(
        f"/internal/v1/lesson-tasks/{task['id']}/heartbeat", json=ref(task), headers=WORKER
    )
    assert heartbeat.status_code == 200, heartbeat.text
    manifest = json.dumps({"lesson_id": lesson_id}).encode()
    stored_manifest = upload(
        lesson_panel,
        "lesson-tasks",
        task["id"],
        task["attempt_id"],
        task["lease_generation"],
        name="manifest.json",
        data=manifest,
    )
    assert stored_manifest.status_code == 201, stored_manifest.text
    stored = upload(
        lesson_panel,
        "lesson-tasks",
        task["id"],
        task["attempt_id"],
        task["lease_generation"],
        data=LESSON_VIDEO,
    )
    assert stored.status_code == 201, stored.text

    response = lesson_panel.post(
        f"/internal/v1/lesson-tasks/{task['id']}/complete",
        json={**ref(task), "result_file_id": stored.json()["id"]},
        headers=WORKER,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"
    lesson = fresh_lesson(worker_engine, lesson_id)
    assert (lesson.status, str(lesson.result_file_id)) == ("ready", stored.json()["id"])
    shown = lesson_panel.get(f"/panel/lessons/{lesson_id}").json()
    assert shown["download_url"] == f"/panel/lessons/{lesson_id}/download"
    assert shown["size_bytes"] == len(LESSON_VIDEO)
    download = lesson_panel.get(shown["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "video/mp4"
    assert download.content == LESSON_VIDEO
    again = lesson_panel.post(
        f"/internal/v1/lesson-tasks/{task['id']}/complete",
        json={**ref(task), "result_file_id": stored.json()["id"]},
        headers=WORKER,
    )
    assert again.status_code == 200


def test_complete_exige_o_final_da_tentativa(lesson_panel, brand, seeded_catalog, worker_engine):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    finish_all_scenes(lesson_panel)
    task = claim_assembly(lesson_panel)
    manifest = upload(
        lesson_panel,
        "lesson-tasks",
        task["id"],
        task["attempt_id"],
        task["lease_generation"],
        name="manifest.json",
        data=b"{}",
    )

    response = lesson_panel.post(
        f"/internal/v1/lesson-tasks/{task['id']}/complete",
        json={**ref(task), "result_file_id": manifest.json()["id"]},
        headers=WORKER,
    )

    assert_error(response, 422, "RESULT_FILE_INVALID")
    assert fresh_lesson(worker_engine, lesson_id).status == "assembling"
    bad_name = upload(
        lesson_panel, "lesson-tasks", task["id"], task["attempt_id"], 1, name="render.mp4"
    )
    assert bad_name.status_code == 422


def test_tentativa_obsoleta_recebe_409_e_aula_nao_muda(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    finish_all_scenes(lesson_panel)
    old = claim_assembly(lesson_panel)
    stored = upload(
        lesson_panel, "lesson-tasks", old["id"], old["attempt_id"], old["lease_generation"]
    )
    with Session(worker_engine) as db:
        db.execute(
            update(LessonAssembleTask)
            .where(LessonAssembleTask.id == uuid.UUID(old["id"]))
            .values(lease_until=func.now() - text("interval '1 s'"))
        )
        db.commit()
    with Session(worker_engine) as db:
        assert jobs.sweep_expired_leases(db).requeued == 1
    current = claim_assembly(lesson_panel)
    assert current["attempt_id"] != old["attempt_id"]

    for response in (
        lesson_panel.post(
            f"/internal/v1/lesson-tasks/{old['id']}/complete",
            json={**ref(old), "result_file_id": stored.json()["id"]},
            headers=WORKER,
        ),
        lesson_panel.post(
            f"/internal/v1/lesson-tasks/{old['id']}/heartbeat", json=ref(old), headers=WORKER
        ),
        upload(lesson_panel, "lesson-tasks", old["id"], old["attempt_id"], 1, data=b"outro"),
    ):
        assert_error(response, 409, "STALE_ATTEMPT")
    lesson = fresh_lesson(worker_engine, lesson_id)
    assert (lesson.status, lesson.result_file_id) == ("assembling", None)


def test_falha_da_montagem_retry_e_falha_definitiva(
    lesson_panel, brand, seeded_catalog, worker_engine
):
    lesson_id = create_lesson(lesson_panel, seeded_catalog)
    finish_all_scenes(lesson_panel)

    def fail(task: dict, retryable: bool, code: str):
        return lesson_panel.post(
            f"/internal/v1/lesson-tasks/{task['id']}/fail",
            json={
                **ref(task),
                "error_code": code,
                "error_message": "A cena 2 tem resolução diferente do formato da aula.",
                "retryable": retryable,
            },
            headers=WORKER,
        )

    first = fail(claim_assembly(lesson_panel), True, "TRANSIENT")
    assert first.json()["status"] == "queued"
    assert fresh_lesson(worker_engine, lesson_id).status == "assembling"

    final = fail(claim_assembly(lesson_panel), False, "OUTPUT_INVALID")

    assert final.json()["status"] == "failed"
    lesson = fresh_lesson(worker_engine, lesson_id)
    assert (lesson.status, lesson.error_code) == ("failed", "OUTPUT_INVALID")
    assert lesson.error_message == (
        "A montagem da aula falhou: A cena 2 tem resolução diferente do formato da aula."
    )
