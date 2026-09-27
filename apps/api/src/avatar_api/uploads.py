"""Validação de imagem enviada: assinatura, tamanho, pixels e decodificação isolada.

A decodificação roda num subprocesso (python -m avatar_api.uploads <caminho>) com limite
de tempo e, no Linux, de memória, para que um arquivo malicioso não derrube a API. As
prévias geradas a partir de uma imagem enviada usam o mesmo subprocesso limitado
(python -m avatar_api.uploads --previews <caminho> <saída> <nome>=<L>x<A>...).
"""

import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from avatar_api.errors import ApiError

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
DECODE_TIMEOUT_SECONDS = 10
DECODE_MEMORY_BYTES = 1024 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
_SNIFF_BYTES = 512
_EXIT_TOO_MANY_PIXELS = 3
_PREVIEWS_MODE = "--previews"

_EXECUTABLE_MAGIC = (
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"#!",
)
_ARCHIVE_MAGIC = (
    b"PK",
    b"\x1f\x8b",
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07",
    b"BZh",
    b"\xfd7zXZ\x00",
)


@dataclass(frozen=True)
class _ImageKind:
    content_type: str
    extension: str
    pillow_formats: frozenset[str]


_JPEG = _ImageKind("image/jpeg", ".jpg", frozenset({"JPEG", "MPO"}))
_PNG = _ImageKind("image/png", ".png", frozenset({"PNG"}))
_WEBP = _ImageKind("image/webp", ".webp", frozenset({"WEBP"}))


@dataclass(frozen=True)
class ValidatedImage:
    path: Path
    sha256: str
    size_bytes: int
    content_type: str
    extension: str
    width: int
    height: int
    has_alpha: bool


def _unsupported(field: str, message: str) -> ApiError:
    return ApiError(422, "UNSUPPORTED_FILE_TYPE", message, field)


def _unreadable(field: str) -> ApiError:
    return ApiError(
        422, "IMAGE_UNREADABLE", "Não foi possível ler a imagem. Envie outro arquivo.", field
    )


def _copy_limited(stream: BinaryIO, tmp_dir: Path, field: str) -> tuple[Path, str, int]:
    """Copia no máximo MAX_IMAGE_BYTES + 1 byte; passou do limite, apaga e recusa."""
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(
        dir=tmp_dir, prefix=".upload.", suffix=".tmp", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            while size <= MAX_IMAGE_BYTES:
                chunk = stream.read(min(CHUNK_BYTES, MAX_IMAGE_BYTES + 1 - size))
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                tmp.write(chunk)
            if size > MAX_IMAGE_BYTES:
                raise ApiError(422, "FILE_TOO_LARGE", "A imagem passa do limite de 20 MB.", field)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
    return tmp_path, digest.hexdigest(), size


def _sniff(head: bytes, field: str) -> _ImageKind:
    if head.startswith(b"\xff\xd8\xff"):
        return _JPEG
    if head.startswith(b"\x89PNG"):
        return _PNG
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return _WEBP
    text = head.removeprefix(b"\xef\xbb\xbf").lstrip().lower()
    if text.startswith(b"<?xml") or b"<svg" in text:
        raise _unsupported(field, "SVG não é aceito.")
    if head.startswith(_EXECUTABLE_MAGIC):
        raise _unsupported(field, "Arquivo executável não é aceito.")
    if head.startswith(_ARCHIVE_MAGIC):
        raise _unsupported(field, "Arquivo compactado não é aceito.")
    raise _unsupported(field, "Envie uma imagem JPEG, PNG ou WebP.")


def _run_limited(args: list[str], field: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            [sys.executable, "-m", "avatar_api.uploads", *args],
            capture_output=True,
            timeout=DECODE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise _unreadable(field) from None


def _decode_in_subprocess(path: Path, field: str) -> dict:
    result = _run_limited([str(path)], field)
    if result.returncode == _EXIT_TOO_MANY_PIXELS:
        raise ApiError(422, "IMAGE_TOO_LARGE", "A imagem passa do limite de 40 megapixels.", field)
    if result.returncode != 0:
        raise _unreadable(field)
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise _unreadable(field) from None


def validate_image(stream: BinaryIO, field: str, tmp_dir: Path) -> ValidatedImage:
    """Confere a imagem e devolve o temporário validado; em toda recusa, apaga o temporário.

    Recusas viram ApiError 422 com código, campo e motivo em português. O chamador fica
    dono do temporário devolvido.
    """
    tmp_path, sha256, size = _copy_limited(stream, tmp_dir, field)
    try:
        if size == 0:
            raise ApiError(422, "FILE_EMPTY", "O arquivo está vazio.", field)
        with tmp_path.open("rb") as file:
            kind = _sniff(file.read(_SNIFF_BYTES), field)
        info = _decode_in_subprocess(tmp_path, field)
        if info["format"] not in kind.pillow_formats:
            raise _unsupported(field, "Envie uma imagem JPEG, PNG ou WebP.")
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return ValidatedImage(
        path=tmp_path,
        sha256=sha256,
        size_bytes=size,
        content_type=kind.content_type,
        extension=kind.extension,
        width=info["width"],
        height=info["height"],
        has_alpha=info["has_alpha"],
    )


def render_previews(path: Path, sizes: dict[str, tuple[int, int]], field: str) -> dict[str, bytes]:
    """PNG de cada tamanho, com a imagem validada ajustada por cover e centralizada.

    Decodifica no subprocesso limitado; falha ou tempo esgotado vira 422 IMAGE_UNREADABLE.
    Os PNG passam por um diretório temporário ao lado da imagem, apagado ao final.
    """
    specs = [f"{name}={width}x{height}" for name, (width, height) in sizes.items()]
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".previews.") as out_dir:
        result = _run_limited([_PREVIEWS_MODE, str(path), out_dir, *specs], field)
        if result.returncode != 0:
            raise _unreadable(field)
        try:
            return {name: (Path(out_dir) / f"{name}.png").read_bytes() for name in sizes}
        except OSError:
            raise _unreadable(field) from None


def _limit_memory() -> None:
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (DECODE_MEMORY_BYTES, DECODE_MEMORY_BYTES))


def _inspect(path: str) -> int:
    """Corpo do subprocesso: decodifica a imagem e escreve o resultado em JSON."""
    _limit_memory()
    from PIL import Image, ImageOps

    # O limite de pixels é conferido aqui, antes do load(); o do Pillow ficaria no caminho.
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as image:
        width, height = image.size
        if width * height > MAX_IMAGE_PIXELS:
            return _EXIT_TOO_MANY_PIXELS
        image_format = image.format
        oriented = ImageOps.exif_transpose(image)
        oriented.load()
        json.dump(
            {
                "format": image_format,
                "width": oriented.width,
                "height": oriented.height,
                "has_alpha": oriented.has_transparency_data,
            },
            sys.stdout,
        )
    return 0


def _previews(path: str, out_dir: str, specs: list[str]) -> int:
    """Corpo do subprocesso: grava <out_dir>/<nome>.png de cada <nome>=<L>x<A>."""
    _limit_memory()
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as image:
        width, height = image.size
        if width * height > MAX_IMAGE_PIXELS:
            return _EXIT_TOO_MANY_PIXELS
        source = ImageOps.exif_transpose(image).convert("RGB")
    for spec in specs:
        name, size = spec.split("=")
        preview_width, preview_height = (int(value) for value in size.split("x"))
        preview = ImageOps.fit(source, (preview_width, preview_height), Image.Resampling.LANCZOS)
        preview.save(Path(out_dir) / f"{name}.png", format="PNG")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2:
        sys.exit(_inspect(sys.argv[1]))
    if len(sys.argv) >= 5 and sys.argv[1] == _PREVIEWS_MODE:
        sys.exit(_previews(sys.argv[2], sys.argv[3], sys.argv[4:]))
    sys.exit(2)
