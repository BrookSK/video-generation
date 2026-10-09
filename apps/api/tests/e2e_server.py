"""Servidor de aceitação local. Controles /__test existem só neste processo de teste.

PostgreSQL, migrações, autenticação, armazenamento e protocolo worker são reais.
Mídia FFmpeg e catálogo sintético NÃO comprovam inferência, GPU nem qualidade humana.
Execute: uv run --directory apps/api python tests/e2e_server.py
"""

import hashlib
import io
import json
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from conftest import migrate
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import update
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from avatar_api.auth import create_user, issue_api_key
from avatar_api.config import Settings
from avatar_api.db import get_engine
from avatar_api.devseed import seed_dev_catalog
from avatar_api.main import create_app
from avatar_api.models import Avatar, RenderRecipe, Scene, WorkerHeartbeat
from avatar_api.storage import save_stream

USERNAME = "e2e@local.test"
PASSWORD = "isolated-e2e-password"
WORKER_TOKEN = "isolated-e2e-worker"


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
                    video = data_dir / f"{job_id}.mp4"
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-v",
                            "error",
                            "-f",
                            "lavfi",
                            "-i",
                            f"color=c=0xCFE0D6:s={size}:r=25",
                            "-f",
                            "lavfi",
                            "-i",
                            "sine=frequency=440:sample_rate=48000",
                            "-t",
                            "1",
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
                            json.dumps({"audio_seconds": 1.0, "test_only": True}).encode(),
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

            try:
                uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
            finally:
                engine.dispose()


if __name__ == "__main__":
    run()
