import gzip
import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from avatar_api import uploads
from avatar_api.errors import ApiError
from avatar_api.uploads import MAX_IMAGE_BYTES, validate_image

FIELD = "image"

SVG = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect/></svg>'
)
SVG_SEM_DECLARACAO = b'  <svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("foto.png", b"conteudo")
    return buffer.getvalue()


def _refuse(data: bytes, tmp_dir: Path) -> ApiError:
    with pytest.raises(ApiError) as caught:
        validate_image(io.BytesIO(data), FIELD, tmp_dir)
    error = caught.value
    assert error.status == 422
    assert error.field == FIELD
    assert list(tmp_dir.iterdir()) == []
    return error


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    return directory


@pytest.mark.parametrize(
    ("fmt", "alpha", "content_type", "extension"),
    [
        ("jpeg", False, "image/jpeg", ".jpg"),
        ("png", True, "image/png", ".png"),
        ("webp", False, "image/webp", ".webp"),
        ("webp", True, "image/webp", ".webp"),
    ],
)
def test_aceita_imagem_valida(image_bytes, tmp_dir, fmt, alpha, content_type, extension):
    data = image_bytes(fmt, (64, 48), alpha)

    image = validate_image(io.BytesIO(data), FIELD, tmp_dir)

    assert image.content_type == content_type
    assert image.extension == extension
    assert (image.width, image.height) == (64, 48)
    assert image.has_alpha is alpha
    assert image.size_bytes == len(data)
    assert image.sha256 == hashlib.sha256(data).hexdigest()
    assert image.path.parent == tmp_dir
    assert image.path.read_bytes() == data


@pytest.mark.parametrize(
    ("data", "motivo"),
    [
        (SVG, "SVG não é aceito."),
        (SVG_SEM_DECLARACAO, "SVG não é aceito."),
        (b"\xef\xbb\xbf<?xml version='1.0'?><root/>", "SVG não é aceito."),
        (b"MZ\x90\x00\x03" + bytes(200), "Arquivo executável não é aceito."),
        (b"\x7fELF\x02\x01\x01" + bytes(200), "Arquivo executável não é aceito."),
        (b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01" + bytes(200), "Arquivo executável não é aceito."),
        (b"#!/bin/sh\nrm -rf /\n", "Arquivo executável não é aceito."),
        (_zip_bytes(), "Arquivo compactado não é aceito."),
        (gzip.compress(b"conteudo"), "Arquivo compactado não é aceito."),
        (b"7z\xbc\xaf\x27\x1c" + bytes(50), "Arquivo compactado não é aceito."),
        (b"Rar!\x1a\x07\x01\x00" + bytes(50), "Arquivo compactado não é aceito."),
        (b"BZh91AY&SY" + bytes(50), "Arquivo compactado não é aceito."),
        (b"\xfd7zXZ\x00" + bytes(50), "Arquivo compactado não é aceito."),
        (GIF, "Envie uma imagem JPEG, PNG ou WebP."),
        (b"%PDF-1.7\n", "Envie uma imagem JPEG, PNG ou WebP."),
    ],
    ids=[
        "svg-renomeado",
        "svg-sem-declaracao",
        "xml-com-bom",
        "exe",
        "elf",
        "mach-o",
        "script",
        "zip",
        "gzip",
        "7z",
        "rar",
        "bzip2",
        "xz",
        "gif-como-png",
        "pdf",
    ],
)
def test_recusa_tipo_pela_assinatura(tmp_dir, data, motivo):
    error = _refuse(data, tmp_dir)

    assert error.code == "UNSUPPORTED_FILE_TYPE"
    assert error.message == motivo


def test_extensao_mentirosa_vale_o_conteudo(image_bytes, tmp_dir):
    # Um PNG enviado como foto.jpg é tratado como PNG: o nome do arquivo não conta.
    image = validate_image(io.BytesIO(image_bytes("png")), FIELD, tmp_dir)

    assert image.content_type == "image/png"
    assert image.extension == ".png"


def test_recusa_formato_decodificado_diferente_da_assinatura(image_bytes, tmp_dir, monkeypatch):
    monkeypatch.setattr(
        uploads,
        "_decode_in_subprocess",
        lambda path, field: {"format": "GIF", "width": 1, "height": 1, "has_alpha": False},
    )

    error = _refuse(image_bytes("png"), tmp_dir)

    assert error.code == "UNSUPPORTED_FILE_TYPE"
    assert error.message == "Envie uma imagem JPEG, PNG ou WebP."


def test_recusa_arquivo_vazio(tmp_dir):
    error = _refuse(b"", tmp_dir)

    assert error.code == "FILE_EMPTY"
    assert error.message == "O arquivo está vazio."


class _CountingStream(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.bytes_read = 0

    def read(self, size: int | None = -1) -> bytes:
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


def test_recusa_arquivo_de_21_mb_sem_ler_alem_do_limite(tmp_dir):
    stream = _CountingStream(b"\xff\xd8\xff\xe0" + bytes(21 * 1024 * 1024))

    with pytest.raises(ApiError) as caught:
        validate_image(stream, FIELD, tmp_dir)

    error = caught.value
    assert (error.status, error.code, error.field) == (422, "FILE_TOO_LARGE", FIELD)
    assert error.message == "A imagem passa do limite de 20 MB."
    assert stream.bytes_read == MAX_IMAGE_BYTES + 1
    assert list(tmp_dir.iterdir()) == []


def test_aceita_imagem_no_limite_exato_de_bytes(image_bytes, tmp_dir):
    # Bytes extras depois do fim do PNG não impedem a leitura; o total fica em 20 MiB.
    data = image_bytes("png")
    data += bytes(MAX_IMAGE_BYTES - len(data))

    image = validate_image(io.BytesIO(data), FIELD, tmp_dir)

    assert image.size_bytes == MAX_IMAGE_BYTES


def test_recusa_imagem_de_41_megapixels(image_bytes, tmp_dir):
    data = image_bytes("png", (6500, 6400))
    assert len(data) < MAX_IMAGE_BYTES

    error = _refuse(data, tmp_dir)

    assert error.code == "IMAGE_TOO_LARGE"
    assert error.message == "A imagem passa do limite de 40 megapixels."


def test_recusa_png_truncado(image_bytes, tmp_dir):
    data = image_bytes("png", (400, 300))

    error = _refuse(data[: len(data) // 2], tmp_dir)

    assert error.code == "IMAGE_UNREADABLE"
    assert error.message == "Não foi possível ler a imagem. Envie outro arquivo."


def test_recusa_assinatura_valida_com_conteudo_corrompido(tmp_dir):
    error = _refuse(b"\x89PNG\r\n\x1a\n" + b"lixo" * 100, tmp_dir)

    assert error.code == "IMAGE_UNREADABLE"


def test_recusa_quando_a_decodificacao_passa_do_tempo(image_bytes, tmp_dir, monkeypatch):
    monkeypatch.setattr(uploads, "DECODE_TIMEOUT_SECONDS", 0.001)

    error = _refuse(image_bytes("jpeg"), tmp_dir)

    assert error.code == "IMAGE_UNREADABLE"
