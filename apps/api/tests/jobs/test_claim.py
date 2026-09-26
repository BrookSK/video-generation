import hmac
import threading
import uuid
from collections import Counter
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from avatar_api import jobs
from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.db import create_db_engine
from avatar_api.devseed import DevCatalog
from avatar_api.main import create_app
from avatar_api.models import AssetPrepareTask, Avatar, JobAttempt, VideoJob

WORKER_TOKEN = "token-do-worker-de-teste"
WORKER = {"Authorization": f"Bearer {WORKER_TOKEN}"}
BOTH_KINDS = ["video", "asset_prepare"]
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def api_key_id(session: Session) -> uuid.UUID:
    user = create_user(session, "admin", "senha-de-teste-bem-longa")
    return issue_api_key(session, user.id, "ERP").row.id


@pytest.fixture
def make_job(session: Session, seeded_catalog: DevCatalog, api_key_id: uuid.UUID):
    """Grava um job queued pelo caminho real de criação; created_at fixa a ordem FIFO."""
    counter = iter(range(10_000))

    def make(created_at: datetime | None = None) -> uuid.UUID:
        payload = jobs.NewVideoJob(
            script_text=f"Vídeo de teste {next(counter)}.",
            avatar_id=seeded_catalog.avatar_id,
            scene_id=seeded_catalog.scene_id,
        )
        job = jobs.create_video_job(
            session, jobs.JobRequester(origin="api", api_key_id=api_key_id), payload
        )
        if created_at is not None:
            session.execute(
                update(VideoJob).where(VideoJob.id == job.id).values(created_at=created_at)
            )
            session.commit()
        return job.id

    return make


@pytest.fixture
def make_task(session: Session, seeded_catalog: DevCatalog):
    def make(created_at: datetime | None = None) -> uuid.UUID:
        task = AssetPrepareTask(avatar_id=seeded_catalog.avatar_id)
        if created_at is not None:
            task.created_at = created_at
        session.add(task)
        session.commit()
        return task.id

    return make


@pytest.fixture
def worker_engine(database_url: str) -> Iterator[Engine]:
    """Engine própria dos workers simulados: cada sessão abre a sua conexão."""
    engine = create_db_engine(database_url)
    yield engine
    engine.dispose()


def claim(client: TestClient, kinds: list[str], worker_id: str = "worker-a"):
    return client.post(
        "/internal/v1/claim", json={"worker_id": worker_id, "kinds": kinds}, headers=WORKER
    )


def fresh(engine: Engine, model, item_id: uuid.UUID):
    with Session(engine) as reader:
        return reader.get(model, item_id)


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- autenticação do worker -----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer token-errado"},
        {"Authorization": f"Bearer {WORKER_TOKEN}x"},
        {"Authorization": f"Basic {WORKER_TOKEN}"},
        {"Authorization": WORKER_TOKEN},
    ],
)
def test_claim_sem_token_valido_devolve_401(
    client: TestClient, make_job, worker_engine: Engine, headers: dict[str, str]
):
    job_id = make_job()

    response = client.post(
        "/internal/v1/claim", json={"worker_id": "w", "kinds": BOTH_KINDS}, headers=headers
    )
    heartbeat = client.post(
        f"/internal/v1/jobs/{job_id}/heartbeat",
        json={"attempt_id": str(uuid.uuid4()), "lease_generation": 1},
        headers=headers,
    )

    assert_error(response, 401, "UNAUTHORIZED")
    assert_error(heartbeat, 401, "UNAUTHORIZED")
    assert fresh(worker_engine, VideoJob, job_id).status == "queued"


def test_token_do_worker_e_conferido_com_compare_digest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make_job
):
    make_job()
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr("avatar_api.internal_v1.hmac.compare_digest", spy)

    assert_error(
        client.post(
            "/internal/v1/claim",
            json={"worker_id": "w", "kinds": BOTH_KINDS},
            headers={"Authorization": "Bearer outro"},
        ),
        401,
        "UNAUTHORIZED",
    )
    assert claim(client, BOTH_KINDS).status_code == 200
    assert calls == [(b"outro", WORKER_TOKEN.encode()), (WORKER_TOKEN.encode(),) * 2]


def test_token_vazio_desativa_a_api_interna_com_503(settings: Settings, make_job):
    make_job()
    app = create_app(replace(settings, worker_token=""))
    with TestClient(app) as client:
        for headers in ({}, {"Authorization": "Bearer "}, WORKER):
            response = client.post(
                "/internal/v1/claim", json={"worker_id": "w", "kinds": BOTH_KINDS}, headers=headers
            )
            assert_error(response, 503, "SERVICE_UNAVAILABLE")


# --- claim ----------------------------------------------------------------------------


def test_claim_de_video_grava_tentativa_e_lease_pelo_relogio_do_banco(
    client: TestClient, make_job, worker_engine: Engine, seeded_catalog: DevCatalog
):
    job_id = make_job()

    response = claim(client, ["video"], worker_id="gpu-01")

    assert response.status_code == 200, response.text
    data = response.json()
    job = fresh(worker_engine, VideoJob, job_id)
    attempt = fresh(worker_engine, JobAttempt, uuid.UUID(data["attempt_id"]))
    assert data == {
        "kind": "video",
        "id": str(job_id),
        "attempt_id": str(job.current_attempt_id),
        "lease_generation": 1,
        "lease_until": data["lease_until"],
        "heartbeat_interval_seconds": 20,
        "payload": {
            "script_text": job.script_text,
            "avatar_id": str(seeded_catalog.avatar_id),
            "avatar_file_id": str(job.avatar_file_id),
            "scene_id": str(seeded_catalog.scene_id),
            "scene_file_id": None,
            "voice": "feminina",
            "aspect_ratio": "9:16",
            "recipe_id": str(seeded_catalog.recipe_id),
        },
    }
    assert (job.status, job.attempt, job.lease_generation, job.worker_id) == (
        "processing",
        1,
        1,
        "gpu-01",
    )
    assert job.started_at is not None
    assert datetime.fromisoformat(data["lease_until"]) == job.lease_until
    # claimed_at e started_at vêm do mesmo now() da transação do claim: lease = now() + 120 s.
    assert job.lease_until - attempt.claimed_at == timedelta(seconds=120)
    assert job.started_at == attempt.claimed_at
    assert (attempt.job_id, attempt.attempt_number, attempt.lease_generation) == (job_id, 1, 1)
    assert (attempt.worker_id, attempt.outcome, attempt.last_heartbeat_at) == (
        "gpu-01",
        "running",
        None,
    )


def test_lease_segue_lease_seconds_da_configuracao(settings: Settings, make_job, worker_engine):
    job_id = make_job()
    with TestClient(create_app(replace(settings, lease_seconds=15))) as client:
        data = claim(client, ["video"]).json()

    job = fresh(worker_engine, VideoJob, job_id)
    attempt = fresh(worker_engine, JobAttempt, uuid.UUID(data["attempt_id"]))
    assert job.lease_until - attempt.claimed_at == timedelta(seconds=15)


def test_claim_de_asset_prepare_devolve_avatar_e_arquivo_de_origem(
    client: TestClient, make_task, worker_engine: Engine, seeded_catalog: DevCatalog
):
    task_id = make_task()

    data = claim(client, ["asset_prepare"], worker_id="cpu-01").json()

    task = fresh(worker_engine, AssetPrepareTask, task_id)
    avatar = fresh(worker_engine, Avatar, seeded_catalog.avatar_id)
    assert data["kind"] == "asset_prepare"
    assert data["id"] == str(task_id)
    assert data["attempt_id"] == str(task.current_attempt_id)
    assert data["lease_generation"] == 1
    assert data["payload"] == {
        "avatar_id": str(avatar.id),
        "source_file_id": str(avatar.source_file_id),
    }
    assert (task.status, task.attempt, task.worker_id) == ("processing", 1, "cpu-01")
    assert datetime.fromisoformat(data["lease_until"]) == task.lease_until
    assert task.lease_until - task.started_at == timedelta(seconds=120)
    with Session(worker_engine) as reader:
        assert reader.scalar(select(func.count()).select_from(JobAttempt)) == 0


def test_fila_vazia_devolve_204(client: TestClient, make_job):
    assert claim(client, BOTH_KINDS).status_code == 204
    job_id = make_job()
    assert claim(client, ["video"]).json()["id"] == str(job_id)

    response = claim(client, BOTH_KINDS)

    assert response.status_code == 204
    assert response.content == b""


def test_claim_segue_fifo_por_created_at(client: TestClient, make_job):
    later = make_job(BASE_TIME + timedelta(minutes=2))
    first = make_job(BASE_TIME)
    middle = make_job(BASE_TIME + timedelta(minutes=1))

    ids = [claim(client, ["video"]).json()["id"] for _ in range(3)]

    assert ids == [str(first), str(middle), str(later)]


def test_filtro_por_tipo_e_ordem_dos_tipos(client: TestClient, make_job, make_task):
    old_job = make_job(BASE_TIME)
    new_task = make_task(BASE_TIME + timedelta(hours=1))
    other_task = make_task(BASE_TIME + timedelta(hours=2))

    # Só asset_prepare: nunca recebe vídeo, mesmo com o job mais antigo na fila.
    only_assets = [claim(client, ["asset_prepare"], "cpu") for _ in range(3)]
    assert [r.json()["kind"] for r in only_assets[:2]] == ["asset_prepare", "asset_prepare"]
    assert [r.json()["id"] for r in only_assets[:2]] == [str(new_task), str(other_task)]
    assert only_assets[2].status_code == 204

    # Só vídeo: recebe o job e depois fila vazia.
    assert claim(client, ["video"], "gpu").json()["id"] == str(old_job)
    assert claim(client, ["video"], "gpu").status_code == 204


def test_tipos_sao_percorridos_na_ordem_enviada(client: TestClient, make_job, make_task):
    job_id = make_job(BASE_TIME)
    task_id = make_task(BASE_TIME + timedelta(hours=1))

    # asset_prepare primeiro, embora o job de vídeo seja mais antigo.
    first = claim(client, ["asset_prepare", "video"]).json()
    second = claim(client, ["asset_prepare", "video"]).json()

    assert (first["kind"], first["id"]) == ("asset_prepare", str(task_id))
    assert (second["kind"], second["id"]) == ("video", str(job_id))


@pytest.mark.parametrize(
    "body",
    [
        {"worker_id": "w", "kinds": []},
        {"worker_id": "w", "kinds": ["render"]},
        {"worker_id": "", "kinds": ["video"]},
        {"kinds": ["video"]},
        {"worker_id": "w"},
    ],
)
def test_claim_com_corpo_invalido_devolve_422(client: TestClient, make_job, body: dict):
    make_job()
    response = client.post("/internal/v1/claim", json=body, headers=WORKER)
    assert_error(response, 422, "VALIDATION_ERROR")


def test_item_em_processing_nao_e_reivindicado_de_novo(client: TestClient, make_job):
    make_job()
    assert claim(client, ["video"], "a").status_code == 200
    assert claim(client, ["video"], "b").status_code == 204


# --- SKIP LOCKED com sessões próprias -------------------------------------------------


def test_transacao_aberta_faz_o_outro_worker_pular_a_linha_travada(make_job, worker_engine: Engine):
    oldest = make_job(BASE_TIME)
    next_job = make_job(BASE_TIME + timedelta(minutes=1))

    with Session(worker_engine) as worker_a, Session(worker_engine) as worker_b:
        claimed_a = jobs.claim_next(worker_a, "a", ["video"], lease_seconds=120)
        # A ainda não fez commit: a linha continua queued para os outros e travada por A.
        worker_b.execute(text("SET LOCAL lock_timeout = '2s'"))
        claimed_b = jobs.claim_next(worker_b, "b", ["video"], lease_seconds=120)
        assert (claimed_a.id, claimed_b.id) == (oldest, next_job)
        worker_b.commit()

        # Com A e B travando os dois únicos jobs, um terceiro worker não acha nada nem espera.
        with Session(worker_engine) as worker_c:
            worker_c.execute(text("SET LOCAL lock_timeout = '2s'"))
            assert jobs.claim_next(worker_c, "c", ["video"], lease_seconds=120) is None
        worker_a.commit()

    assert fresh(worker_engine, VideoJob, oldest).worker_id == "a"
    assert fresh(worker_engine, VideoJob, next_job).worker_id == "b"


def test_claim_pela_api_nao_espera_linha_travada_por_outra_transacao(
    client: TestClient, make_job, worker_engine: Engine
):
    oldest = make_job(BASE_TIME)
    next_job = make_job(BASE_TIME + timedelta(minutes=1))
    result: dict = {}

    with Session(worker_engine) as locker:
        locker.execute(select(VideoJob).where(VideoJob.id == oldest).with_for_update()).scalar_one()
        thread = threading.Thread(target=lambda: result.update(r=claim(client, ["video"], "b")))
        thread.start()
        thread.join(timeout=10)
        # Sem SKIP LOCKED o claim ficaria preso aqui até o locker terminar.
        blocked = thread.is_alive()
        locker.rollback()
    thread.join()

    assert not blocked
    assert result["r"].json()["id"] == str(next_job)
    assert fresh(worker_engine, VideoJob, oldest).status == "queued"


def test_dois_workers_com_transacoes_simultaneas_nunca_pegam_o_mesmo_item(
    make_job, make_task, worker_engine: Engine
):
    for i in range(20):
        make_job(BASE_TIME + timedelta(seconds=i))
    for i in range(5):
        make_task(BASE_TIME + timedelta(seconds=i))
    both_claimed = threading.Barrier(2, timeout=30)
    round_start = threading.Barrier(2, timeout=30)
    rounds: list[dict[str, tuple[str, uuid.UUID] | None]] = []
    lock = threading.Lock()
    errors: list[Exception] = []

    def worker(name: str) -> None:
        try:
            with Session(worker_engine) as session:
                for index in range(100):
                    round_start.wait()
                    session.execute(text("SET LOCAL lock_timeout = '5s'"))
                    claimed = jobs.claim_next(session, name, BOTH_KINDS, lease_seconds=120)
                    with lock:
                        if len(rounds) <= index:
                            rounds.append({})
                        rounds[index][name] = claimed and (claimed.kind, claimed.id)
                    # Os dois estão com a transação aberta e a linha travada ao mesmo tempo.
                    both_claimed.wait()
                    session.commit()
                    if all(value is None for value in rounds[index].values()):
                        return
        except Exception as exc:  # propagado para a thread principal
            errors.append(exc)
            round_start.abort()
            both_claimed.abort()

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    items = [item for round_ in rounds for item in round_.values() if item is not None]
    for round_ in rounds:
        taken = [item for item in round_.values() if item is not None]
        assert len(taken) == len(set(taken))
    counts = Counter(items)
    assert len(items) == 25
    assert max(counts.values()) == 1
    assert Counter(kind for kind, _ in items) == {"video": 20, "asset_prepare": 5}
    # Na primeira rodada os dois travam uma linha cada, na mesma hora.
    assert all(rounds[0].values())
    with Session(worker_engine) as reader:
        assert reader.scalar(select(func.count()).where(VideoJob.status == "queued")) == 0
        assert reader.scalar(select(func.count()).select_from(JobAttempt)) == 20
        assert set(reader.scalars(select(VideoJob.lease_generation))) == {1}


def test_dois_workers_em_threads_esvaziam_a_fila_pela_api(
    settings: Settings, make_job, make_task, worker_engine: Engine
):
    for i in range(20):
        make_job(BASE_TIME + timedelta(seconds=i))
    for i in range(5):
        make_task(BASE_TIME + timedelta(seconds=i))
    app = create_app(settings)
    start = threading.Barrier(2, timeout=30)
    claimed: dict[str, list[tuple[str, str]]] = {"a": [], "b": []}
    errors: list[Exception] = []

    def worker(name: str) -> None:
        try:
            with TestClient(app) as client:
                start.wait()
                while (response := claim(client, BOTH_KINDS, name)).status_code == 200:
                    data = response.json()
                    claimed[name].append((data["kind"], data["id"]))
                assert response.status_code == 204, response.text
        except Exception as exc:  # propagado para a thread principal
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(name,)) for name in claimed]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, errors
    items = claimed["a"] + claimed["b"]
    assert len(items) == 25
    assert len(set(items)) == 25
    assert Counter(kind for kind, _ in items) == {"video": 20, "asset_prepare": 5}
    with Session(worker_engine) as reader:
        owners = dict(reader.execute(select(VideoJob.id, VideoJob.worker_id)).all())
        owners |= dict(
            reader.execute(select(AssetPrepareTask.id, AssetPrepareTask.worker_id)).all()
        )
    for name, taken in claimed.items():
        assert all(owners[uuid.UUID(item_id)] == name for _, item_id in taken)


# --- heartbeat ------------------------------------------------------------------------


def heartbeat(client: TestClient, path: str, item_id, attempt_id, generation: int, **extra):
    return client.post(
        f"/internal/v1/{path}/{item_id}/heartbeat",
        json={"attempt_id": str(attempt_id), "lease_generation": generation, **extra},
        headers=WORKER,
    )


def set_lease_from_now(engine: Engine, model, item_id: uuid.UUID, seconds: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(model)
            .where(model.id == item_id)
            .values(lease_until=func.now() + timedelta(seconds=seconds))
        )


def test_heartbeat_de_video_renova_lease_e_grava_etapa(
    client: TestClient, make_job, worker_engine: Engine
):
    job_id = make_job()
    data = claim(client, ["video"]).json()
    set_lease_from_now(worker_engine, VideoJob, job_id, 5)
    before = fresh(worker_engine, VideoJob, job_id)

    response = heartbeat(client, "jobs", job_id, data["attempt_id"], 1, stage="render")

    assert response.status_code == 200, response.text
    job = fresh(worker_engine, VideoJob, job_id)
    attempt = fresh(worker_engine, JobAttempt, uuid.UUID(data["attempt_id"]))
    assert datetime.fromisoformat(response.json()["lease_until"]) == job.lease_until
    assert job.lease_until > before.lease_until
    # Novo lease = now() da transação do heartbeat + 120 s, o mesmo now() de last_heartbeat_at.
    assert job.lease_until - attempt.last_heartbeat_at == timedelta(seconds=120)
    assert (job.stage, job.status, job.lease_generation, job.attempt) == (
        "render",
        "processing",
        1,
        1,
    )


def test_heartbeat_sem_etapa_mantem_a_etapa(client: TestClient, make_job, worker_engine):
    job_id = make_job()
    data = claim(client, ["video"]).json()
    assert heartbeat(client, "jobs", job_id, data["attempt_id"], 1, stage="tts").status_code == 200

    assert heartbeat(client, "jobs", job_id, data["attempt_id"], 1).status_code == 200

    assert fresh(worker_engine, VideoJob, job_id).stage == "tts"


def test_heartbeat_com_etapa_invalida_devolve_422(client: TestClient, make_job):
    job_id = make_job()
    data = claim(client, ["video"]).json()

    response = heartbeat(client, "jobs", job_id, data["attempt_id"], 1, stage="waiting")

    assert_error(response, 422, "VALIDATION_ERROR")


def test_heartbeat_de_asset_task_renova_lease(client: TestClient, make_task, worker_engine):
    task_id = make_task()
    data = claim(client, ["asset_prepare"]).json()
    set_lease_from_now(worker_engine, AssetPrepareTask, task_id, 5)
    before = fresh(worker_engine, AssetPrepareTask, task_id)

    response = heartbeat(client, "asset-tasks", task_id, data["attempt_id"], 1)

    assert response.status_code == 200, response.text
    task = fresh(worker_engine, AssetPrepareTask, task_id)
    assert task.lease_until > before.lease_until
    assert datetime.fromisoformat(response.json()["lease_until"]) == task.lease_until


def _requeue(engine: Engine, model, item_id: uuid.UUID) -> None:
    """Simula o varredor: lease vencido devolve o item à fila sem zerar os contadores."""
    with engine.begin() as connection:
        connection.execute(
            update(model).where(model.id == item_id).values(status="queued", lease_until=None)
        )


@pytest.mark.parametrize(
    ("path", "kind", "model"),
    [
        ("jobs", "video", VideoJob),
        ("asset-tasks", "asset_prepare", AssetPrepareTask),
    ],
)
def test_heartbeat_da_tentativa_obsoleta_devolve_409_e_nao_altera_o_item(
    client: TestClient, make_job, make_task, worker_engine: Engine, path, kind, model
):
    item_id = make_job() if kind == "video" else make_task()
    first = claim(client, [kind], "a").json()
    _requeue(worker_engine, model, item_id)
    second = claim(client, [kind], "b").json()
    assert second["lease_generation"] == 2
    current = fresh(worker_engine, model, item_id)

    stale_generation = heartbeat(client, path, item_id, second["attempt_id"], 1)
    stale_attempt = heartbeat(client, path, item_id, first["attempt_id"], 2)
    old_pair = heartbeat(client, path, item_id, first["attempt_id"], 1)
    unknown = heartbeat(client, path, item_id, uuid.uuid4(), 2)

    for response in (stale_generation, stale_attempt, old_pair, unknown):
        assert_error(response, 409, "STALE_ATTEMPT")
    after = fresh(worker_engine, model, item_id)
    assert (after.lease_until, after.lease_generation, after.attempt, after.worker_id) == (
        current.lease_until,
        2,
        2,
        "b",
    )
    assert after.current_attempt_id == uuid.UUID(second["attempt_id"])
    assert heartbeat(client, path, item_id, second["attempt_id"], 2).status_code == 200


def test_heartbeat_com_lease_vencido_devolve_409(client: TestClient, make_job, worker_engine):
    job_id = make_job()
    data = claim(client, ["video"]).json()
    set_lease_from_now(worker_engine, VideoJob, job_id, -1)
    expired = fresh(worker_engine, VideoJob, job_id)

    response = heartbeat(client, "jobs", job_id, data["attempt_id"], 1, stage="render")

    assert_error(response, 409, "STALE_ATTEMPT")
    after = fresh(worker_engine, VideoJob, job_id)
    assert (after.lease_until, after.stage) == (expired.lease_until, "waiting")
    assert fresh(worker_engine, JobAttempt, uuid.UUID(data["attempt_id"])).last_heartbeat_at is None


def test_heartbeat_de_item_fora_de_processing_devolve_409(
    client: TestClient, make_job, worker_engine
):
    job_id = make_job()
    data = claim(client, ["video"]).json()
    with worker_engine.begin() as connection:
        connection.execute(update(VideoJob).where(VideoJob.id == job_id).values(status="failed"))

    assert_error(heartbeat(client, "jobs", job_id, data["attempt_id"], 1), 409, "STALE_ATTEMPT")


def test_heartbeat_de_item_inexistente_ou_de_outro_tipo_devolve_404(
    client: TestClient, make_job, make_task
):
    job_id = make_job()
    task_id = make_task()
    job = claim(client, ["video"]).json()
    task = claim(client, ["asset_prepare"]).json()

    assert_error(heartbeat(client, "jobs", uuid.uuid4(), job["attempt_id"], 1), 404, "NOT_FOUND")
    assert_error(heartbeat(client, "asset-tasks", job_id, job["attempt_id"], 1), 404, "NOT_FOUND")
    assert_error(heartbeat(client, "jobs", task_id, task["attempt_id"], 1), 404, "NOT_FOUND")
