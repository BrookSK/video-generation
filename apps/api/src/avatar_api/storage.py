"""Arquivos no volume de dados: gravação atômica com SHA-256 conferido."""

import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.errors import ApiError
from avatar_api.models import StoredFile

CHUNK_BYTES = 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StoragePathError(ValueError):
    """Caminho que sairia de DATA_DIR; indica erro de programação ou dado adulterado."""


def _inside(data_dir: Path, relative: str) -> Path:
    root = data_dir.resolve()
    target = (root / relative).resolve()
    if target == root or not target.is_relative_to(root):
        raise StoragePathError(f"caminho fora de DATA_DIR: {relative!r}")
    return target


def resolve_path(data_dir: Path, file: StoredFile) -> Path:
    """Caminho absoluto do arquivo, recusando qualquer um que saia de DATA_DIR."""
    return _inside(data_dir, file.relative_path)


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_to_temp(directory: Path, name: str, stream: BinaryIO) -> tuple[Path, str, int]:
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(
        dir=directory, prefix=f".{name}.", suffix=".tmp", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            while chunk := stream.read(CHUNK_BYTES):
                digest.update(chunk)
                size += len(chunk)
                tmp.write(chunk)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
    return tmp_path, digest.hexdigest(), size


def save_stream(
    session: Session,
    data_dir: Path,
    relative_dir: str,
    name: str,
    stream: BinaryIO,
    expected_sha256: str,
    content_type: str,
    attempt_id: uuid.UUID | None = None,
) -> StoredFile:
    """Grava o fluxo em relative_dir/name dentro de DATA_DIR e cria a linha de stored_files.

    O conteúdo vai para um temporário no mesmo diretório; só com o SHA-256 igual ao
    declarado ele é sincronizado e renomeado para o nome final, e a linha é confirmada.
    """
    expected = expected_sha256.strip().lower()
    if not _SHA256.fullmatch(expected):
        raise ApiError(422, "VALIDATION_ERROR", "SHA-256 inválido.", "sha256")
    if not _NAME.fullmatch(name):
        raise StoragePathError(f"nome de arquivo inválido: {name!r}")
    directory = _inside(data_dir, relative_dir)
    final = directory / name
    relative_path = final.relative_to(data_dir.resolve()).as_posix()

    directory.mkdir(parents=True, exist_ok=True)
    tmp_path, sha256, size = _copy_to_temp(directory, name, stream)
    try:
        if sha256 != expected:
            raise ApiError(
                422,
                "CHECKSUM_MISMATCH",
                "O SHA-256 do arquivo não confere com o informado.",
                "sha256",
            )
        stored = StoredFile(
            relative_path=relative_path,
            name=name,
            size_bytes=size,
            sha256=sha256,
            content_type=content_type,
            attempt_id=attempt_id,
        )
        session.add(stored)
        # O flush antes do rename faz o índice único de relative_path barrar uma segunda
        # gravação no mesmo caminho sem sobrescrever o arquivo já registrado.
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise ApiError(
                409, "FILE_EXISTS", "Já existe um arquivo gravado nesse caminho.", "name"
            ) from None
        os.replace(tmp_path, final)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    try:
        _fsync_dir(directory)
        session.commit()
    except BaseException:
        session.rollback()
        final.unlink(missing_ok=True)
        raise
    return stored
