"""Dobles de inferência só nos subprocessos de teste; imagens/WAV/MP4/FFmpeg são reais."""

import copy
import hashlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from PIL import Image

from avatar_worker import video
from avatar_worker.finalize import probe_output
from avatar_worker.video import GenerationFailure, VideoRuntime, generate_video

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs/models/MODEL_MANIFEST.json"

TTS_FIXTURE = """
import fcntl, json, os, pathlib, sys, wave
request = json.loads(pathlib.Path(sys.argv[1]).read_text())
if os.environ.get('TEST_TTS_OOM'):
    print('CUDA out of memory', file=sys.stderr)
    sys.exit(1)
with open(pathlib.Path(request['out_wav']).parent / 'tts.lock', 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    with wave.open(request['out_wav'], 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        frames = round(float(os.environ.get('TEST_AUDIO_SECONDS', '1.2')) * 24000)
        wav.writeframes(b'\\x10\\x00' * frames)
    pathlib.Path(sys.argv[2]).write_text(json.dumps({'audio_path': request['out_wav']}))
"""

AVATAR_FIXTURE = """
import fcntl, json, os, pathlib, subprocess, sys, wave
request = json.loads(pathlib.Path(sys.argv[1]).read_text())
with open(pathlib.Path(request['out_dir']) / 'tts.lock') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
with wave.open(request['audio']) as wav:
    duration = wav.getnframes() / wav.getframerate()
case = os.environ.get('TEST_RENDER_CASE', '')
if case == 'short': duration = 0.2
size = {'9:16': '448:832', '16:9': '896:448'}[request['format']]
if case == 'crop': size = '256:256'
path = pathlib.Path(request['out_dir']) / 'native.mp4'
if case == 'escape': path = path.parent.parent / 'outside.mp4'
if case == 'invalid':
    path.write_bytes(b'incomplete mp4')
else:
    subprocess.run(['ffmpeg', '-v', 'error', '-y',
                    '-loop', '1', '-i', request['image'], '-vf', 'scale=' + size,
                    '-t', str(duration), '-r', '25', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(path)], check=True)
pathlib.Path(sys.argv[2]).write_text(json.dumps({'video_path': str(path)}))
"""


@pytest.fixture
def video_case(tmp_path):
    raw = json.loads((ROOT / "docs/models/RECIPE-v1.json").read_text())
    raw["status"] = "frozen"
    raw["worker_image"]["digest"] = "sha256:" + "b" * 64
    # Metadados sintéticos isolados, nunca uma receita real carregada no cliente.
    measurement = {
        "audio_seconds": 1.2,
        "stages": {s: {"seconds": 1, "vram_peak_mb": 0} for s in ("tts", "render", "finalize")},
        "seconds_per_video_second": {"cold": 1, "warm": 1},
    }
    raw["pilot"] = {
        "formats": {aspect: copy.deepcopy(measurement) for aspect in ("9:16", "16:9")},
        "approved_max_audio_seconds": raw["limits"]["max_audio_seconds"],
        "evaluation": {"verdict": "aprovado", "evaluator": "test-only"},
    }
    payload = {
        "recipe_id": "isolated-test-recipe",
        "recipe_spec": raw,
        "aspect_ratio": "9:16",
        "voice": "feminina",
        "script_text": "Teste de geração local.",
        "background_color": "#1f2937",
        "composition": {a: {"scale": 0.5, "x": 0.5, "y": 0.9} for a in ("9:16", "16:9")},
    }
    image = tmp_path / "avatar.png"
    Image.new("RGBA", (80, 160), (230, 50, 20, 255)).save(image)
    tts, avatar = tmp_path / "tts.py", tmp_path / "avatar.py"
    tts.write_text(textwrap.dedent(TTS_FIXTURE))
    avatar.write_text(textwrap.dedent(AVATAR_FIXTURE))
    runtime = VideoRuntime(
        models_dir=tmp_path / "models",
        manifest_path=MANIFEST,
        tts_python=Path(sys.executable),
        avatar_python=Path(sys.executable),
        tts_script=tts,
        avatar_script=avatar,
    )
    return payload, {"avatar": image}, tmp_path / "attempt", runtime


def generate(case):
    return generate_video(*case, lambda: None, lambda stage: None)


@pytest.mark.parametrize(
    "aspect,size,native",
    [
        ("9:16", (1080, 1920), (448, 832)),
        ("16:9", (1920, 1080), (896, 448)),
    ],
)
def test_pipeline_preserves_canvas_audio_and_manifest_of_real_files(
    video_case, aspect, size, native
):
    payload, inputs, work, runtime = video_case
    payload["aspect_ratio"] = aspect

    result = generate(video_case)

    profile = probe_output(result.files["final.mp4"])
    assert (profile["width"], profile["height"]) == size
    assert (profile["video_codec"], profile["pix_fmt"], profile["r_frame_rate"]) == (
        "h264",
        "yuv420p",
        "25/1",
    )
    assert (profile["audio_codec"], profile["sample_rate"]) == ("aac", 48000)
    assert abs(profile["audio_duration"] - 1.2) < 0.08
    assert abs(profile["video_duration"] - 1.2) < 0.08
    manifest = json.loads(result.files["manifest.json"].read_text())
    assert (manifest["native"]["width"], manifest["native"]["height"]) == native
    assert manifest["audio_seconds"] == 1.2
    for name in ("audio.wav", "render.mp4", "final.mp4"):
        assert (
            hashlib.sha256(result.files[name].read_bytes()).hexdigest() == manifest["files"][name]
        )
    decoded = work / "decoded.png"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(result.files["final.mp4"]),
            "-frames:v",
            "1",
            str(decoded),
        ],
        check=True,
    )
    with Image.open(decoded) as frame:
        for point, expected in [
            ((0, 0), (31, 41, 55)),
            ((size[0] // 2, round(size[1] * 0.7)), (230, 50, 20)),
        ]:
            assert all(
                abs(a - b) <= 8 for a, b in zip(frame.getpixel(point), expected, strict=True)
            )


def test_real_audio_over_limit_stops_before_render_even_if_adapter_omits_duration(
    video_case, monkeypatch
):
    monkeypatch.setenv("TEST_AUDIO_SECONDS", "40.1")
    with pytest.raises(GenerationFailure) as failure:
        generate(video_case)
    assert failure.value.code == "INPUT_INVALID"
    assert failure.value.retryable is False
    assert not (video_case[2] / "native.mp4").exists()
    assert not (video_case[2] / "final.mp4").exists()


@pytest.mark.parametrize("case", ["escape", "short", "crop", "invalid"])
def test_invalid_native_render_never_reaches_export(video_case, monkeypatch, case):
    monkeypatch.setenv("TEST_RENDER_CASE", case)
    with pytest.raises(GenerationFailure) as failure:
        generate(video_case)
    assert failure.value.code == "OUTPUT_INVALID"
    assert not (video_case[2] / "final.mp4").exists()


def test_draft_recipe_never_executes_a_stage(video_case):
    video_case[0]["recipe_spec"]["status"] = "draft"
    with pytest.raises(GenerationFailure) as failure:
        generate(video_case)
    assert failure.value.code == "INPUT_INVALID"
    assert not video_case[2].exists()


def test_runtime_oom_is_permanent_and_diagnostic_is_not_returned(video_case, monkeypatch):
    monkeypatch.setenv("TEST_TTS_OOM", "1")
    with pytest.raises(GenerationFailure) as failure:
        generate(video_case)
    assert failure.value.code == "OUT_OF_MEMORY"
    assert failure.value.retryable is False
    assert "CUDA" not in failure.value.message
    assert not (video_case[2] / "final.mp4").exists()


def test_finalizer_output_with_wrong_frame_rate_is_refused(video_case, monkeypatch):
    real_run = video.run_process

    def generate_wrong_rate(argv, *args, **kwargs):
        if argv[0] == "ffmpeg":
            # Falha de fronteira: FFmpeg real exporta perfil incorreto, sem mock de saída.
            argv = [*argv[:-1], "-r", "24", argv[-1]]
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(video, "run_process", generate_wrong_rate)
    with pytest.raises(GenerationFailure) as failure:
        generate(video_case)
    assert failure.value.code == "OUTPUT_INVALID"
    assert probe_output(video_case[2] / "final.mp4")["r_frame_rate"] == "24/1"
