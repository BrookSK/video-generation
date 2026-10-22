"""Montagem da aula com FFmpeg real: cenas sintéticas de cores distintas, nada de GPU."""

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from avatar_worker.finalize import probe_output
from avatar_worker.lesson import CARD_SECONDS, assemble_lesson, draw_card
from avatar_worker.lesson_text import LAYOUTS
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


# --- legenda, tópicos e imagem por cena ----------------------------------------------------

MAGENTA = (220, 30, 200)


def blend(top: str, below: tuple[int, int, int], alpha: float = 225 / 255) -> tuple[int, ...]:
    return tuple(round(alpha * a + (1 - alpha) * b) for a, b in zip(rgb(top), below, strict=True))


def picture(path: Path, size: tuple[int, int]) -> Path:
    Image.new("RGB", size, MAGENTA).save(path)
    return path


def magenta_box(frame: Image.Image) -> tuple[int, int, int, int]:
    mask = Image.new("L", frame.size)
    mask.putdata([255 if near(p, MAGENTA, 30) else 0 for p in frame.get_flattened_data()])
    return mask.getbbox()


def rich_payload(aspect: str) -> dict:
    data = payload(aspect)
    for scene in data["scenes"]:
        scene["script_text"] = f"Fala literal da cena {scene['position']}, com legenda."
        scene["topics"] = ["Isolar a área", "Usar EPI"] if scene["position"] == 1 else []
        scene["image_file_id"] = "imagem-2" if scene["position"] == 2 else None
    return data


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
def test_legenda_topicos_e_imagem_so_nas_cenas_certas(tmp_path, logo, aspect):
    size = "1920x1080" if aspect == "16:9" else "1080x1920"
    layout = LAYOUTS[aspect]
    scenes = {
        position: make_scene(tmp_path / f"cena-{position}.mp4", color, seconds, size)
        for position, _, color, seconds in SCENES
    }
    image = picture(tmp_path / "tela.png", (800, 400))

    result = assemble_lesson(
        rich_payload(aspect), scenes, logo, tmp_path / "work", lambda: None, images={2: image}
    )

    final = result.files["final.mp4"]
    frames, start = {}, CARD_SECONDS
    for position, _, _, seconds in SCENES:
        frames[position] = frame_at(final, start + seconds / 2, tmp_path / f"q-{position}.png")
        start += seconds
    colors = {position: color for position, _, color, _ in SCENES}
    il, it, ir, ib = layout.image
    image_center = ((il + ir) // 2, (it + ib) // 2)
    width = 1920 if aspect == "16:9" else 1080
    subtitle = (width // 2, layout.subtitle_bottom - 12)

    # Legenda em todas as cenas, na caixa da cor de fundo da identidade.
    # Na cena com imagem, a legenda fica sobre o fundo da cena, que é a cor da identidade.
    for position, frame in frames.items():
        under = rgb(BACKGROUND) if position == 2 else colors[position]
        assert near(frame.getpixel(subtitle), blend(BACKGROUND, under), 20), position
    # Tópicos só na cena 1.
    tl, tt, tr, tb = layout.topics
    corner = (tl + 10, tt + 10) if aspect == "16:9" else (tl + 10, tb - 10)
    assert near(frames[1].getpixel(corner), blend(BACKGROUND, colors[1]), 20)
    assert near(frames[3].getpixel(corner), colors[3])
    # Imagem só na cena 2, sem distorção, com o apresentador no quadro menor.
    assert near(frames[2].getpixel(image_center), MAGENTA, 20)
    left, top, right, bottom = magenta_box(frames[2])
    assert abs((right - left) / (bottom - top) - 2.0) < 0.03
    assert left >= il and right <= ir and top >= it and bottom <= ib
    pl, pt, pr, pb = layout.pip
    assert near(frames[2].getpixel(((pl + pr) // 2, (pt + pb) // 2)), colors[2], 20)
    for position in (1, 3):
        assert near(frames[position].getpixel(image_center), colors[position]), position
        assert magenta_box(frames[position]) is None

    manifest = json.loads(result.files["manifest.json"].read_text())
    for scene, sent in zip(manifest["scenes"], rich_payload(aspect)["scenes"][::-1], strict=True):
        assert "".join(s["text"] for s in scene["subtitles"]) == sent["script_text"]
        assert scene["subtitle_timing"] == "silence"
    assert manifest["scenes"][0]["topics"] == ["Isolar a área", "Usar EPI"]
    assert manifest["scenes"][1]["image_sha256"] is not None


def test_imagem_ilegivel_falha_com_input_invalid(tmp_path, logo):
    scenes = {
        position: make_scene(tmp_path / f"cena-{position}.mp4", color, seconds, "1920x1080")
        for position, _, color, seconds in SCENES
    }
    broken = tmp_path / "tela.png"
    broken.write_bytes(b"nao e imagem")

    with pytest.raises(GenerationFailure) as exc_info:
        assemble_lesson(
            rich_payload("16:9"), scenes, logo, tmp_path / "work", lambda: None, images={2: broken}
        )

    assert exc_info.value.code == "INPUT_INVALID"
    assert "cena 2" in exc_info.value.message
