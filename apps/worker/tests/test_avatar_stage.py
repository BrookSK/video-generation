import importlib.util
import json
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "apps" / "worker" / "runtimes" / "avatar"
STAGE_PATH = RUNTIME / "avatar_stage.py"
RECIPE = json.loads((ROOT / "docs" / "models" / "RECIPE-v1.json").read_text())

_spec = importlib.util.spec_from_file_location("avatar_stage", STAGE_PATH)
avatar_stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(avatar_stage)

MODELS = "/models"
PROFILE_480P_FP8 = RECIPE["avatar"]
RESULT_FIELDS = {"video_path", "native_width", "native_height", "frames", "elapsed_s"}

# generate_infinitetalk.py falso: registra argv, cwd e ambiente e grava <save_file>.mp4
# no tamanho do bucket com o FFmpeg real.
FAKE_GENERATE = textwrap.dedent(
    """
    import json, os, subprocess, sys
    args = sys.argv[1:]
    opts = dict(zip(args[::2], args[1::2]))
    record = {
        "argv": args,
        "cwd": os.getcwd(),
        "env": {k: os.environ.get(k) for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")},
        "input": json.load(open(opts["--input_json"], encoding="utf-8")),
    }
    json.dump(record, open(os.path.join(os.getcwd(), "fake_call.json"), "w"))
    if os.environ.get("FAKE_EXIT"):
        sys.exit(int(os.environ["FAKE_EXIT"]))
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=448x832:r=25",
         "-frames:v", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", opts["--save_file"] + ".mp4"],
        check=True,
    )
    """
)


def _request(tmp_path, aspect="9:16", avatar=PROFILE_480P_FP8, models_dir=MODELS):
    return {
        "image": str(tmp_path / "out" / "canvas.png"),
        "audio": str(tmp_path / "out" / "speech.wav"),
        "format": aspect,
        "models_dir": models_dir,
        "infinitetalk_dir": str(tmp_path / "infinitetalk"),
        "out_dir": str(tmp_path / "out"),
        "recipe_avatar": avatar,
    }


def _write_request(tmp_path, request):
    fake = tmp_path / "infinitetalk" / "generate_infinitetalk.py"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_text(FAKE_GENERATE)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def spy_run(monkeypatch):
    calls = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        calls.append((cmd, kwargs))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(avatar_stage.subprocess, "run", spy)
    return calls


def test_render_produces_native_video_with_offline_environment(tmp_path):
    request = _request(tmp_path, "9:16")
    request_path = _write_request(tmp_path, request)
    result_path = tmp_path / "result.json"
    out = tmp_path / "out"

    assert avatar_stage.main([str(request_path), str(result_path)]) == 0


    call = json.loads((out / "fake_call.json").read_text())
    assert call["env"] == {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    assert Path(call["cwd"]).resolve() == out.resolve()

    result = json.loads(result_path.read_text())
    assert set(result) == RESULT_FIELDS
    assert result["video_path"] == str(out / "avatar_9x16.mp4")
    assert (result["native_width"], result["native_height"]) == (448, 832)
    assert result["frames"] == 30
    assert isinstance(result["elapsed_s"], float) and result["elapsed_s"] >= 0


def test_relative_paths_survive_generator_working_directory(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    Image.new("RGB", (448, 832), "#204080").save(out / "canvas.png")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=1.2", str(out / "speech.wav")],
        check=True,
    )
    (tmp_path / "models").mkdir()
    request = _request(tmp_path, models_dir="models")
    for key in ("image", "audio", "infinitetalk_dir", "out_dir"):
        request[key] = str(Path(request[key]).relative_to(tmp_path))
    request_path = _write_request(tmp_path, request)
    # Fronteira de teste: abre os inputs que o upstream abre depois de trocar cwd.
    # FFmpeg consome a imagem e o áudio reais; não há pesos nem inferência nesta fixture.
    (tmp_path / "infinitetalk" / "generate_infinitetalk.py").write_text(textwrap.dedent(
        """
        import json, pathlib, subprocess, sys
        opts = dict(zip(sys.argv[1::2], sys.argv[2::2]))
        assert pathlib.Path(opts["--ckpt_dir"]).parent.is_dir()
        inputs = json.loads(pathlib.Path(opts["--input_json"]).read_text())
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", inputs["cond_video"],
             "-i", inputs["cond_audio"]["person1"], "-t", "1.2", "-r", "25",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             opts["--save_file"] + ".mp4"],
            check=True,
        )
        pathlib.Path("save_audio").mkdir()
        """
    ))

    assert avatar_stage.main([str(request_path.relative_to(tmp_path)), "result.json"]) == 0
    result = json.loads((tmp_path / "result.json").read_text())
    video = Path(result["video_path"])
    assert video.is_file()
    assert (result["native_width"], result["native_height"], result["frames"]) == (448, 832, 30)
    decoded = out / "decoded.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-frames:v", "1", str(decoded)],
        check=True,
    )
    with Image.open(decoded) as frame:
        assert all(
            abs(a - b) <= 5
            for a, b in zip(frame.getpixel((224, 416)), (32, 64, 128), strict=True)
        )
    assert (out / "save_audio").is_dir()
    assert not (tmp_path / "save_audio").exists()


def test_failed_render_exits_1_without_result(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_EXIT", "3")
    request_path = _write_request(tmp_path, _request(tmp_path))
    result_path = tmp_path / "result.json"

    assert avatar_stage.main([str(request_path), str(result_path)]) == 1

    assert not result_path.exists()
    assert "saiu com código 3" in capsys.readouterr().err


@pytest.mark.parametrize(
    "change",
    [
        {"format": "4:3"},
        {"models_dir": ""},
        {"recipe_avatar": {**PROFILE_480P_FP8, "size": None}},
        {"recipe_avatar": None},
    ],
)
def test_invalid_request_exits_1_before_render(tmp_path, spy_run, change):
    request_path = _write_request(tmp_path, {**_request(tmp_path), **change})
    result_path = tmp_path / "result.json"

    assert avatar_stage.main([str(request_path), str(result_path)]) == 1

    assert spy_run == []
    assert not result_path.exists()


