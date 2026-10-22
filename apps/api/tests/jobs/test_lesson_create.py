import uuid
from collections.abc import Iterator

import pytest
from conftest import SCENE_TEXTS, lesson_body, logo_png, put_identity
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from avatar_api import lessons
from avatar_api.db import create_db_engine
from avatar_api.devseed import RECIPE_MAX_SCRIPT_CHARS, DevCatalog
from avatar_api.models import (
    Avatar,
    BrandIdentity,
    Lesson,
    LessonScene,
    Scene,
    User,
    VideoJob,
)


@pytest.fixture
def other_engine(database_url: str) -> Iterator[Engine]:
    """Engine própria, fora do pool da API, para ler o que já está commitado."""
    engine = create_db_engine(database_url)
    yield engine
    engine.dispose()


def post_lesson(client: TestClient, body: dict, key: str | None = None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/panel/lessons", json=body, headers=headers)


def counts(session: Session) -> tuple[int, int, int]:
    session.expire_all()
    return tuple(
        session.scalar(select(func.count()).select_from(model))
        for model in (Lesson, LessonScene, VideoJob)
    )


def assert_error(response, status: int, code: str, field: str | None = None) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error.get("field") == field
    return error


# --- criação ----------------------------------------------------------------------------


def test_202_so_depois_do_commit_com_cenas_jobs_e_identidade(
    lesson_panel, brand, seeded_catalog: DevCatalog, session, other_engine
):
    response = post_lesson(lesson_panel, lesson_body(seeded_catalog))

    assert response.status_code == 202, response.text
    data = response.json()
    assert data == {
        "id": data["id"],
        "status": "queued",
        "status_url": f"/panel/lessons/{data['id']}",
        "download_url": None,
    }
    lesson_id = uuid.UUID(data["id"])
    # Lido por outra conexão, fora do pool da API: aula, cenas e jobs já estão commitados.
    with Session(other_engine) as fresh:
        lesson = fresh.get(Lesson, lesson_id)
        identity = fresh.get(BrandIdentity, 1)
        user_id = fresh.scalar(select(User.id).where(User.username == "painel-aulas"))
        assert (lesson.status, lesson.aspect_ratio, lesson.requested_by_user_id) == (
            "queued",
            "16:9",
            user_id,
        )
        assert (lesson.logo_file_id, lesson.background_color, lesson.accent_color) == (
            identity.logo_file_id,
            "#0B2545",
            "#F2A541",
        )
        scenes = fresh.scalars(
            select(LessonScene).where(LessonScene.lesson_id == lesson_id).order_by("position")
        ).all()
        assert [(s.position, s.script_text, s.shot) for s in scenes] == [
            (1, SCENE_TEXTS[0], "medio"),
            (2, SCENE_TEXTS[1], "close"),
            (3, SCENE_TEXTS[2], "medio"),
        ]
        avatar = fresh.get(Avatar, seeded_catalog.avatar_id)
        for scene in scenes:
            job = fresh.get(VideoJob, scene.video_job_id)
            assert (job.lesson_id, job.lesson_position, job.shot) == (
                lesson_id,
                scene.position,
                scene.shot,
            )
            assert job.script_text == scene.script_text
            assert (job.origin, job.requested_by_user_id, job.api_key_id) == (
                "panel",
                user_id,
                None,
            )
            assert (job.avatar_file_id, job.voice, job.aspect_ratio) == (
                avatar.prepared_file_id,
                avatar.voice,
                "16:9",
            )
            assert (job.status, job.recipe_id) == ("queued", seeded_catalog.recipe_id)


def test_formato_padrao_e_9x16_e_plano_padrao_e_medio(
    lesson_panel, brand, seeded_catalog, session
):
    body = lesson_body(seeded_catalog)
    del body["aspect_ratio"]
    body["scenes"] = [{"script_text": text} for text in SCENE_TEXTS[:2]]

    response = post_lesson(lesson_panel, body)

    assert response.status_code == 202, response.text
    lesson = session.get(Lesson, uuid.UUID(response.json()["id"]))
    assert lesson.aspect_ratio == "9:16"
    shots = session.scalars(select(VideoJob.shot).where(VideoJob.lesson_id == lesson.id)).all()
    assert shots == ["medio", "medio"]


def test_texto_literal_preservado_por_cena(lesson_panel, brand, seeded_catalog, session):
    texts = ["  Espaços  e\nquebra.  ", "Acentuação: ação, pôr, à."]
    body = lesson_body(seeded_catalog, scenes=[{"script_text": t} for t in texts])

    response = post_lesson(lesson_panel, body)

    assert response.status_code == 202, response.text
    jobs = session.scalars(
        select(VideoJob)
        .where(VideoJob.lesson_id == uuid.UUID(response.json()["id"]))
        .order_by(VideoJob.lesson_position)
    ).all()
    assert [job.script_text for job in jobs] == texts


# --- recusas sem gravar nada ------------------------------------------------------------


@pytest.mark.parametrize("total", [0, 1, 13])
def test_numero_de_cenas_fora_do_limite_recusado(
    lesson_panel, brand, seeded_catalog, session, total
):
    scenes = [{"script_text": f"Cena {n}."} for n in range(total)]

    response = post_lesson(lesson_panel, lesson_body(seeded_catalog, scenes=scenes))

    error = assert_error(response, 422, "LESSON_SCENES_OUT_OF_RANGE", "scenes")
    assert error["message"] == "A aula precisa ter de 2 a 12 cenas."
    assert counts(session) == (0, 0, 0)


def test_doze_cenas_aceitas(lesson_panel, brand, seeded_catalog, session):
    scenes = [{"script_text": f"Cena {n}."} for n in range(12)]

    response = post_lesson(lesson_panel, lesson_body(seeded_catalog, scenes=scenes))

    assert response.status_code == 202, response.text
    assert counts(session) == (1, 12, 12)


def test_cena_acima_do_limite_de_fala_recusada_com_a_posicao(
    lesson_panel, brand, seeded_catalog, session
):
    scenes = [
        {"script_text": "Cena curta."},
        {"script_text": "x" * (RECIPE_MAX_SCRIPT_CHARS + 1)},
    ]

    response = post_lesson(lesson_panel, lesson_body(seeded_catalog, scenes=scenes))

    error = assert_error(response, 422, "SCRIPT_TOO_LONG", "scenes.1.script_text")
    assert error["message"] == (
        f"Cena 2: o texto passa do limite de {RECIPE_MAX_SCRIPT_CHARS} caracteres."
    )
    assert counts(session) == (0, 0, 0)


def test_cena_vazia_recusada_com_a_posicao(lesson_panel, brand, seeded_catalog, session):
    scenes = [{"script_text": "Cena."}, {"script_text": "Cena."}, {"script_text": "   "}]

    response = post_lesson(lesson_panel, lesson_body(seeded_catalog, scenes=scenes))

    error = assert_error(response, 422, "SCRIPT_EMPTY", "scenes.2.script_text")
    assert error["message"] == "Cena 3: o texto está vazio."
    assert counts(session) == (0, 0, 0)


def test_plano_invalido_recusado(lesson_panel, brand, seeded_catalog, session):
    response = post_lesson(lesson_panel, lesson_body(seeded_catalog, shots=("medio", "aberto")))

    assert_error(response, 422, "VALIDATION_ERROR", "scenes.1.shot")
    assert counts(session) == (0, 0, 0)


def test_avatar_arquivado_recusado(lesson_panel, brand, seeded_catalog, session):
    session.execute(
        update(Avatar).where(Avatar.id == seeded_catalog.avatar_id).values(archived_at=func.now())
    )
    session.commit()

    response = post_lesson(lesson_panel, lesson_body(seeded_catalog))

    assert_error(response, 422, "AVATAR_UNAVAILABLE", "avatar_id")
    assert counts(session) == (0, 0, 0)


def test_cenario_arquivado_recusado(lesson_panel, brand, seeded_catalog, session):
    session.execute(
        update(Scene).where(Scene.id == seeded_catalog.scene_id).values(archived_at=func.now())
    )
    session.commit()

    response = post_lesson(lesson_panel, lesson_body(seeded_catalog))

    assert_error(response, 422, "SCENE_UNAVAILABLE", "scene_id")
    assert counts(session) == (0, 0, 0)


def test_sem_identidade_recusado(lesson_panel, seeded_catalog, session):
    response = post_lesson(lesson_panel, lesson_body(seeded_catalog))

    error = assert_error(response, 422, "BRAND_IDENTITY_MISSING")
    assert "Identidade" in error["message"]
    assert counts(session) == (0, 0, 0)


def test_criacao_exige_sessao_e_csrf(lesson_panel, client, brand, seeded_catalog, session):
    assert client.post("/panel/lessons", json=lesson_body(seeded_catalog)).status_code == 401
    lesson_panel.headers.pop("X-CSRF-Token")
    assert post_lesson(lesson_panel, lesson_body(seeded_catalog)).status_code == 403
    assert counts(session) == (0, 0, 0)


# --- idempotência -----------------------------------------------------------------------


def test_mesma_chave_e_mesmo_corpo_devolve_a_mesma_aula(
    lesson_panel, brand, seeded_catalog, session
):
    first = post_lesson(lesson_panel, lesson_body(seeded_catalog), key="aula-1")
    again = post_lesson(lesson_panel, lesson_body(seeded_catalog), key="aula-1")

    assert first.status_code == again.status_code == 202
    assert first.json()["id"] == again.json()["id"]
    assert counts(session) == (1, 3, 3)


def test_mesma_chave_com_corpo_diferente_responde_409(
    lesson_panel, brand, seeded_catalog, session
):
    assert post_lesson(lesson_panel, lesson_body(seeded_catalog), key="aula-1").status_code == 202

    for changed in (
        lesson_body(seeded_catalog, shots=("close", "close", "medio")),
        lesson_body(seeded_catalog, aspect_ratio="9:16"),
    ):
        response = post_lesson(lesson_panel, changed, key="aula-1")
        assert_error(response, 409, "IDEMPOTENCY_CONFLICT")
    assert counts(session) == (1, 3, 3)


def test_identidade_trocada_depois_nao_muda_a_aula(lesson_panel, brand, seeded_catalog, session):
    created = post_lesson(lesson_panel, lesson_body(seeded_catalog)).json()
    old_logo = session.get(BrandIdentity, 1).logo_file_id

    put_identity(lesson_panel, logo_png((10, 10, 10)), "#000000", "#FFFFFF")
    later = post_lesson(lesson_panel, lesson_body(seeded_catalog)).json()

    session.expire_all()
    before = session.get(Lesson, uuid.UUID(created["id"]))
    after = session.get(Lesson, uuid.UUID(later["id"]))
    assert (before.logo_file_id, before.background_color) == (old_logo, "#0B2545")
    assert after.logo_file_id != old_logo
    assert (after.background_color, after.accent_color) == ("#000000", "#FFFFFF")


# --- leitura e download -----------------------------------------------------------------


def test_aula_mostra_estado_da_aula_e_de_cada_cena(lesson_panel, brand, seeded_catalog):
    created = post_lesson(lesson_panel, lesson_body(seeded_catalog)).json()

    response = lesson_panel.get(created["status_url"])

    assert response.status_code == 200, response.text
    lesson = response.json()
    assert lesson["status"] == "queued"
    assert lesson["download_url"] is None
    assert lesson["error"] is None
    assert (lesson["aspect_ratio"], lesson["background_color"]) == ("16:9", "#0B2545")
    assert lesson["requested_by"] == "painel-aulas"
    assert [
        (scene["position"], scene["script_text"], scene["shot"], scene["status"])
        for scene in lesson["scenes"]
    ] == [
        (1, SCENE_TEXTS[0], "medio", "queued"),
        (2, SCENE_TEXTS[1], "close", "queued"),
        (3, SCENE_TEXTS[2], "medio", "queued"),
    ]
    listed = lesson_panel.get("/panel/lessons").json()
    assert [entry["id"] for entry in listed] == [created["id"]]


def test_download_antes_de_pronta_recusado(lesson_panel, brand, seeded_catalog):
    created = post_lesson(lesson_panel, lesson_body(seeded_catalog)).json()

    response = lesson_panel.get(f"{created['status_url']}/download")

    assert_error(response, 409, "LESSON_NOT_READY")


def test_aula_inexistente_e_leitura_sem_sessao(lesson_panel, client, brand, seeded_catalog):
    created = post_lesson(lesson_panel, lesson_body(seeded_catalog)).json()

    assert_error(lesson_panel.get(f"/panel/lessons/{uuid.uuid4()}"), 404, "NOT_FOUND")
    assert_error(lesson_panel.get(f"/panel/lessons/{uuid.uuid4()}/download"), 404, "NOT_FOUND")
    for path in ("/panel/lessons", created["status_url"], f"{created['status_url']}/download"):
        assert client.get(path).status_code == 401


def test_corrida_de_insercao_com_a_mesma_chave_rele_a_aula_vencedora(
    lesson_panel, brand, seeded_catalog, session, monkeypatch
):
    winner = post_lesson(lesson_panel, lesson_body(seeded_catalog), key="corrida")
    assert winner.status_code == 202

    # Simula a corrida: a primeira leitura não vê a aula vencedora e o INSERT colide no índice.
    real_find = lessons._find_by_idempotency_key
    calls = []

    def find_after_race(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_find(*args)

    monkeypatch.setattr(lessons, "_find_by_idempotency_key", find_after_race)
    same = post_lesson(lesson_panel, lesson_body(seeded_catalog), key="corrida")

    assert same.status_code == 202, same.text
    assert same.json()["id"] == winner.json()["id"]
    assert counts(session) == (1, 3, 3)
