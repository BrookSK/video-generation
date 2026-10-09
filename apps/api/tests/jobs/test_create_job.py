import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from avatar_api import jobs
from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.db import create_db_engine
from avatar_api.devseed import RECIPE_MAX_SCRIPT_CHARS, DevCatalog
from avatar_api.main import create_app
from avatar_api.models import ApiKey, Avatar, RenderRecipe, Scene, VideoJob

SCRIPT = "Olá, este é o vídeo de teste."


@pytest.fixture
def api_key(session: Session) -> tuple[str, ApiKey]:
    user = create_user(session, "admin", "senha-de-teste-bem-longa")
    issued = issue_api_key(session, user.id, "ERP")
    return issued.key, issued.row


@pytest.fixture
def auth(api_key: tuple[str, ApiKey]) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key[0]}"}


def body(catalog: DevCatalog, **overrides) -> dict:
    return {
        "script_text": SCRIPT,
        "avatar_id": str(catalog.avatar_id),
        "scene_id": str(catalog.scene_id),
        **overrides,
    }


def post_job(client: TestClient, headers: dict[str, str], json: dict):
    return client.post("/api/v1/jobs", json=json, headers=headers)


def job_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(VideoJob))


def assert_error(response, status: int, code: str, field: str | None = None) -> None:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error.get("field") == field


@pytest.fixture
def other_engine(database_url: str) -> Iterator[Engine]:
    """Engine própria, fora do pool da API, para ler o que já está commitado."""
    engine = create_db_engine(database_url)
    yield engine
    engine.dispose()


def read_job(engine: Engine, job_id: str) -> VideoJob | None:
    with Session(engine) as fresh:
        return fresh.get(VideoJob, uuid.UUID(job_id))


def add_avatar(session: Session, catalog: DevCatalog, **fields) -> Avatar:
    seeded = session.get(Avatar, catalog.avatar_id)
    avatar = Avatar(
        name=fields.pop("name", "Outro avatar"),
        voice=fields.pop("voice", "feminina"),
        source_file_id=seeded.source_file_id,
        prepared_file_id=fields.pop("prepared_file_id", seeded.prepared_file_id),
        **fields,
    )
    session.add(avatar)
    session.commit()
    return avatar


def add_scene(session: Session, **fields) -> Scene:
    fields.setdefault("background_color", "#000000")
    scene = Scene(name="Outro cenário", composition={"9:16": {}, "16:9": {}}, **fields)
    session.add(scene)
    session.commit()
    return scene


# --- criação válida -------------------------------------------------------------------


def test_202_so_depois_do_commit_com_snapshot_completo(
    client: TestClient,
    auth: dict[str, str],
    api_key: tuple[str, ApiKey],
    seeded_catalog: DevCatalog,
    session: Session,
    other_engine: Engine,
):
    response = post_job(client, auth, body(seeded_catalog))

    assert response.status_code == 202, response.text
    data = response.json()
    assert data == {
        "id": data["id"],
        "status": "queued",
        "status_url": f"/api/v1/jobs/{data['id']}",
        "download_url": None,
    }

    # Lido por outra conexão, fora do pool da API: o job já está commitado.
    job = read_job(other_engine, data["id"])
    assert job is not None
    seeded_avatar = session.get(Avatar, seeded_catalog.avatar_id)
    assert job.origin == "api"
    assert job.api_key_id == api_key[1].id
    assert job.requested_by_user_id is None
    assert job.script_text == SCRIPT
    assert job.avatar_id == seeded_catalog.avatar_id
    assert job.avatar_file_id == seeded_avatar.prepared_file_id
    assert job.avatar_file_id != seeded_avatar.source_file_id
    assert job.scene_id == seeded_catalog.scene_id
    assert job.scene_file_id is None
    assert job.voice == "feminina"
    assert job.aspect_ratio == "9:16"
    assert job.recipe_id == seeded_catalog.recipe_id
    assert (job.status, job.stage, job.attempt, job.lease_generation) == (
        "queued",
        "waiting",
        0,
        0,
    )
    assert job.lease_until is None
    assert job.current_attempt_id is None
    assert job.idempotency_key is None
    assert job.result_file_id is None


def test_16x9_aceito_e_formato_invalido_recusado(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, other_engine: Engine
):
    response = post_job(client, auth, body(seeded_catalog, aspect_ratio="16:9"))
    assert response.status_code == 202
    assert read_job(other_engine, response.json()["id"]).aspect_ratio == "16:9"

    for invalid in ("4:3", "9x16", None):
        response = post_job(client, auth, body(seeded_catalog, aspect_ratio=invalid))
        assert_error(response, 422, "VALIDATION_ERROR", "aspect_ratio")


def test_snapshot_copia_voz_do_avatar_e_arquivo_do_cenario(
    client: TestClient,
    auth: dict[str, str],
    seeded_catalog: DevCatalog,
    session: Session,
    other_engine: Engine,
):
    avatar = add_avatar(session, seeded_catalog, voice="masculina", prepare_status="ativo")
    background_id = avatar.source_file_id
    scene = add_scene(session, background_file_id=background_id, background_color=None)

    response = post_job(
        client, auth, body(seeded_catalog, avatar_id=str(avatar.id), scene_id=str(scene.id))
    )

    assert response.status_code == 202, response.text
    job = read_job(other_engine, response.json()["id"])
    assert job.voice == "masculina"
    assert job.avatar_file_id == avatar.prepared_file_id
    assert job.scene_file_id == background_id




# --- recusas --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"prepare_status": "ativo", "archived_at": func.now()},
        {"prepare_status": "preparando", "prepared_file_id": None},
        {"prepare_status": "falha", "prepared_file_id": None, "prepare_error": "sem rosto"},
    ],
    ids=["arquivado", "preparando", "falha"],
)
def test_avatar_indisponivel_recusado_com_422(
    client: TestClient,
    auth: dict[str, str],
    seeded_catalog: DevCatalog,
    session: Session,
    fields: dict,
):
    avatar = add_avatar(session, seeded_catalog, **fields)

    response = post_job(client, auth, body(seeded_catalog, avatar_id=str(avatar.id)))

    assert_error(response, 422, "AVATAR_UNAVAILABLE", "avatar_id")
    assert job_count(session) == 0


def test_avatar_inexistente_recusado_com_422(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, session: Session
):
    response = post_job(client, auth, body(seeded_catalog, avatar_id=str(uuid.uuid4())))

    assert_error(response, 422, "AVATAR_UNAVAILABLE", "avatar_id")
    assert job_count(session) == 0


def test_cenario_arquivado_ou_inexistente_recusado_com_422(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, session: Session
):
    archived = add_scene(session, archived_at=func.now())

    for scene_id in (archived.id, uuid.uuid4()):
        response = post_job(client, auth, body(seeded_catalog, scene_id=str(scene_id)))
        assert_error(response, 422, "SCENE_UNAVAILABLE", "scene_id")
    assert job_count(session) == 0


def test_texto_vazio_ou_acima_do_limite_recusado(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, session: Session
):
    for empty in ("", "   \n\t "):
        response = post_job(client, auth, body(seeded_catalog, script_text=empty))
        assert_error(response, 422, "SCRIPT_EMPTY", "script_text")

    too_long = "a" * (RECIPE_MAX_SCRIPT_CHARS + 1)
    response = post_job(client, auth, body(seeded_catalog, script_text=too_long))
    assert_error(response, 422, "SCRIPT_TOO_LONG", "script_text")
    assert str(RECIPE_MAX_SCRIPT_CHARS) in response.json()["error"]["message"]
    assert job_count(session) == 0


def test_campos_ausentes_ou_mal_formados_recusados(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, session: Session
):
    response = post_job(client, auth, body(seeded_catalog, avatar_id="nao-e-uuid"))
    assert_error(response, 422, "VALIDATION_ERROR", "avatar_id")

    incomplete = body(seeded_catalog)
    del incomplete["scene_id"]
    assert_error(post_job(client, auth, incomplete), 422, "VALIDATION_ERROR", "scene_id")
    assert job_count(session) == 0


def test_texto_com_nul_recusado_com_422_sem_ir_para_o_log(
    client: TestClient,
    auth: dict[str, str],
    seeded_catalog: DevCatalog,
    session: Session,
    caplog: pytest.LogCaptureFixture,
):
    secret = "fala sigilosa do cliente"
    caplog.set_level(logging.DEBUG)

    response = post_job(client, auth, body(seeded_catalog, script_text=f"{secret}\u0000"))

    assert_error(response, 422, "VALIDATION_ERROR", "script_text")
    assert secret not in response.text
    assert job_count(session) == 0
    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in (record.exc_text or "")
    assert secret not in caplog.text


def test_engine_esconde_parametros_sql_nos_erros(other_engine: Engine):
    assert other_engine.hide_parameters is True


def test_sem_receita_vigente_responde_503(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, session: Session
):
    session.execute(update(RenderRecipe).values(is_current=False))
    session.commit()

    response = post_job(client, auth, body(seeded_catalog))

    assert_error(response, 503, "RECIPE_UNAVAILABLE")
    assert job_count(session) == 0


def test_sem_chave_ou_com_chave_revogada_responde_401(
    client: TestClient,
    auth: dict[str, str],
    api_key: tuple[str, ApiKey],
    seeded_catalog: DevCatalog,
    session: Session,
):
    assert_error(post_job(client, {}, body(seeded_catalog)), 401, "UNAUTHORIZED")

    session.execute(update(ApiKey).values(revoked_at=func.now()))
    session.commit()
    assert_error(post_job(client, auth, body(seeded_catalog)), 401, "UNAUTHORIZED")
    assert job_count(session) == 0


# --- commit que falha -----------------------------------------------------------------


@pytest.fixture
def failing_commit(engine: Engine, session: Session) -> Iterator[None]:
    """Trigger adiado: o INSERT passa, e é o COMMIT de video_jobs que falha no banco."""
    session.commit()
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION test_fail_commit() RETURNS trigger LANGUAGE plpgsql AS"
                " $$ BEGIN RAISE EXCEPTION 'commit forçado a falhar'; END $$"
            )
        )
        connection.execute(
            text(
                "CREATE CONSTRAINT TRIGGER test_fail_commit AFTER INSERT ON video_jobs"
                " DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION test_fail_commit()"
            )
        )
    yield
    # A transação de leitura do teste segura lock em video_jobs e travaria o DROP.
    session.rollback()
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER test_fail_commit ON video_jobs"))
        connection.execute(text("DROP FUNCTION test_fail_commit()"))


def test_commit_que_falha_nao_devolve_202_nem_deixa_linha(
    settings: Settings,
    auth: dict[str, str],
    seeded_catalog: DevCatalog,
    session: Session,
    failing_commit: None,
):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = post_job(client, auth, body(seeded_catalog))

    assert response.status_code != 202
    assert_error(response, 500, "INTERNAL_ERROR")
    assert "commit forçado" not in response.text
    assert job_count(session) == 0


# --- idempotência ---------------------------------------------------------------------




def test_mesma_chave_com_corpo_diferente_responde_409(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, session: Session
):
    headers = {**auth, "Idempotency-Key": "pedido-123"}
    assert post_job(client, headers, body(seeded_catalog)).status_code == 202

    for changed in (
        body(seeded_catalog, script_text="Outro texto."),
        body(seeded_catalog, aspect_ratio="16:9"),
    ):
        assert_error(post_job(client, headers, changed), 409, "IDEMPOTENCY_CONFLICT")
    assert job_count(session) == 1


def test_mesma_idempotency_key_em_chaves_de_api_diferentes_cria_dois_jobs(
    client: TestClient,
    auth: dict[str, str],
    api_key: tuple[str, ApiKey],
    seeded_catalog: DevCatalog,
    session: Session,
):
    other = issue_api_key(session, api_key[1].created_by_user_id, "CRM")
    first = post_job(client, {**auth, "Idempotency-Key": "k"}, body(seeded_catalog))
    second = post_job(
        client,
        {"Authorization": f"Bearer {other.key}", "Idempotency-Key": "k"},
        body(seeded_catalog),
    )

    assert first.status_code == second.status_code == 202
    assert first.json()["id"] != second.json()["id"]
    assert session.get(VideoJob, uuid.UUID(second.json()["id"])).api_key_id == other.row.id


def test_idempotency_key_limitada_a_128_caracteres(
    client: TestClient, auth: dict[str, str], seeded_catalog: DevCatalog, session: Session
):
    response = post_job(client, {**auth, "Idempotency-Key": "k" * 128}, body(seeded_catalog))
    assert response.status_code == 202

    for invalid in ("k" * 129, ""):
        response = post_job(client, {**auth, "Idempotency-Key": invalid}, body(seeded_catalog))
        assert_error(response, 422, "VALIDATION_ERROR", "Idempotency-Key")
    assert job_count(session) == 1


def test_corrida_de_insercao_com_a_mesma_chave_rele_o_job_vencedor(
    client: TestClient,
    auth: dict[str, str],
    seeded_catalog: DevCatalog,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = {**auth, "Idempotency-Key": "corrida"}
    winner = post_job(client, headers, body(seeded_catalog))
    assert winner.status_code == 202

    # Simula a corrida: a primeira leitura não vê o job vencedor e o INSERT colide no índice.
    real_find = jobs._find_by_idempotency_key
    calls = []

    def find_after_race(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_find(*args)

    monkeypatch.setattr(jobs, "_find_by_idempotency_key", find_after_race)
    same = post_job(client, headers, body(seeded_catalog))
    calls.clear()
    changed = post_job(client, headers, body(seeded_catalog, script_text="Outro texto."))

    assert same.status_code == 202
    assert same.json()["id"] == winner.json()["id"]
    assert_error(changed, 409, "IDEMPOTENCY_CONFLICT")
    assert job_count(session) == 1
