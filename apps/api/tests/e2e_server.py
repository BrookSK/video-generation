"""Servidor de aceitação local. Controles /__test existem só neste processo de teste.

PostgreSQL, migrações, autenticação, armazenamento e protocolo worker são reais. O supervisor
CPU real roda com WORKER_KINDS=lesson_assemble e monta as aulas com FFmpeg.
Mídia FFmpeg e catálogo sintético NÃO comprovam inferência, GPU nem qualidade humana.
Execute: uv run --directory apps/api python tests/e2e_server.py
"""

import hashlib
import io
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from conftest import migrate
from fastapi import HTTPException, Response
from PIL import Image
from sqlalchemy import update
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.db import get_engine
from avatar_api.devseed import seed_dev_catalog
from avatar_api.main import create_app
from avatar_api.models import (
    Avatar,
    Lesson,
    RenderRecipe,
    Scene,
    StoredFile,
    VideoJob,
    WorkerHeartbeat,
)
from avatar_api.storage import save_stream

USERNAME = "e2e@local.test"
PASSWORD = "isolated-e2e-password"
WORKER_TOKEN = "isolated-e2e-worker"
WORKER_DIR = Path(__file__).resolve().parents[2] / "worker"
# Dublê de TTS e render: cena de aula com 3 s e cor ligada à posição, para conferir a ordem.
# A voz da cena é um tom de 300 Hz com fala de 0 a 1 s, pausa de 1 a 2 s e fala de 2 a 3 s.
LESSON_SCENE_SECONDS = "3"
LESSON_VOICE = "volume='if(between(t,1,2),0,1)':eval=frame"
SCENE_COLORS = ["0xDC2828", "0x28C83C", "0x283CDC", "0xE0C020", "0xC020C0", "0x20C0C0"]
AVULSO_COLOR = "0xCFE0D6"


def scene_color(position: int) -> str:
    return SCENE_COLORS[(position - 1) % len(SCENE_COLORS)]


def start_lesson_supervisor() -> subprocess.Popen:
    """Supervisor CPU real, só com montagem de aula; sem GPU, Verda ou servidor do cliente."""
    env = {
        **os.environ,
        "API_URL": "http://127.0.0.1:8000",
        "WORKER_TOKEN": WORKER_TOKEN,
        "WORKER_KINDS": "lesson_assemble",
        "WORKER_ID": "e2e-cpu",
        "POLL_SECONDS": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }
    command = ["uv", "run", "--directory", str(WORKER_DIR), "python", "-m"]
    return subprocess.Popen([*command, "avatar_worker.supervisor"], env=env)


def run():
    with TemporaryDirectory(prefix="avatar-e2e-") as temporary:
        with PostgresContainer("postgres:18.6", driver="psycopg") as postgres:
            url = postgres.get_connection_url()
            migrate(url)
            data_dir = Path(temporary)
            settings = Settings(url, data_dir, WORKER_TOKEN, app_env="test", lease_seconds=600)
            engine = get_engine(url)
            with Session(engine) as db:
                catalog = seed_dev_catalog(db, data_dir)
                recipe = db.get(RenderRecipe, catalog.recipe_id)
                recipe.spec = {
                    "development": True,
                    "limits": {"max_audio_seconds": 40, "chars_per_second": 15},
                }
                avatar = db.get(Avatar, catalog.avatar_id)
                avatar.name = "Helena (fixture local)"
                db.add(
                    Avatar(
                        name="Rafael (fixture local)",
                        voice="masculina",
                        source_file_id=avatar.source_file_id,
                        prepared_file_id=avatar.prepared_file_id,
                        prepare_status="ativo",
                    )
                )
                scene = db.get(Scene, catalog.scene_id)
                scene.name = "Fundo sálvia (fixture local)"
                scene.background_color = "#CFE0D6"
                for ratio, size in [("9x16", (270, 480)), ("16x9", (480, 270))]:
                    buffer = io.BytesIO()
                    Image.new("RGB", size, scene.background_color).save(buffer, format="PNG")
                    content = buffer.getvalue()
                    stored = save_stream(
                        db,
                        data_dir,
                        "seed",
                        f"scene-{ratio}.png",
                        io.BytesIO(content),
                        hashlib.sha256(content).hexdigest(),
                        "image/png",
                    )
                    setattr(scene, f"preview_{ratio}_file_id", stored.id)
                user = create_user(db, USERNAME, PASSWORD)
                issued = issue_api_key(db, user.id, "Consumidor HTTP isolado")
                api_key = issued.key
                db.commit()
            app = create_app(settings)
            claims = {}

            # Não importado por main.py, CLI ou imagem de produção. Só loopback.
            @app.get("/__test/config")
            def config():
                return {"username": USERNAME, "password": PASSWORD, "api_key": api_key}

            @app.get("/__test/logo.png")
            def logo():
                # Logo sintético: retângulo branco em fundo transparente.
                image = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
                image.paste((255, 255, 255, 255), (20, 20, 280, 100))
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                return Response(buffer.getvalue(), media_type="image/png")

            @app.get("/__test/picture.png")
            def picture():
                # Imagem de cena sintética: magenta 4:3, fácil de achar no quadro.
                buffer = io.BytesIO()
                Image.new("RGB", (800, 600), (255, 0, 255)).save(buffer, format="PNG")
                return Response(buffer.getvalue(), media_type="image/png")

            @app.get("/__test/music.wav")
            def music():
                # Trilha sintética: tom de 4 kHz, longe da voz de 300 Hz, para medir o ducking.
                wav = subprocess.run(
                    [
                        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                        "-i", "sine=frequency=4000:sample_rate=44100:duration=2",
                        "-ac", "2", "-f", "wav", "-",
                    ],
                    check=True, capture_output=True, timeout=60,
                ).stdout  # fmt: skip
                return Response(wav, media_type="audio/wav")

            @app.get("/__test/lessons/{lesson_id}/manifest")
            def lesson_manifest(lesson_id: uuid.UUID):
                with Session(engine) as db:
                    lesson = db.get(Lesson, lesson_id)
                    if lesson is None or lesson.result_file_id is None:
                        raise HTTPException(409, "Lesson not ready")
                    final = db.get(StoredFile, lesson.result_file_id)
                    manifest = Path(final.relative_path).with_name("manifest.json")
                return json.loads((data_dir / manifest).read_text("utf-8"))

            @app.post("/__test/presence")
            def presence():
                with Session(engine) as db:
                    db.execute(
                        update(WorkerHeartbeat).values(
                            last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=121)
                        )
                    )
                    db.commit()
                return {"ok": True}

            @app.post("/__test/claim")
            def claim():
                with httpx.Client(
                    base_url="http://127.0.0.1:8000",
                    headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
                ) as worker:
                    response = worker.post(
                        "/internal/v1/claim", json={"worker_id": "e2e-local", "kinds": ["video"]}
                    )
                    response.raise_for_status()
                    if response.status_code == 204:
                        raise HTTPException(409, "No queued job")
                    claimed = response.json()
                    claims[claimed["id"]] = claimed
                    ref = {
                        "attempt_id": claimed["attempt_id"],
                        "lease_generation": claimed["lease_generation"],
                    }
                    worker.post(
                        f"/internal/v1/jobs/{claimed['id']}/heartbeat", json={**ref, "stage": "tts"}
                    ).raise_for_status()
                    return claimed

            @app.post("/__test/jobs/{job_id}/{action}")
            def finish(job_id: uuid.UUID, action: str):
                claimed = claims.get(str(job_id))
                if claimed is None:
                    raise HTTPException(409, "Claim the job first")
                ref = {
                    "attempt_id": claimed["attempt_id"],
                    "lease_generation": claimed["lease_generation"],
                }
                with httpx.Client(
                    base_url="http://127.0.0.1:8000",
                    headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
                    timeout=30,
                ) as worker:
                    if action == "fail":
                        response = worker.post(
                            f"/internal/v1/jobs/{job_id}/fail",
                            json={
                                **ref,
                                "error_code": "RENDER_FAILED",
                                "error_message": "Falha controlada de inferência no teste local.",
                                "retryable": False,
                            },
                        )
                        response.raise_for_status()
                        return response.json()
                    if action != "complete":
                        raise HTTPException(404, "Unknown test action")
                    ratio = claimed["payload"]["aspect_ratio"]
                    size = "1080x1920" if ratio == "9:16" else "1920x1080"
                    with Session(engine) as db:
                        position = db.get(VideoJob, job_id).lesson_position
                    color = AVULSO_COLOR if position is None else scene_color(position)
                    seconds = "1" if position is None else LESSON_SCENE_SECONDS
                    voice = "anull" if position is None else LESSON_VOICE
                    video = data_dir / f"{job_id}.mp4"
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-v",
                            "error",
                            "-f",
                            "lavfi",
                            "-i",
                            f"color=c={color}:s={size}:r=25",
                            "-f",
                            "lavfi",
                            "-i",
                            "sine=frequency=440:sample_rate=48000",
                            "-t",
                            seconds,
                            "-af",
                            voice,
                            "-c:v",
                            "libx264",
                            "-preset",
                            "ultrafast",
                            "-pix_fmt",
                            "yuv420p",
                            "-c:a",
                            "aac",
                            "-movflags",
                            "+faststart",
                            str(video),
                        ],
                        check=True,
                        timeout=60,
                    )
                    result_file_id = None
                    for name, content in [
                        (
                            "manifest.json",
                            json.dumps(
                                {"audio_seconds": float(seconds), "test_only": True}
                            ).encode(),
                        ),
                        ("final.mp4", video.read_bytes()),
                    ]:
                        response = worker.put(
                            f"/internal/v1/jobs/{job_id}/attempts/{claimed['attempt_id']}/files/{name}",
                            data={
                                "lease_generation": str(claimed["lease_generation"]),
                                "sha256": hashlib.sha256(content).hexdigest(),
                            },
                            files={"file": (name, content)},
                        )
                        response.raise_for_status()
                        result_file_id = response.json()["id"]
                    response = worker.post(
                        f"/internal/v1/jobs/{job_id}/complete",
                        json={**ref, "result_file_id": result_file_id},
                    )
                    response.raise_for_status()
                    return response.json()

            supervisor = start_lesson_supervisor()
            try:
                uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
            finally:
                supervisor.terminate()
                try:
                    supervisor.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    supervisor.kill()
                engine.dispose()


if __name__ == "__main__":
    run()
