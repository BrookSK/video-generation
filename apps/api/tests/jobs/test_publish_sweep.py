import hashlib
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from avatar_api import jobs
from avatar_api.auth import IssuedApiKey, create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.db import create_db_engine
from avatar_api.devseed import DevCatalog
from avatar_api.main import create_app
from avatar_api.models import AssetPrepareTask, JobAttempt, StoredFile, VideoJob

WORKER = {"Authorization": "Bearer token-do-worker-de-teste"}
VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"conteudo-final" * 64


@pytest.fixture
def api_key(session: Session) -> IssuedApiKey:
    user = create_user(session, "admin", "senha-de-teste-bem-longa")
    return issue_api_key(session, user.id, "ERP")


@pytest.fixture
def make_job(session: Session, seeded_catalog: DevCatalog, api_key: IssuedApiKey):
    def make() -> uuid.UUID:
        payload = jobs.NewVideoJob(
            script_text=f"Vídeo {uuid.uuid4()}.",
            avatar_id=seeded_catalog.avatar_id,
            scene_id=seeded_catalog.scene_id,
        )
        requester = jobs.JobRequester(origin="api", api_key_id=api_key.row.id)
        return jobs.create_video_job(session, requester, payload).id

    return make


@pytest.fixture
def make_task(session: Session, seeded_catalog: DevCatalog):
    def make() -> uuid.UUID:
        task = AssetPrepareTask(avatar_id=seeded_catalog.avatar_id)
        session.add(task)
        session.commit()
        return task.id

    return make


@pytest.fixture
def worker_engine(database_url: str) -> Iterator[Engine]:
    engine = create_db_engine(database_url)
    yield engine
    engine.dispose()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def claim(client: TestClient, kind: str, worker_id: str = "worker-a") -> dict:
    response = client.post(
        "/internal/v1/claim", json={"worker_id": worker_id, "kinds": [kind]}, headers=WORKER
    )
    assert response.status_code == 200, response.text
    return response.json()


def upload(client, job_id, attempt_id, generation, name="final.mp4", data=VIDEO, digest=None):
    return client.put(
        f"/internal/v1/jobs/{job_id}/attempts/{attempt_id}/files/{name}",
        files={"file": (name, data, "application/octet-stream")},
        data={"sha256": digest or sha(data), "lease_generation": str(generation)},
        headers=WORKER,
    )


def complete(client, job_id, attempt_id, generation, result_file_id, **extra):
    return client.post(
        f"/internal/v1/jobs/{job_id}/complete",
        json={
            "attempt_id": str(attempt_id),
            "lease_generation": generation,
            "result_file_id": str(result_file_id),
            **extra,
        },
        headers=WORKER,
    )


def fail(client, path, item_id, attempt_id, generation, retryable, code="TRANSIENT"):
    return client.post(
        f"/internal/v1/{path}/{item_id}/fail",
        json={
            "attempt_id": str(attempt_id),
            "lease_generation": generation,
            "error_code": code,
            "error_message": "Falha simulada no teste.",
            "retryable": retryable,
        },
        headers=WORKER,
    )


def complete_task(client, task_id, attempt_id, generation):
    return client.post(
        f"/internal/v1/asset-tasks/{task_id}/complete",
        json={"attempt_id": str(attempt_id), "lease_generation": generation},
        headers=WORKER,
    )


def fresh(engine: Engine, model, item_id):
    with Session(engine) as reader:
        return reader.get(model, item_id)


def expire_lease(engine: Engine, model, item_id: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(model)
            .where(model.id == item_id)
            .values(lease_until=func.now() - text("interval '1 second'"))
        )


def sweep(engine: Engine) -> jobs.SweepResult:
    with Session(engine) as session:
        return jobs.sweep_expired_leases(session)


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def snapshot(engine: Engine, job_id: uuid.UUID) -> tuple:
    job = fresh(engine, VideoJob, job_id)
    return (
        job.status,
        job.result_file_id,
        job.lease_generation,
        job.attempt,
        job.current_attempt_id,
        job.lease_until,
        job.finished_at,
    )


# --- caminho feliz --------------------------------------------------------------------


def test_tentativa_vigente_envia_final_e_conclui_com_ready(
    client: TestClient, make_job, worker_engine: Engine, settings: Settings, api_key
):
    job_id = make_job()
    data = claim(client, "video")
    attempt_id = data["attempt_id"]

    sent = upload(client, job_id, attempt_id, 1)

    assert sent.status_code == 201, sent.text
    file_out = sent.json()
    assert file_out["name"] == "final.mp4"
    assert file_out["sha256"] == sha(VIDEO)
    assert (file_out["size_bytes"], file_out["content_type"]) == (len(VIDEO), "video/mp4")
    stored = fresh(worker_engine, StoredFile, uuid.UUID(file_out["id"]))
    assert stored.relative_path == f"jobs/{job_id}/{attempt_id}/final.mp4"
    assert stored.attempt_id == uuid.UUID(attempt_id)
    assert (settings.data_dir / stored.relative_path).read_bytes() == VIDEO
    # Antes do complete o job continua em processing e sem resultado.
    assert fresh(worker_engine, VideoJob, job_id).status == "processing"
    assert fresh(worker_engine, VideoJob, job_id).result_file_id is None

    done = complete(
        client,
        job_id,
        attempt_id,
        1,
        file_out["id"],
        stage_timings={"tts": 1.5, "render": 40.0},
        peak_vram_mb=18000,
    )

    assert done.status_code == 200, done.text
    job = fresh(worker_engine, VideoJob, job_id)
    attempt = fresh(worker_engine, JobAttempt, uuid.UUID(attempt_id))
    body = done.json()
    assert (body["id"], body["status"], body["result_file_id"]) == (
        str(job_id),
        "ready",
        file_out["id"],
    )
    assert datetime.fromisoformat(body["finished_at"]) == job.finished_at
    assert (job.status, job.result_file_id, job.lease_until) == ("ready", stored.id, None)
    # ready, result_file_id, finished_at e o outcome vêm do mesmo commit (mesmo now()).
    assert job.finished_at == attempt.finished_at
    assert attempt.outcome == "completed"
    assert attempt.stage_timings == {"tts": 1.5, "render": 40.0}
    assert attempt.peak_vram_mb == 18000

    # O sistema externo vê ready e baixa exatamente o arquivo enviado.
    public = {"Authorization": f"Bearer {api_key.key}"}
    status = client.get(f"/api/v1/jobs/{job_id}", headers=public).json()
    assert (status["status"], status["download_url"]) == (
        "ready",
        f"/api/v1/jobs/{job_id}/download",
    )
    download = client.get(status["download_url"], headers=public)
    assert download.status_code == 200
    assert sha(download.content) == sha(VIDEO)


def test_complete_repetido_pela_mesma_tentativa_devolve_o_mesmo_resultado(
    client: TestClient, make_job, worker_engine: Engine
):
    job_id = make_job()
    data = claim(client, "video")
    file_id = upload(client, job_id, data["attempt_id"], 1).json()["id"]
    first = complete(client, job_id, data["attempt_id"], 1, file_id)
    before = snapshot(worker_engine, job_id)

    again = complete(client, job_id, data["attempt_id"], 1, file_id)

    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    assert snapshot(worker_engine, job_id) == before
    # Outro arquivo na repetição não é o mesmo resultado: recusado sem mudar o job.
    other = complete(client, job_id, data["attempt_id"], 1, uuid.uuid4())
    assert_error(other, 409, "STALE_ATTEMPT")
    assert snapshot(worker_engine, job_id) == before


# --- envio de arquivos ----------------------------------------------------------------


def test_reenvio_com_mesmo_sha_devolve_o_existente_e_sha_diferente_da_409(
    client: TestClient, make_job, worker_engine: Engine, settings: Settings
):
    job_id = make_job()
    data = claim(client, "video")
    first = upload(client, job_id, data["attempt_id"], 1)

    again = upload(client, job_id, data["attempt_id"], 1)
    other = upload(client, job_id, data["attempt_id"], 1, data=b"outro conteudo")

    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    assert_error(other, 409, "FILE_EXISTS")
    path = settings.data_dir / f"jobs/{job_id}/{data['attempt_id']}/final.mp4"
    assert path.read_bytes() == VIDEO
    with Session(worker_engine) as reader:
        assert (
            reader.scalar(
                select(func.count())
                .select_from(StoredFile)
                .where(StoredFile.attempt_id == uuid.UUID(data["attempt_id"]))
            )
            == 1
        )


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("audio.wav", "audio/wav"),
        ("render.mp4", "video/mp4"),
        ("manifest.json", "application/json"),
    ],
)
def test_nomes_aceitos_gravam_na_pasta_da_tentativa(
    client: TestClient, make_job, worker_engine: Engine, name: str, content_type: str
):
    job_id = make_job()
    data = claim(client, "video")

    response = upload(client, job_id, data["attempt_id"], 1, name=name, data=b"x" * 10)

    assert response.status_code == 201, response.text
    stored = fresh(worker_engine, StoredFile, uuid.UUID(response.json()["id"]))
    assert stored.relative_path == f"jobs/{job_id}/{data['attempt_id']}/{name}"
    assert stored.content_type == content_type


@pytest.mark.parametrize(
    ("name", "digest", "code"),
    [
        ("outro.mp4", None, "VALIDATION_ERROR"),
        ("..final.mp4", None, "VALIDATION_ERROR"),
        ("final.mp4", "abc", "VALIDATION_ERROR"),
        ("final.mp4", "0" * 64, "CHECKSUM_MISMATCH"),
    ],
)
def test_envio_invalido_devolve_422_sem_gravar(
    client: TestClient, make_job, worker_engine: Engine, settings: Settings, name, digest, code
):
    job_id = make_job()
    data = claim(client, "video")

    response = upload(client, job_id, data["attempt_id"], 1, name=name, digest=digest)

    assert_error(response, 422, code)
    with Session(worker_engine) as reader:
        assert (
            reader.scalar(
                select(func.count())
                .select_from(StoredFile)
                .where(StoredFile.attempt_id.is_not(None))
            )
            == 0
        )
    assert not list(settings.data_dir.glob("jobs/**/*.mp4"))


def test_envio_acima_do_limite_devolve_413(settings: Settings, make_job, worker_engine):
    job_id = make_job()
    with TestClient(create_app(replace(settings, max_upload_bytes=10))) as client:
        data = claim(client, "video")
        response = upload(client, job_id, data["attempt_id"], 1)

    assert_error(response, 413, "PAYLOAD_TOO_LARGE")
    with Session(worker_engine) as reader:
        assert (
            reader.scalar(
                select(func.count())
                .select_from(StoredFile)
                .where(StoredFile.attempt_id.is_not(None))
            )
            == 0
        )


def test_envio_de_job_inexistente_devolve_404(client: TestClient, make_job):
    make_job()
    data = claim(client, "video")
    assert_error(upload(client, uuid.uuid4(), data["attempt_id"], 1), 404, "NOT_FOUND")


# --- tentativa obsoleta ---------------------------------------------------------------


def test_tentativa_obsoleta_nunca_publica_depois_de_novo_claim(
    client: TestClient, make_job, worker_engine: Engine, settings: Settings
):
    job_id = make_job()
    a = claim(client, "video", "worker-a")
    a_file = upload(client, job_id, a["attempt_id"], 1).json()["id"]
    # A para de mandar heartbeat: o lease vence e o varredor devolve o job à fila.
    expire_lease(worker_engine, VideoJob, job_id)
    assert sweep(worker_engine) == jobs.SweepResult(requeued=1, lost=0)
    b = claim(client, "video", "worker-b")
    assert (b["lease_generation"], fresh(worker_engine, VideoJob, job_id).attempt) == (2, 2)
    current = snapshot(worker_engine, job_id)

    refused = [
        complete(client, job_id, a["attempt_id"], 1, a_file),
        complete(client, job_id, a["attempt_id"], 2, a_file),
        complete(client, job_id, b["attempt_id"], 1, a_file),
        upload(client, job_id, a["attempt_id"], 1, data=b"tardio"),
        upload(client, job_id, a["attempt_id"], 2, data=b"tardio"),
        fail(client, "jobs", job_id, a["attempt_id"], 1, retryable=False),
    ]

    for response in refused:
        assert_error(response, 409, "STALE_ATTEMPT")
        assert snapshot(worker_engine, job_id) == current
    assert not (settings.data_dir / f"jobs/{job_id}/{a['attempt_id']}/tardio").exists()
    assert fresh(worker_engine, JobAttempt, uuid.UUID(a["attempt_id"])).outcome == "expired"

    # B, vigente, também não publica o final.mp4 que A gravou.
    assert_error(complete(client, job_id, b["attempt_id"], 2, a_file), 422, "RESULT_FILE_INVALID")
    assert snapshot(worker_engine, job_id) == current

    b_file = upload(client, job_id, b["attempt_id"], 2).json()["id"]
    assert complete(client, job_id, b["attempt_id"], 2, b_file).status_code == 200
    published = snapshot(worker_engine, job_id)
    assert published[:3] == ("ready", uuid.UUID(b_file), 2)

    # Depois do ready, A continua recusado e o resultado de B fica.
    assert_error(complete(client, job_id, a["attempt_id"], 1, a_file), 409, "STALE_ATTEMPT")
    assert_error(complete(client, job_id, a["attempt_id"], 2, b_file), 409, "STALE_ATTEMPT")
    assert_error(fail(client, "jobs", job_id, b["attempt_id"], 2, True), 409, "STALE_ATTEMPT")
    assert snapshot(worker_engine, job_id) == published


def test_complete_com_lease_vencido_antes_da_varredura_devolve_409(
    client: TestClient, make_job, worker_engine: Engine
):
    job_id = make_job()
    data = claim(client, "video")
    file_id = upload(client, job_id, data["attempt_id"], 1).json()["id"]
    expire_lease(worker_engine, VideoJob, job_id)
    before = snapshot(worker_engine, job_id)

    assert_error(complete(client, job_id, data["attempt_id"], 1, file_id), 409, "STALE_ATTEMPT")
    assert_error(
        upload(client, job_id, data["attempt_id"], 1, name="audio.wav"), 409, "STALE_ATTEMPT"
    )
    assert_error(fail(client, "jobs", job_id, data["attempt_id"], 1, True), 409, "STALE_ATTEMPT")
    assert snapshot(worker_engine, job_id) == before


@pytest.mark.parametrize("case", ["outro_nome", "inexistente", "sem_arquivo_no_volume"])
def test_complete_so_aceita_o_final_mp4_integro_da_propria_tentativa(
    client: TestClient, make_job, worker_engine: Engine, settings: Settings, case: str
):
    job_id = make_job()
    data = claim(client, "video")
    if case == "outro_nome":
        file_id = upload(client, job_id, data["attempt_id"], 1, name="render.mp4").json()["id"]
    elif case == "inexistente":
        file_id = str(uuid.uuid4())
    else:
        file_id = upload(client, job_id, data["attempt_id"], 1).json()["id"]
        (settings.data_dir / f"jobs/{job_id}/{data['attempt_id']}/final.mp4").unlink()
    before = snapshot(worker_engine, job_id)

    response = complete(client, job_id, data["attempt_id"], 1, file_id)

    assert_error(response, 422, "RESULT_FILE_INVALID")
    assert response.json()["error"]["field"] == "result_file_id"
    assert snapshot(worker_engine, job_id) == before
    assert fresh(worker_engine, JobAttempt, uuid.UUID(data["attempt_id"])).outcome == "running"


def test_final_de_outro_job_nao_publica(client: TestClient, make_job, worker_engine: Engine):
    first, second = make_job(), make_job()
    a = claim(client, "video", "a")
    b = claim(client, "video", "b")
    assert {a["id"], b["id"]} == {str(first), str(second)}
    a_file = upload(client, a["id"], a["attempt_id"], 1).json()["id"]

    response = complete(client, b["id"], b["attempt_id"], 1, a_file)

    assert_error(response, 422, "RESULT_FILE_INVALID")
    assert fresh(worker_engine, VideoJob, uuid.UUID(b["id"])).status == "processing"


# --- fail -----------------------------------------------------------------------------


def test_fail_retryable_reenfileira_ate_a_terceira_tentativa(
    client: TestClient, make_job, worker_engine: Engine
):
    job_id = make_job()
    for attempt_number in (1, 2):
        data = claim(client, "video")
        response = fail(client, "jobs", job_id, data["attempt_id"], attempt_number, True)
        assert response.status_code == 200, response.text
        assert response.json() == {"id": str(job_id), "status": "queued", "attempt": attempt_number}
        job = fresh(worker_engine, VideoJob, job_id)
        assert (job.status, job.stage, job.lease_until, job.error_code) == (
            "queued",
            "waiting",
            None,
            None,
        )
        attempt = fresh(worker_engine, JobAttempt, uuid.UUID(data["attempt_id"]))
        assert (attempt.outcome, attempt.error_code) == ("failed", "TRANSIENT")
        assert attempt.finished_at is not None

    last = claim(client, "video")
    assert last["lease_generation"] == 3
    response = fail(client, "jobs", job_id, last["attempt_id"], 3, True)

    assert response.json() == {"id": str(job_id), "status": "failed", "attempt": 3}
    job = fresh(worker_engine, VideoJob, job_id)
    assert (job.status, job.error_code, job.error_message) == (
        "failed",
        "TRANSIENT",
        "Falha simulada no teste.",
    )
    assert job.finished_at is not None
    assert job.result_file_id is None


def test_fail_nao_retryable_deixa_failed_na_primeira(
    client: TestClient, make_job, worker_engine: Engine, api_key
):
    job_id = make_job()
    data = claim(client, "video")

    response = fail(client, "jobs", job_id, data["attempt_id"], 1, False, code="INPUT_INVALID")

    assert response.json()["status"] == "failed"
    public = {"Authorization": f"Bearer {api_key.key}"}
    status = client.get(f"/api/v1/jobs/{job_id}", headers=public).json()
    assert status["error"] == {"code": "INPUT_INVALID", "message": "Falha simulada no teste."}


@pytest.mark.parametrize(
    "body",
    [
        {"error_code": "minusculo"},
        {"error_message": ""},
        {"retryable": None},
    ],
)
def test_fail_com_corpo_invalido_devolve_422(client: TestClient, make_job, worker_engine, body):
    job_id = make_job()
    data = claim(client, "video")
    payload = {
        "attempt_id": data["attempt_id"],
        "lease_generation": 1,
        "error_code": "TRANSIENT",
        "error_message": "x",
        "retryable": True,
        **body,
    }

    response = client.post(f"/internal/v1/jobs/{job_id}/fail", json=payload, headers=WORKER)

    assert_error(response, 422, "VALIDATION_ERROR")
    assert fresh(worker_engine, VideoJob, job_id).status == "processing"


# --- asset_prepare --------------------------------------------------------------------


def test_asset_task_conclui_e_repete_com_o_mesmo_resultado(
    client: TestClient, make_task, worker_engine: Engine
):
    task_id = make_task()
    data = claim(client, "asset_prepare")

    first = complete_task(client, task_id, data["attempt_id"], 1)
    again = complete_task(client, task_id, data["attempt_id"], 1)

    assert first.status_code == 200, first.text
    assert again.json() == first.json()
    task = fresh(worker_engine, AssetPrepareTask, task_id)
    assert (task.status, task.lease_until) == ("ready", None)
    assert first.json()["status"] == "ready"
    assert first.json()["result_file_id"] is None


def test_asset_task_obsoleta_e_recusada_e_fail_reenfileira(
    client: TestClient, make_task, worker_engine: Engine
):
    task_id = make_task()
    a = claim(client, "asset_prepare", "cpu-a")
    assert fail(client, "asset-tasks", task_id, a["attempt_id"], 1, True).json()["status"] == (
        "queued"
    )
    b = claim(client, "asset_prepare", "cpu-b")
    current = fresh(worker_engine, AssetPrepareTask, task_id)

    assert_error(complete_task(client, task_id, a["attempt_id"], 1), 409, "STALE_ATTEMPT")
    assert_error(complete_task(client, task_id, a["attempt_id"], 2), 409, "STALE_ATTEMPT")
    assert_error(
        fail(client, "asset-tasks", task_id, a["attempt_id"], 1, False), 409, "STALE_ATTEMPT"
    )
    after = fresh(worker_engine, AssetPrepareTask, task_id)
    assert (after.status, after.lease_generation, after.current_attempt_id) == (
        "processing",
        2,
        uuid.UUID(b["attempt_id"]),
    )
    assert after.lease_until == current.lease_until

    assert complete_task(client, task_id, b["attempt_id"], 2).json()["status"] == "ready"


def test_rotas_de_publicacao_exigem_token_do_worker(client: TestClient, make_job, make_task):
    job_id = make_job()
    task_id = make_task()
    ref = {"attempt_id": str(uuid.uuid4()), "lease_generation": 1}
    calls = [
        client.put(
            f"/internal/v1/jobs/{job_id}/attempts/{uuid.uuid4()}/files/final.mp4",
            files={"file": ("f", b"x")},
            data={"sha256": sha(b"x"), "lease_generation": "1"},
        ),
        client.post(f"/internal/v1/jobs/{job_id}/complete", json=ref),
        client.post(f"/internal/v1/jobs/{job_id}/fail", json=ref),
        client.post(f"/internal/v1/asset-tasks/{task_id}/complete", json=ref),
        client.post(f"/internal/v1/asset-tasks/{task_id}/fail", json=ref),
    ]
    for response in calls:
        assert_error(response, 401, "UNAUTHORIZED")


# --- varredura ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "model"), [("video", VideoJob), ("asset_prepare", AssetPrepareTask)]
)
def test_lease_vencido_volta_a_fila_ate_a_terceira_e_depois_worker_lost(
    client: TestClient, make_job, make_task, worker_engine: Engine, kind, model
):
    item_id = make_job() if kind == "video" else make_task()
    attempts = []
    for number in (1, 2):
        attempts.append(claim(client, kind)["attempt_id"])
        expire_lease(worker_engine, model, item_id)

        assert sweep(worker_engine) == jobs.SweepResult(requeued=1, lost=0)

        item = fresh(worker_engine, model, item_id)
        assert (item.status, item.attempt, item.lease_generation, item.lease_until) == (
            "queued",
            number,
            number,
            None,
        )
    attempts.append(claim(client, kind)["attempt_id"])
    expire_lease(worker_engine, model, item_id)

    assert sweep(worker_engine) == jobs.SweepResult(requeued=0, lost=1)

    item = fresh(worker_engine, model, item_id)
    assert (item.status, item.attempt, item.error_code) == ("failed", 3, "WORKER_LOST")
    assert item.error_message == jobs.WORKER_LOST_MESSAGE
    assert item.finished_at is not None
    if kind == "video":
        with Session(worker_engine) as reader:
            outcomes = reader.execute(
                select(JobAttempt.attempt_id, JobAttempt.outcome, JobAttempt.finished_at)
            ).all()
        assert {row.attempt_id: row.outcome for row in outcomes} == {
            uuid.UUID(a): "expired" for a in attempts
        }
        assert all(row.finished_at is not None for row in outcomes)
    # Um item failed não volta mais: a fila fica vazia e a varredura não mexe nele.
    empty = client.post(
        "/internal/v1/claim", json={"worker_id": "w", "kinds": [kind]}, headers=WORKER
    )
    assert empty.status_code == 204
    assert sweep(worker_engine) == jobs.SweepResult(requeued=0, lost=0)


def test_varredura_nao_mexe_em_lease_vigente_nem_em_item_terminado(
    client: TestClient, make_job, worker_engine: Engine
):
    running = make_job()
    finished = make_job()
    queued = make_job()
    claimed = {claim(client, "video")["id"]: None for _ in range(2)}
    assert set(claimed) == {str(running), str(finished)}
    with worker_engine.begin() as connection:
        connection.execute(
            update(VideoJob)
            .where(VideoJob.id == finished)
            .values(status="failed", lease_until=func.now() - text("interval '1 hour'"))
        )
    before = {job_id: snapshot(worker_engine, job_id) for job_id in (running, finished, queued)}

    assert sweep(worker_engine) == jobs.SweepResult(requeued=0, lost=0)

    assert {job_id: snapshot(worker_engine, job_id) for job_id in before} == before


def test_varredura_pula_linha_travada_sem_esperar(
    client: TestClient, make_job, worker_engine: Engine
):
    locked = make_job()
    other = make_job()
    for _ in range(2):
        claim(client, "video")
    expire_lease(worker_engine, VideoJob, locked)
    expire_lease(worker_engine, VideoJob, other)

    with Session(worker_engine) as holder:
        holder.execute(select(VideoJob).where(VideoJob.id == locked).with_for_update()).scalar_one()
        with Session(worker_engine) as sweeper:
            sweeper.execute(text("SET LOCAL lock_timeout = '2s'"))
            assert jobs.sweep_expired_leases(sweeper) == jobs.SweepResult(requeued=1, lost=0)
        holder.rollback()

    assert fresh(worker_engine, VideoJob, locked).status == "processing"
    assert fresh(worker_engine, VideoJob, other).status == "queued"
    assert sweep(worker_engine) == jobs.SweepResult(requeued=1, lost=0)
    assert fresh(worker_engine, VideoJob, locked).status == "queued"


def wait_for(condition, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def test_varredor_do_lifespan_devolve_o_job_a_fila_e_o_novo_claim_vence(
    settings: Settings, make_job, worker_engine: Engine
):
    job_id = make_job()
    app = create_app(replace(settings, sweep_interval_seconds=1))
    with TestClient(app) as client:
        a = claim(client, "video", "worker-a")
        expire_lease(worker_engine, VideoJob, job_id)

        assert wait_for(lambda: fresh(worker_engine, VideoJob, job_id).status == "queued")
        requeued = fresh(worker_engine, VideoJob, job_id)
        assert (requeued.attempt, requeued.lease_generation) == (1, 1)

        b = claim(client, "video", "worker-b")
        a_file = upload(client, job_id, a["attempt_id"], 1)
        b_file = upload(client, job_id, b["attempt_id"], 2).json()["id"]
        assert_error(a_file, 409, "STALE_ATTEMPT")
        assert_error(complete(client, job_id, a["attempt_id"], 1, b_file), 409, "STALE_ATTEMPT")
        assert complete(client, job_id, b["attempt_id"], 2, b_file).status_code == 200

    job = fresh(worker_engine, VideoJob, job_id)
    assert (job.status, job.result_file_id, job.lease_generation) == ("ready", uuid.UUID(b_file), 2)


def test_falha_na_varredura_e_registrada_e_o_varredor_continua(
    settings: Settings,
    make_job,
    worker_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    job_id = make_job()
    real = jobs.sweep_expired_leases
    calls = {"n": 0}
    lock = threading.Lock()

    def flaky(session):
        with lock:
            calls["n"] += 1
            first = calls["n"] == 1
        if first:
            raise RuntimeError("banco fora do ar na varredura")
        return real(session)

    monkeypatch.setattr(jobs, "sweep_expired_leases", flaky)
    caplog.set_level(logging.INFO, logger="avatar_api.main")
    app = create_app(replace(settings, sweep_interval_seconds=1))
    with TestClient(app) as client:
        claim(client, "video")
        expire_lease(worker_engine, VideoJob, job_id)

        assert wait_for(lambda: fresh(worker_engine, VideoJob, job_id).status == "queued")
        assert client.get("/healthz").status_code == 200

    assert calls["n"] >= 2
    messages = [record.getMessage() for record in caplog.records]
    assert "falha na varredura de leases vencidos" in messages
    assert any("1 item(ns) de volta à fila" in message for message in messages)
