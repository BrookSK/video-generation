import hashlib
import io
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api.config import Settings
from avatar_api.devseed import DevCatalog, seed_dev_catalog
from avatar_api.errors import ApiError
from avatar_api.models import Avatar, RenderRecipe, Scene, StoredFile
from avatar_api.storage import StoragePathError, resolve_path, save_stream

AVATAR_API = Path(sys.executable).parent / "avatar-api"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leftovers(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.rglob("*") if p.name.endswith(".tmp"))


def count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


class FailingStream(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        if self.tell() > 0:
            raise OSError("conexão caiu no meio do envio")
        return super().read(4)


def test_save_stream_grava_arquivo_com_hash_conferido(session: Session, settings: Settings):
    data = b"conteudo do video" * 100_000
    attempt_id = uuid.uuid4()

    stored = save_stream(
        session,
        settings.data_dir,
        "jobs/abc/tentativa",
        "final.mp4",
        io.BytesIO(data),
        sha256(data).upper(),
        "video/mp4",
        attempt_id=attempt_id,
    )

    path = settings.data_dir / "jobs/abc/tentativa/final.mp4"
    assert path.read_bytes() == data
    assert resolve_path(settings.data_dir, stored) == path.resolve()
    assert leftovers(settings.data_dir) == []
    session.expire_all()
    row = session.get(StoredFile, stored.id)
    assert row.relative_path == "jobs/abc/tentativa/final.mp4"
    assert row.name == "final.mp4"
    assert row.sha256 == sha256(data)
    assert row.size_bytes == len(data)
    assert row.content_type == "video/mp4"
    assert row.attempt_id == attempt_id


def test_sha256_divergente_recusado_sem_sobra_no_disco(session: Session, settings: Settings):
    data = b"arquivo enviado"

    with pytest.raises(ApiError) as exc:
        save_stream(
            session,
            settings.data_dir,
            "jobs/abc",
            "final.mp4",
            io.BytesIO(data),
            sha256(b"outro conteudo"),
            "video/mp4",
        )

    assert (exc.value.status, exc.value.code, exc.value.field) == (
        422,
        "CHECKSUM_MISMATCH",
        "sha256",
    )
    directory = settings.data_dir / "jobs/abc"
    assert list(directory.iterdir()) == []
    assert count(session, StoredFile) == 0


def test_sha256_mal_formado_recusado(session: Session, settings: Settings):
    with pytest.raises(ApiError) as exc:
        save_stream(
            session, settings.data_dir, "jobs", "a.bin", io.BytesIO(b"x"), "123", "text/plain"
        )

    assert (exc.value.status, exc.value.code) == (422, "VALIDATION_ERROR")
    assert list(settings.data_dir.iterdir()) == []


def test_falha_no_meio_da_copia_apaga_o_temporario(session: Session, settings: Settings):
    data = b"0123456789"

    with pytest.raises(OSError):
        save_stream(
            session,
            settings.data_dir,
            "jobs/abc",
            "final.mp4",
            FailingStream(data),
            sha256(data),
            "video/mp4",
        )

    assert list((settings.data_dir / "jobs/abc").iterdir()) == []
    assert count(session, StoredFile) == 0


def test_caminho_repetido_nao_sobrescreve(session: Session, settings: Settings):
    first = b"primeira versao"
    save_stream(
        session,
        settings.data_dir,
        "jobs/abc",
        "final.mp4",
        io.BytesIO(first),
        sha256(first),
        "video/mp4",
    )
    second = b"segunda versao"

    with pytest.raises(ApiError) as exc:
        save_stream(
            session,
            settings.data_dir,
            "jobs/abc",
            "final.mp4",
            io.BytesIO(second),
            sha256(second),
            "video/mp4",
        )

    assert (exc.value.status, exc.value.code) == (409, "FILE_EXISTS")
    assert (settings.data_dir / "jobs/abc/final.mp4").read_bytes() == first
    assert leftovers(settings.data_dir) == []
    assert count(session, StoredFile) == 1


@pytest.mark.parametrize(
    ("relative_dir", "name"),
    [
        ("../fora", "a.bin"),
        ("/tmp", "a.bin"),
        ("jobs/../..", "a.bin"),
        ("", "a.bin/.."),
        ("jobs", "../a.bin"),
        ("jobs", ".oculto"),
        ("jobs", "a/b.bin"),
    ],
)
def test_caminho_fora_de_data_dir_recusado(
    session: Session, settings: Settings, relative_dir: str, name: str
):
    data = b"x"
    before = set(settings.data_dir.parent.rglob("*"))

    with pytest.raises(StoragePathError):
        save_stream(
            session,
            settings.data_dir,
            relative_dir,
            name,
            io.BytesIO(data),
            sha256(data),
            "application/octet-stream",
        )

    assert set(settings.data_dir.parent.rglob("*")) == before
    assert count(session, StoredFile) == 0


def test_link_simbolico_para_fora_de_data_dir_recusado(
    session: Session, settings: Settings, tmp_path: Path
):
    outside = tmp_path / "fora"
    outside.mkdir()
    (settings.data_dir / "jobs").symlink_to(outside)
    data = b"x"

    with pytest.raises(StoragePathError):
        save_stream(
            session,
            settings.data_dir,
            "jobs",
            "a.bin",
            io.BytesIO(data),
            sha256(data),
            "application/octet-stream",
        )

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("relative_path", ["../segredo", "/etc/passwd", "a/../../b", "."])
def test_resolve_path_recusa_caminho_fora_de_data_dir(settings: Settings, relative_path: str):
    stored = StoredFile(relative_path=relative_path)

    with pytest.raises(StoragePathError):
        resolve_path(settings.data_dir, stored)


def test_seed_dev_catalog_idempotente(session: Session, settings: Settings):
    first = seed_dev_catalog(session, settings.data_dir)
    second = seed_dev_catalog(session, settings.data_dir)

    assert first == second
    assert count(session, RenderRecipe) == 1
    assert count(session, Avatar) == 1
    assert count(session, Scene) == 1
    assert count(session, StoredFile) == 2
    assert leftovers(settings.data_dir) == []


def test_seed_dev_catalog_conteudo(
    session: Session, settings: Settings, seeded_catalog: DevCatalog
):
    session.expire_all()
    recipe = session.get(RenderRecipe, seeded_catalog.recipe_id)
    assert recipe.name == "dev-seed"
    assert recipe.is_current is True
    assert recipe.max_script_chars == 600
    assert recipe.spec["development"] is True

    avatar = session.get(Avatar, seeded_catalog.avatar_id)
    assert avatar.prepare_status == "ativo"
    assert avatar.voice == "feminina"
    assert avatar.archived_at is None
    for file_id in (avatar.source_file_id, avatar.prepared_file_id):
        stored = session.get(StoredFile, file_id)
        content = resolve_path(settings.data_dir, stored).read_bytes()
        assert content.startswith(PNG_SIGNATURE)
        assert sha256(content) == stored.sha256
        assert stored.size_bytes == len(content)
        assert stored.content_type == "image/png"

    scene = session.get(Scene, seeded_catalog.scene_id)
    assert scene.archived_at is None
    assert scene.background_color is not None
    assert scene.background_file_id is None
    assert set(scene.composition) == {"9:16", "16:9"}


def test_seed_dev_catalog_nao_toma_vigencia_de_outra_receita(session: Session, settings: Settings):
    session.add(RenderRecipe(name="RECIPE-v1", max_script_chars=1000, spec={}, is_current=True))
    session.commit()

    catalog = seed_dev_catalog(session, settings.data_dir)

    session.expire_all()
    assert session.get(RenderRecipe, catalog.recipe_id).is_current is False
    current = session.scalars(select(RenderRecipe.name).where(RenderRecipe.is_current)).all()
    assert current == ["RECIPE-v1"]


def run_seed_dev(database_url: str, data_dir: Path, app_env: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url, "DATA_DIR": str(data_dir)}
    env["APP_ENV"] = app_env
    return subprocess.run(
        [str(AVATAR_API), "seed-dev"], capture_output=True, text=True, env=env, timeout=60
    )


def test_cli_seed_dev_recusado_fora_de_development(session: Session, settings: Settings):
    for app_env in ("production", "test", ""):
        result = run_seed_dev(settings.database_url, settings.data_dir, app_env)

        assert result.returncode == 1
        assert "APP_ENV=development" in result.stderr
        assert result.stdout == ""
    assert count(session, RenderRecipe) == 0
    assert count(session, Avatar) == 0
    assert count(session, Scene) == 0
    assert list(settings.data_dir.iterdir()) == []


def test_cli_seed_dev_imprime_json_e_e_idempotente(session: Session, settings: Settings):
    first = run_seed_dev(settings.database_url, settings.data_dir, "development")
    second = run_seed_dev(settings.database_url, settings.data_dir, "development")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    printed = json.loads(first.stdout)
    assert printed == json.loads(second.stdout)
    assert set(printed) == {"recipe_id", "avatar_id", "scene_id"}
    assert session.get(RenderRecipe, uuid.UUID(printed["recipe_id"])).name == "dev-seed"
    assert session.get(Avatar, uuid.UUID(printed["avatar_id"])) is not None
    assert session.get(Scene, uuid.UUID(printed["scene_id"])) is not None
    assert count(session, Avatar) == 1
