import ast
import importlib.util
import json
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "apps" / "worker" / "runtimes" / "avatar"
STAGE_PATH = RUNTIME / "avatar_stage.py"
MANIFEST = json.loads((ROOT / "docs" / "models" / "MODEL_MANIFEST.json").read_text())
RECIPE = json.loads((ROOT / "docs" / "models" / "RECIPE-v1.json").read_text())

_spec = importlib.util.spec_from_file_location("avatar_stage", STAGE_PATH)
avatar_stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(avatar_stage)

MODELS = "/models"
PROFILE_480P_FP8 = RECIPE["avatar"]
PROFILE_720P = {
    **RECIPE["avatar"],
    "profile": "720p",
    "size": "infinitetalk-720",
    "quant": None,
    "num_persistent_param_in_dit": None,
}
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


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
def test_args_for_480p_fp8_match_recipe_field_by_field(tmp_path, aspect):
    tag = aspect.replace(":", "x")
    out = tmp_path / "out"

    args = avatar_stage.build_args(_request(tmp_path, aspect, PROFILE_480P_FP8))

    assert args == [
        "--ckpt_dir", "/models/wan2.1-i2v-14b-480p",
        "--wav2vec_dir", "/models/chinese-wav2vec2-base",
        "--infinitetalk_dir", "/models/infinitetalk-weights/single/infinitetalk.safetensors",
        "--quant", "fp8",
        "--quant_dir",
        "/models/infinitetalk-weights/quant_models/infinitetalk_single_fp8.safetensors",
        "--size", "infinitetalk-480",
        "--sample_steps", "40",
        "--mode", "streaming",
        "--motion_frame", "9",
        "--max_frame_num", "1000",
        "--num_persistent_param_in_dit", "0",
        "--input_json", str(out / f"infinitetalk_input_{tag}.json"),
        "--save_file", str(out / f"avatar_{tag}"),
    ]  # fmt: skip


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
def test_args_for_720p_without_quant_omit_quant_and_persistent_params(tmp_path, aspect):
    tag = aspect.replace(":", "x")
    out = tmp_path / "out"

    args = avatar_stage.build_args(_request(tmp_path, aspect, PROFILE_720P))

    assert args == [
        "--ckpt_dir", "/models/wan2.1-i2v-14b-480p",
        "--wav2vec_dir", "/models/chinese-wav2vec2-base",
        "--infinitetalk_dir", "/models/infinitetalk-weights/single/infinitetalk.safetensors",
        "--size", "infinitetalk-720",
        "--sample_steps", "40",
        "--mode", "streaming",
        "--motion_frame", "9",
        "--max_frame_num", "1000",
        "--input_json", str(out / f"infinitetalk_input_{tag}.json"),
        "--save_file", str(out / f"avatar_{tag}"),
    ]  # fmt: skip


@pytest.mark.parametrize("avatar", [PROFILE_480P_FP8, PROFILE_720P])
@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
def test_every_path_arg_is_under_models_or_out_dir(tmp_path, aspect, avatar):
    request = _request(tmp_path, aspect, avatar)
    roots = (Path(MODELS), Path(request["out_dir"]))

    args = avatar_stage.build_args(request)

    paths = [Path(value) for value in args if value.startswith("/")]
    assert len(paths) >= 5
    for path in paths:
        assert any(path.is_relative_to(root) for root in roots), path
        assert ".." not in path.parts


def test_weight_paths_exist_in_manifest():
    files = {
        f"{component['id']}/{item['path']}"
        for component in MANIFEST["components"]
        for item in component["files"]
    }
    ids = {component["id"] for component in MANIFEST["components"]}
    quant_dir = avatar_stage.QUANT_WEIGHTS.format(quant="fp8")

    assert {avatar_stage.WAN_DIR, avatar_stage.WAV2VEC_DIR} <= ids
    assert avatar_stage.INFINITETALK_WEIGHTS in files
    assert quant_dir in files
    assert quant_dir.replace("safetensors", "json") in files
    t5_dir = quant_dir.rsplit("/", 1)[0]
    assert {f"{t5_dir}/t5_fp8.safetensors", f"{t5_dir}/t5_map_fp8.json"} <= files


def test_run_writes_input_json_runs_offline_without_shell_and_writes_result(tmp_path, spy_run):
    request = _request(tmp_path, "9:16")
    request_path = _write_request(tmp_path, request)
    result_path = tmp_path / "result.json"
    out = tmp_path / "out"

    assert avatar_stage.main([str(request_path), str(result_path)]) == 0

    input_json = json.loads((out / "infinitetalk_input_9x16.json").read_text())
    assert input_json == {
        "prompt": RECIPE["avatar"]["prompt"],
        "cond_video": request["image"],
        "cond_audio": {"person1": request["audio"]},
    }
    render_cmd, render_kwargs = spy_run[0]
    assert render_cmd[:2] == [
        sys.executable,
        str(tmp_path / "infinitetalk" / "generate_infinitetalk.py"),
    ]
    assert render_cmd[2:] == avatar_stage.build_args(request)
    assert render_kwargs["shell"] is False
    assert all(kwargs.get("shell") is False for _, kwargs in spy_run)

    call = json.loads((out / "fake_call.json").read_text())
    assert call["env"] == {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    assert Path(call["cwd"]).resolve() == out.resolve()
    assert call["input"] == input_json

    result = json.loads(result_path.read_text())
    assert set(result) == RESULT_FIELDS
    assert result["video_path"] == str(out / "avatar_9x16.mp4")
    assert (result["native_width"], result["native_height"]) == (448, 832)
    assert result["frames"] == 30
    assert isinstance(result["elapsed_s"], float) and result["elapsed_s"] >= 0


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


@pytest.mark.parametrize(
    ("package_name", "component_id"),
    [("flash-attn", "flash-attn-wheel"), ("xformers", "xformers-wheel")],
)
def test_wheel_url_and_sha256_in_lock_match_manifest(package_name, component_id):
    lock = tomllib.loads((RUNTIME / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == package_name)
    component = next(c for c in MANIFEST["components"] if c["id"] == component_id)
    (expected,) = component["files"]

    assert package["version"] == component["revision"]
    assert package["source"] == {"url": expected["url"]}
    (wheel,) = package["wheels"]
    assert wheel["url"] == expected["url"]
    assert wheel["hash"] == f"sha256:{expected['sha256']}"


def test_lock_has_torch_241_cu121_for_linux_x86_64():
    lock = tomllib.loads((RUNTIME / "uv.lock").read_text())
    versions = {p["name"]: p["version"] for p in lock["package"]}

    assert versions["torch"] == "2.4.1+cu121"
    assert versions["torchvision"] == "0.19.1+cu121"
    assert versions["torchaudio"] == "2.4.1+cu121"
    assert lock["requires-python"] == "==3.10.*"


def test_stage_module_is_stdlib_only_and_python_310_syntax():
    source = STAGE_PATH.read_text()
    tree = ast.parse(source, feature_version=(3, 10))
    modules = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module.split(".")[0])
    assert modules <= sys.stdlib_module_names
