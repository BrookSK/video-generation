"""Montagem da aula com FFmpeg real: cenas sintéticas de cores distintas, nada de GPU."""

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from avatar_worker.finalize import probe_output
from avatar_worker.lesson import CARD_SECONDS, assemble_lesson, draw_card
from avatar_worker.video import GenerationFailure

BACKGROUND = "#0B2545"
ACCENT = "#F2A541"
SCENES = [
    # posição, plano, cor, duração em segundos
    (1, "medio", (220, 40, 40), 1.0),
    (2, "close", (40, 200, 60), 1.2),
    (3, "medio", (40, 60, 220), 0.8),
]


def _hex(rgb: tuple[int, int, int]) -> str:
    return "0x{:02X}{:02X}{:02X}".format(*rgb)


def make_scene(path: Path, rgb: tuple[int, int, int], seconds: float, size: str) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={_hex(rgb)}:s={size}:r=25:d={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


def frame_at(video: Path, seconds: float, out: Path) -> Image.Image:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{seconds:.3f}",
            "-i", str(video), "-frames:v", "1", str(out),
        ],
        check=True,
    )  # fmt: skip
    with Image.open(out) as image:
        return image.convert("RGB")


def near(pixel, expected, tolerance=14) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, expected, strict=True))


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


@pytest.fixture
def logo(tmp_path: Path) -> Path:
    path = tmp_path / "logo.png"
    image = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (20, 20, 280, 100))
    image.save(path)
    return path


def payload(aspect: str = "16:9") -> dict:
    return {
        "lesson_id": "aula-de-teste",
        "aspect_ratio": aspect,
        "logo_file_id": "logo",
        "background_color": BACKGROUND,
        "accent_color": ACCENT,
        "scenes": [
            {"position": position, "shot": shot, "file_id": f"cena-{position}"}
            for position, shot, _, _ in reversed(SCENES)
        ],
    }


def test_aula_16x9_tem_perfil_duracao_abertura_ordem_e_encerramento(tmp_path, logo):
    scenes = {
        position: make_scene(tmp_path / f"cena-{position}.mp4", color, seconds, "1920x1080")
        for position, _, color, seconds in SCENES
    }

    result = assemble_lesson(payload(), scenes, logo, tmp_path / "work", lambda: None)

    final = result.files["final.mp4"]
    profile = probe_output(final)
    assert (profile["width"], profile["height"]) == (1920, 1080)
    assert (profile["video_codec"], profile["pix_fmt"], profile["r_frame_rate"]) == (
        "h264",
        "yuv420p",
        "25/1",
    )
    assert (profile["audio_codec"], profile["sample_rate"]) == ("aac", 48000)
    expected = 2 * CARD_SECONDS + sum(seconds for *_, seconds in SCENES)
    junction = (len(SCENES) + 1) / 25
    assert abs(profile["video_duration"] - expected) <= junction
    assert abs(profile["audio_duration"] - expected) <= junction

    opening = frame_at(final, 1.5, tmp_path / "abertura.png")
    assert near(opening.getpixel((40, 40)), rgb(BACKGROUND))
    assert near(opening.getpixel((960, 540)), (255, 255, 255))
    accent_band = [opening.getpixel((960, y)) for y in range(560, 700)]
    assert any(near(pixel, rgb(ACCENT)) for pixel in accent_band)
    start = CARD_SECONDS
    for position, _, color, seconds in SCENES:
        frame = frame_at(final, start + seconds / 2, tmp_path / f"quadro-{position}.png")
        assert near(frame.getpixel((960, 540)), color), position
        start += seconds
    closing = frame_at(final, start + 1.5, tmp_path / "encerramento.png")
    assert near(closing.getpixel((40, 40)), rgb(BACKGROUND))

    manifest = json.loads(result.files["manifest.json"].read_text())
    assert [(s["position"], s["shot"]) for s in manifest["scenes"]] == [
        (1, "medio"),
        (2, "close"),
        (3, "medio"),
    ]


def test_cena_com_resolucao_diferente_falha_sem_escalar(tmp_path, logo):
    scenes = {
        position: make_scene(tmp_path / f"cena-{position}.mp4", color, seconds, "1920x1080")
        for position, _, color, seconds in SCENES
    }
    scenes[2] = make_scene(tmp_path / "cena-vertical.mp4", (0, 0, 0), 0.5, "1080x1920")

    with pytest.raises(GenerationFailure) as exc_info:
        assemble_lesson(payload(), scenes, logo, tmp_path / "work", lambda: None)

    assert exc_info.value.code == "OUTPUT_INVALID"
    assert exc_info.value.retryable is False
    assert "cena 2" in exc_info.value.message
    assert not (tmp_path / "work" / "final.mp4").exists()


def test_logo_grande_e_reduzido_e_pequeno_nunca_e_ampliado(tmp_path):
    big, small = tmp_path / "grande.png", tmp_path / "pequeno.png"
    Image.new("RGB", (4000, 400), (255, 255, 255)).save(big)
    Image.new("RGB", (40, 20), (255, 255, 255)).save(small)

    for path, max_width in ((big, round(1920 * 0.6)), (small, 40)):
        card = draw_card(path, BACKGROUND, ACCENT, (1920, 1080))
        left, top, right, bottom = card.convert("L").point(lambda v: 255 * (v == 255)).getbbox()
        assert right - left <= max_width
        center = ((left + right) / 2, (top + bottom) / 2)
        assert abs(center[0] - 960) <= 1


def test_logo_ilegivel_falha_com_input_invalid(tmp_path):
    broken = tmp_path / "logo.png"
    broken.write_bytes(b"nao e imagem")

    with pytest.raises(GenerationFailure) as exc_info:
        draw_card(broken, BACKGROUND, ACCENT, (1080, 1920))

    assert exc_info.value.code == "INPUT_INVALID"
