import hashlib
import json
import shlex
import sys
import textwrap
from pathlib import Path

import pytest
from PIL import Image

from avatar_worker import pilot

ROOT = Path(__file__).resolve().parents[3]
RECIPE_PATH = ROOT / "docs" / "models" / "RECIPE-v1.json"
MANIFEST_PATH = ROOT / "docs" / "models" / "MODEL_MANIFEST.json"
COMPOSITION = {
    "9:16": {"scale": 0.8, "x": 0.5, "y": 1.0},
    "16:9": {"scale": 0.9, "x": 0.5, "y": 1.0},
}
TEXT = "Olá, eu sou a Mariana Albuquerque. Ligue para 0800 721 4400 até 15 de março de 2027."
STAGES = ["compose", "tts", "avatar", "finalize"]
CANVAS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
BUCKETS = {"9:16": [448, 832], "16:9": [896, 448]}

# Runtimes falsos: recebem <stage.py> <request.json> <result.json> como o Python do runtime.
# Registram início e fim em PILOT_LOG e sobem a VRAM falsa em PILOT_VRAM durante o trabalho.
FAKE_COMMON = """
import json, os, subprocess, sys, time, wave
_, request_path, result_path = sys.argv[1:]
request = json.load(open(request_path, encoding="utf-8"))
def event(name):
    with open(os.environ["PILOT_LOG"], "a") as log:
        log.write(name + "\\n")
def vram(value):
    with open(os.environ["PILOT_VRAM"], "w") as out:
        out.write(value)
"""

FAKE_TTS = """
event("tts:start")
vram("3000")
time.sleep(0.3)
seconds = float(os.environ.get("FAKE_TTS_SECONDS", "1.0"))
with wave.open(request["out_wav"], "wb") as out:
    out.setnchannels(1)
    out.setsampwidth(2)
    out.setframerate(24000)
    out.writeframes(b"\\0\\0" * int(24000 * seconds))
vram("100")
result = {"audio_path": request["out_wav"], "duration_s": seconds, "sample_rate": 24000,
          "peak_vram_mb": 2500.0, "watermark_detected": True, "elapsed_s": 0.3}
json.dump(result, open(result_path, "w"))
event("tts:end")
"""

FAKE_AVATAR = """
event("avatar:start")
if not os.path.isfile(request["audio"]):
    sys.exit(5)
if os.environ.get("FAKE_AVATAR_EXIT"):
    sys.exit(int(os.environ["FAKE_AVATAR_EXIT"]))
vram("7000")
time.sleep(0.3)
width, height = {"9:16": (448, 832), "16:9": (896, 448)}[request["format"]]
out_dir = request["out_dir"]
os.makedirs(os.path.join(out_dir, "save_audio", "canvas"), exist_ok=True)
video = os.path.join(out_dir, "avatar_" + request["format"].replace(":", "x") + ".mp4")
subprocess.run(
    ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={width}x{height}:r=25",
     "-frames:v", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p", video],
    check=True,
)
vram("100")
result = {"video_path": video, "native_width": width, "native_height": height, "frames": 25,
          "elapsed_s": 0.3}
json.dump(result, open(result_path, "w"))
event("avatar:end")
"""


def _script(path, body):
    path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(FAKE_COMMON) + body)
    path.chmod(0o755)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    log = tmp_path / "events.log"
    vram = tmp_path / "vram.txt"
    vram.write_text("100")
    net = tmp_path / "net"
    (net / "lo").mkdir(parents=True)
    monkeypatch.setenv("PILOT_LOG", str(log))
    monkeypatch.setenv("PILOT_VRAM", str(vram))
    monkeypatch.setenv("WORKER_IMAGE_DIGEST", "sha256:" + "a" * 64)
    monkeypatch.setattr(pilot, "VRAM_INTERVAL_S", 0.05)
    monkeypatch.setattr(pilot, "NET_DIR", net)

    avatar = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    avatar.paste((200, 150, 120, 255), (100, 100, 300, 800))
    image = tmp_path / "avatar.png"
    avatar.save(image)
    text_file = tmp_path / "fala.txt"
    text_file.write_text(TEXT + "\n", encoding="utf-8")
    vram_command = shlex.join(
        [sys.executable, "-c", "import sys; print(open(sys.argv[1]).read())", str(vram)]
    )
    args = [
        "--recipe", str(RECIPE_PATH),
        "--manifest", str(MANIFEST_PATH),
        "--models", str(tmp_path / "models"),
        "--image", str(image),
        "--background", "#1f2937",
        "--composition", json.dumps(COMPOSITION),
        "--text-file", str(text_file),
        "--voice", "feminina",
        "--out", str(tmp_path / "out"),
        "--tts-python", str(_script(tmp_path / "fake-tts-python", FAKE_TTS)),
        "--avatar-python", str(_script(tmp_path / "fake-avatar-python", FAKE_AVATAR)),
        "--infinitetalk-dir", str(tmp_path / "infinitetalk"),
        "--vram-command", vram_command,
    ]  # fmt: skip
    return {"args": args, "log": log, "out": tmp_path / "out"}


def _report(out):
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def _events(log):
    return log.read_text().split() if log.exists() else []


def test_report_has_both_formats_with_stage_times_vram_peaks_and_hashes(env):
    assert pilot.main([*env["args"], "--formats", "9:16,16:9", "--runs", "2"]) == 0

    report = _report(env["out"])
    assert report["status"] == "ok"
    assert report["error"] is None
    assert report["recipe_sha256"] == hashlib.sha256(RECIPE_PATH.read_bytes()).hexdigest()
    assert report["worker_image"] == "sha256:" + "a" * 64
    assert report["network_interfaces"] == ["lo"]
    assert report["text"] == {
        "sha256": hashlib.sha256(TEXT.encode("utf-8")).hexdigest(),
        "chars": len(TEXT),
    }
    assert report["limits"] == {
        "max_audio_seconds": 40,
        "recipe_max_audio_seconds": 40,
        "max_frame_num": 1000,
    }
    assert report["cutout"]["cutout"]["seconds"] >= 0
    assert list(report["formats"]) == ["9:16", "16:9"]

    for aspect, summary in report["formats"].items():
        assert summary["canvas"] == list(CANVAS[aspect])
        assert summary["bucket"] == BUCKETS[aspect]
        assert [run["load"] for run in summary["runs"]] == ["cold", "warm"]
        assert summary["seconds_per_video_second"]["cold"] > 0
        assert summary["seconds_per_video_second"]["warm"] > 0
        for run in summary["runs"]:
            stages = run["stages"]
            assert list(stages) == STAGES
            assert all(stage["seconds"] > 0 for stage in stages.values())
            assert stages["compose"]["vram_peak_mb"] == 100
            assert stages["tts"]["vram_peak_mb"] == 3000
            assert stages["tts"]["runtime_peak_vram_mb"] == 2500.0
            assert stages["avatar"]["vram_peak_mb"] == 7000
            assert stages["finalize"]["vram_peak_mb"] == 100
            assert run["audio_seconds"] == 1.0
            assert run["watermark_detected"] is True
            assert [run["native_width"], run["native_height"]] == BUCKETS[aspect]
            assert run["frames"] == 25
            final = Path(run["final_path"])
            assert final.name == "final.mp4"
            assert run["final_sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
            assert (run["final"]["width"], run["final"]["height"]) == CANVAS[aspect]
            assert run["final"]["pix_fmt"] == "yuv420p"
            assert run["final"]["sample_rate"] == 48000
            assert run["seconds_per_video_second"] > 0
            assert not (final.parent / "save_audio").exists()

    # Cada execução termina o TTS antes de o render começar.
    assert _events(env["log"]) == ["tts:start", "tts:end", "avatar:start", "avatar:end"] * 4


def test_runtimes_receive_literal_text_voice_canvas_and_recipe(env):
    assert pilot.main([*env["args"], "--formats", "16:9"]) == 0

    run_dir = env["out"] / "16x9" / "run-1"
    tts = json.loads((run_dir / "tts_request.json").read_text(encoding="utf-8"))
    assert tts["text"] == TEXT
    assert tts["language"] == "pt"
    assert tts["voice"] == {"kind": "default"}
    avatar = json.loads((run_dir / "avatar_request.json").read_text(encoding="utf-8"))
    assert avatar["format"] == "16:9"
    assert avatar["audio"] == tts["out_wav"]
    assert avatar["recipe_avatar"]["max_frame_num"] == 1000
    assert avatar["recipe_avatar"]["quant"] == "fp8"
    with Image.open(avatar["image"]) as canvas:
        assert canvas.size == CANVAS["16:9"]


def test_failed_render_writes_error_and_exits_1_without_final(env, monkeypatch):
    monkeypatch.setenv("FAKE_AVATAR_EXIT", "3")

    assert pilot.main([*env["args"], "--formats", "9:16,16:9"]) == 1

    report = _report(env["out"])
    assert report["status"] == "failed"
    assert report["error"]["stage"] == "avatar"
    assert report["error"]["format"] == "9:16"
    assert report["error"]["run"] == 1
    assert "código 3" in report["error"]["message"]
    (run,) = report["formats"]["9:16"]["runs"]
    assert list(run["stages"]) == ["compose", "tts", "avatar"]
    assert "16:9" not in report["formats"]
    assert list(env["out"].rglob("final.mp4")) == []


def test_audio_above_limit_fails_tts_before_render(env, monkeypatch):
    monkeypatch.setenv("FAKE_TTS_SECONDS", "1.0")

    assert pilot.main([*env["args"], "--formats", "9:16", "--max-audio-seconds", "0.5"]) == 1

    report = _report(env["out"])
    assert report["limits"]["max_audio_seconds"] == 0.5
    assert report["limits"]["max_frame_num"] == 13
    assert report["error"]["stage"] == "tts"
    assert "limite" in report["error"]["message"]
    assert _events(env["log"]) == ["tts:start", "tts:end"]
    assert list(env["out"].rglob("final.mp4")) == []


def test_composition_without_requested_format_is_rejected(env):
    args = [*env["args"], "--composition", json.dumps({"9:16": COMPOSITION["9:16"]})]
    with pytest.raises(SystemExit) as exc:
        pilot.main([*args, "--formats", "9:16,16:9"])
    assert exc.value.code == 2
    assert _events(env["log"]) == []


def test_pad_color_is_scene_color_or_mean_of_background_image():
    assert pilot._pad_color("#1f2937") == "#1f2937"
    assert pilot._pad_color(Image.new("RGB", (8, 8), (10, 20, 30))) == "#0a141e"
