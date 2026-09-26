import struct
import subprocess
from pathlib import Path

import pytest

from avatar_worker import finalize
from avatar_worker.finalize import build_finalize_args, probe_output, run_finalize
from avatar_worker.recipe import load_recipe

MODELS_DIR = Path(__file__).resolve().parents[3] / "docs" / "models"
RECIPE = load_recipe(MODELS_DIR / "RECIPE-v1.json", MODELS_DIR / "MODEL_MANIFEST.json")
PAD_COLOR = "#1f2937"
PAD_RGB = (31, 41, 55)
SECONDS = 2
RENDER_SIZES = {"9:16": (448, 896), "16:9": (896, 448)}


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], shell=False, check=True)


def _render(path, size):
    width, height = size
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"color=c=red:s={width}x{height}:r=25:d={SECONDS}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    )


def _wav(path):
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=24000:duration={SECONDS}",
        "-ac",
        "1",
        str(path),
    )


def _top_level_atoms(path):
    atoms = []
    data = Path(path).read_bytes()
    offset = 0
    while offset + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[offset : offset + 8])
        if size == 1:
            size = struct.unpack(">Q", data[offset + 8 : offset + 16])[0]
        elif size == 0:
            size = len(data) - offset
        atoms.append(kind.decode("latin-1"))
        offset += size
    return atoms


def _pixel(path, x, y):
    frame = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        shell=False,
        check=True,
        capture_output=True,
    ).stdout
    width = probe_output(path)["width"]
    offset = (y * width + x) * 3
    return tuple(frame[offset : offset + 3])


def test_args_are_exact_list_without_shortest():
    args = build_finalize_args(
        "render.mp4", "audio.wav", "final.mp4", (1080, 1920), PAD_COLOR, RECIPE.output
    )

    assert args == [
        "ffmpeg",
        "-y",
        "-i",
        "render.mp4",
        "-i",
        "audio.wav",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        "fps=25,scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=#1f2937,setsar=1,format=yuv420p",
        "-fps_mode",
        "cfr",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "final.mp4",
    ]
    assert "-shortest" not in args
    assert all(isinstance(arg, str) for arg in args)


@pytest.mark.parametrize("color", ["1f2937", "#1f293", "#1f29377", "#gggggg", "red", "", None])
def test_invalid_color_raises_before_ffmpeg(monkeypatch, color):
    def fail(*args, **kwargs):
        raise AssertionError("ffmpeg não pode ser chamado com cor inválida")

    monkeypatch.setattr(finalize.subprocess, "run", fail)
    with pytest.raises(ValueError, match="#RRGGBB"):
        build_finalize_args("r.mp4", "a.wav", "o.mp4", (1080, 1920), color, RECIPE.output)


def test_run_finalize_uses_no_shell(monkeypatch):
    calls = []
    monkeypatch.setattr(
        finalize.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs))
    )
    run_finalize(["ffmpeg", "-version"])

    assert calls[0][0] == ["ffmpeg", "-version"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["check"] is True


@pytest.mark.parametrize("aspect", RENDER_SIZES)
def test_finalize_exports_dat005_profile(tmp_path, aspect):
    canvas = RECIPE.canvas[aspect]
    render, audio, final = tmp_path / "render.mp4", tmp_path / "audio.wav", tmp_path / "final.mp4"
    _render(render, RENDER_SIZES[aspect])
    _wav(audio)

    run_finalize(build_finalize_args(render, audio, final, canvas, PAD_COLOR, RECIPE.output))
    profile = probe_output(final)

    assert (profile["width"], profile["height"]) == canvas
    assert profile["video_codec"] == "h264"
    assert profile["pix_fmt"] == "yuv420p"
    assert profile["r_frame_rate"] == "25/1"
    assert profile["audio_codec"] == "aac"
    assert profile["sample_rate"] == 48000
    assert profile["video_duration"] == pytest.approx(SECONDS, abs=0.1)
    assert profile["audio_duration"] == pytest.approx(SECONDS, abs=0.1)
    atoms = _top_level_atoms(final)
    assert atoms.index("moov") < atoms.index("mdat")
    # O canto fica no pad: 9:16 escala para 960x1920 e 16:9 para 1920x960.
    for channel, expected in zip(_pixel(final, 0, 0), PAD_RGB, strict=True):
        assert abs(channel - expected) <= 4
    center = _pixel(final, canvas[0] // 2, canvas[1] // 2)
    assert center[0] > 200 and center[1] < 60 and center[2] < 60
