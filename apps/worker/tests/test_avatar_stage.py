import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "apps" / "worker" / "runtimes" / "avatar"
STAGE_PATH = RUNTIME / "avatar_stage.py"
PATCH_SCRIPT = RUNTIME / "patch_infinitetalk.py"
RECIPE = json.loads((ROOT / "docs" / "models" / "RECIPE-v1.json").read_text())

_spec = importlib.util.spec_from_file_location("avatar_stage", STAGE_PATH)
avatar_stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(avatar_stage)

DRAFT_AVATAR = RECIPE["avatar"]
LORA = DRAFT_AVATAR["lora"]
LORA_BYTES = b"lora sintetica de teste"
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
        "env": {
            k: os.environ.get(k)
            for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "TORCHDYNAMO_DISABLE")
        },
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


def _request(tmp_path, aspect="9:16", models_dir=None):
    """Pedido com o avatar do draft; a LoRA é um arquivo sintético com o sha256 do pedido."""
    lora_file = tmp_path / "models" / LORA["component"] / LORA["file"]
    lora_file.parent.mkdir(parents=True, exist_ok=True)
    lora_file.write_bytes(LORA_BYTES)
    avatar = copy.deepcopy(DRAFT_AVATAR)
    avatar["lora"]["sha256"] = hashlib.sha256(LORA_BYTES).hexdigest()
    return {
        "image": str(tmp_path / "out" / "canvas.png"),
        "audio": str(tmp_path / "out" / "speech.wav"),
        "format": aspect,
        "models_dir": str(tmp_path / "models") if models_dir is None else models_dir,
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


def test_render_produces_native_video_with_offline_environment(tmp_path, monkeypatch):
    # Ambiente pai em 0: o gerador ainda recebe os valores que o estágio força.
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "TORCHDYNAMO_DISABLE"):
        monkeypatch.setenv(name, "0")
    request = _request(tmp_path, "9:16")
    request_path = _write_request(tmp_path, request)
    result_path = tmp_path / "result.json"
    out = tmp_path / "out"

    assert avatar_stage.main([str(request_path), str(result_path)]) == 0


    call = json.loads((out / "fake_call.json").read_text())
    # TORCHDYNAMO_DISABLE: o @torch.compile do InfiniteTalk exige compilador C, ausente na imagem.
    assert call["env"] == {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TORCHDYNAMO_DISABLE": "1",
    }
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
    # Os pesos vêm de models/ relativo ao cwd; _request grava a LoRA sintética lá.
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


@pytest.mark.parametrize("lora", [True, False], ids=["draft-com-lora", "perfil-declarado-sem-lora"])
def test_generator_receives_recipe_lora_steps_and_guides_explicitly(tmp_path, lora):
    request = _request(tmp_path)
    if not lora:
        request["recipe_avatar"]["lora"] = None
    request_path = _write_request(tmp_path, request)

    assert avatar_stage.main([str(request_path), str(tmp_path / "result.json")]) == 0

    argv = json.loads((tmp_path / "out" / "fake_call.json").read_text())["argv"]
    opts = dict(zip(argv[::2], argv[1::2], strict=True))
    # Os defaults do CLI fixado (40 passos, guias 5.0/4.0, LoRA 1.2) nunca valem.
    assert opts["--sample_steps"] == str(DRAFT_AVATAR["sample_steps"])
    assert opts["--sample_text_guide_scale"] == str(DRAFT_AVATAR["sample_text_guide_scale"])
    assert opts["--sample_audio_guide_scale"] == str(DRAFT_AVATAR["sample_audio_guide_scale"])
    assert "--quant" not in opts
    if lora:
        lora_file = tmp_path / "models" / LORA["component"] / LORA["file"]
        assert opts["--lora_dir"] == str(lora_file.resolve())
        assert opts["--lora_scale"] == str(LORA["scale"])
    else:
        assert "--lora_dir" not in opts
        assert "--lora_scale" not in opts


@pytest.mark.parametrize("declared", [True, False], ids=["declarados", "omitidos"])
def test_seed_shift_and_color_reach_generator_only_when_declared(tmp_path, declared):
    request = _request(tmp_path)
    if declared:
        request["recipe_avatar"].update(
            base_seed=37, sample_shift=5.0, color_correction_strength=0.0
        )
    request_path = _write_request(tmp_path, request)

    assert avatar_stage.main([str(request_path), str(tmp_path / "result.json")]) == 0

    argv = json.loads((tmp_path / "out" / "fake_call.json").read_text())["argv"]
    opts = dict(zip(argv[::2], argv[1::2], strict=True))
    if declared:
        # Cor 0.0 desliga a correção; retake com outra seed muda o vídeo.
        assert opts["--base_seed"] == "37"
        assert opts["--sample_shift"] == "5.0"
        assert opts["--color_correction_strength"] == "0.0"
    else:
        assert not {"--base_seed", "--sample_shift", "--color_correction_strength"} & set(opts)


def _avatar(**changes):
    return lambda request: request["recipe_avatar"].update(changes)


def _lora(**changes):
    return lambda request: request["recipe_avatar"]["lora"].update(changes)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda request: request.update(format="4:3"), "request.format"),
        (lambda request: request.update(models_dir=""), "request.models_dir"),
        (_avatar(size=None), "request.recipe_avatar sem size"),
        (lambda request: request.update(recipe_avatar=None), "recipe_avatar precisa ser um objeto"),
        (_avatar(quant="fp8"), "extensão CUDA do optimum-quanto na primeira inferência e a imagem"),
        (_avatar(negative_prompt="mãos, gestos"), "generate_infinitetalk.py fixado (50aa0a94)"),
        (_avatar(sample_steps=0), "sample_steps precisa ser inteiro positivo"),
        (_avatar(sample_text_guide_scale=float("inf")), "sample_text_guide_scale precisa ser"),
        (_avatar(sample_audio_guide_scale=0), "sample_audio_guide_scale precisa ser"),
        (_avatar(base_seed=-1), "base_seed precisa ser inteiro não negativo"),
        (_avatar(base_seed=4.2), "base_seed precisa ser inteiro não negativo"),
        (_avatar(sample_shift=0), "sample_shift precisa ser número finito e positivo"),
        (_avatar(color_correction_strength=1.5), "color_correction_strength precisa estar"),
        (lambda request: request["recipe_avatar"].pop("lora"), "recipe_avatar sem lora"),
        (_lora(scale=-1.0), "lora.scale precisa ser número finito e positivo"),
        (_lora(file="../../fora.safetensors"), "recipe_avatar.lora fora de models_dir"),
        (_lora(file="ausente.safetensors"), "LoRA ausente"),
        (_lora(sha256="0" * 64), "sha256 da LoRA"),
    ],
)
def test_invalid_request_exits_1_before_render(tmp_path, spy_run, capsys, mutate, expected):
    request = _request(tmp_path)
    mutate(request)
    request_path = _write_request(tmp_path, request)
    result_path = tmp_path / "result.json"

    assert avatar_stage.main([str(request_path), str(result_path)]) == 1

    assert spy_run == []
    assert not result_path.exists()
    assert expected in capsys.readouterr().err


# custom_init de generate_infinitetalk.py no commit 50aa0a94 do manifesto (linhas 277-281),
# byte a byte. O Wav2Vec2FeatureExtractor recebe os mesmos argumentos do encoder.
CUSTOM_INIT = (
    "def custom_init(device, wav2vec):    \n"
    "    audio_encoder = Wav2Vec2Model.from_pretrained(wav2vec, local_files_only=True).to(device)\n"
    "    audio_encoder.feature_extractor._freeze_parameters()\n"
    "    wav2vec_feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained("
    "wav2vec, local_files_only=True)\n"
    "    return wav2vec_feature_extractor, audio_encoder\n"
)
# O mesmo trecho depois do patch: só o carregamento do encoder ganha atenção eager.
EAGER_CUSTOM_INIT = (
    "def custom_init(device, wav2vec):    \n"
    "    audio_encoder = Wav2Vec2Model.from_pretrained("
    'wav2vec, local_files_only=True, attn_implementation="eager").to(device)\n'
    "    audio_encoder.feature_extractor._freeze_parameters()\n"
    "    wav2vec_feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained("
    "wav2vec, local_files_only=True)\n"
    "    return wav2vec_feature_extractor, audio_encoder\n"
)


def _patch_checkout(tmp_path, source):
    """Roda o script como o Dockerfile, sobre um checkout com generate_infinitetalk.py."""
    checkout = tmp_path / "infinitetalk"
    checkout.mkdir()
    (checkout / "generate_infinitetalk.py").write_text(source)
    completed = subprocess.run(
        [sys.executable, str(PATCH_SCRIPT), str(checkout)],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, (checkout / "generate_infinitetalk.py").read_text()


def test_patch_loads_only_the_wav2vec2_encoder_with_eager_attention(tmp_path):
    completed, patched = _patch_checkout(tmp_path, CUSTOM_INIT)

    assert completed.returncode == 0, completed.stderr
    assert patched == EAGER_CUSTOM_INIT


@pytest.mark.parametrize(
    ("source", "found"),
    [(EAGER_CUSTOM_INIT, 0), (CUSTOM_INIT + CUSTOM_INIT, 2)],
    ids=["ancora-ausente", "ancora-repetida"],
)
def test_patch_fails_without_touching_checkout_unless_anchor_appears_once(tmp_path, source, found):
    completed, patched = _patch_checkout(tmp_path, source)

    assert completed.returncode == 1
    assert f"encontradas {found}" in completed.stderr
    assert patched == source
