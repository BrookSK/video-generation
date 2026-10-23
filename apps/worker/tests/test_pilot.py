import hashlib
import json
import shlex
import sys
import textwrap
from pathlib import Path

import pytest
from PIL import Image

from avatar_worker import pilot
from avatar_worker.canvas import background_pad_color, compose_canvas

ROOT = Path(__file__).resolve().parents[3]
RECIPE_PATH = ROOT / "docs" / "models" / "RECIPE-v1.json"
MANIFEST_PATH = ROOT / "docs" / "models" / "MODEL_MANIFEST.json"
RECIPE = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
# Diferente de calibration.composition da receita, para a precedência aparecer no canvas.
COMPOSITION = {"scale": 0.6, "x": 0.4, "y": 0.9}
TEXT = "Olá, eu sou a Mariana Albuquerque. Ligue para 0800 721 4400 até 15 de março de 2027."
STAGES = ["compose", "tts", "avatar", "finalize"]
CANVAS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
BUCKETS = {"9:16": [448, 832], "16:9": [896, 448]}
RENDER_INPUT = {
    "9:16": {"size": [1092, 2028], "canvas_offset": [6, 54], "canvas_cut_px": 0},
    "16:9": {"size": [2160, 1080], "canvas_offset": [120, 0], "canvas_cut_px": 0},
}

# Leitor da VRAM falsa no lugar do nvidia-smi: imprime o valor e registra cada leitura em
# <PILOT_VRAM>.reads, para o runtime falso saber quando o medidor já leu.
READ_VRAM = (
    "import sys; value = open(sys.argv[1]).read(); "
    "open(sys.argv[1] + '.reads', 'a').write(value + '\\n'); print(value)"
)

# Runtimes falsos: recebem <stage.py> <request.json> <result.json> como o Python do runtime.
# Registram início e fim de cada execução (<id>/run-N) em PILOT_LOG e seguram a VRAM falsa em
# PILOT_VRAM durante o trabalho. FAKE_AVATAR_FAIL=<id> faz o render dessa amostra sair com 3.
FAKE_COMMON = """
import json, os, pathlib, subprocess, sys, time, wave
_, request_path, result_path = sys.argv[1:]
request = json.load(open(request_path, encoding="utf-8"))
def event(name, run_dir):
    with open(os.environ["PILOT_LOG"], "a") as log:
        log.write(name + ":" + "/".join(pathlib.Path(run_dir).parts[-2:]) + "\\n")
def vram(value):
    with open(os.environ["PILOT_VRAM"], "w") as out:
        out.write(value)
def hold_vram(value):
    # Segura o valor até três leituras depois da escrita, sem depender da carga da máquina.
    # O medidor lê uma vez por vez: a terceira só começa depois que ele registrou a segunda,
    # que já leu o valor dentro do estágio.
    vram(value)
    reads = os.environ["PILOT_VRAM"] + ".reads"
    def count():
        return len(open(reads).readlines()) if os.path.exists(reads) else 0
    target, deadline = count() + 3, time.monotonic() + 30
    while count() < target and time.monotonic() < deadline:
        time.sleep(0.01)
"""

FAKE_TTS = """
run_dir = os.path.dirname(request["out_wav"])
event("tts:start", run_dir)
hold_vram("3000")
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
event("tts:end", run_dir)
"""

FAKE_AVATAR = """
event("avatar:start", request["out_dir"])
if not os.path.isfile(request["audio"]):
    sys.exit(5)
if pathlib.Path(request["out_dir"]).parent.name == os.environ.get("FAKE_AVATAR_FAIL"):
    sys.exit(3)
hold_vram("7000")
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
event("avatar:end", request["out_dir"])
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

    # Entradas na pasta da fila; as amostras as referem por caminho relativo a ela.
    inputs = tmp_path / "fila"
    inputs.mkdir()
    avatar = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    avatar.paste((200, 150, 120, 255), (100, 100, 300, 800))
    avatar.save(inputs / "avatar.png")
    Image.new("RGB", (64, 36), (10, 20, 30)).save(inputs / "fundo.png")
    vram_command = shlex.join([sys.executable, "-c", READ_VRAM, str(vram)])
    tts = _script(tmp_path / "fake-tts-python", FAKE_TTS)
    render = _script(tmp_path / "fake-avatar-python", FAKE_AVATAR)
    args = [
        "--recipe", str(RECIPE_PATH),
        "--manifest", str(MANIFEST_PATH),
        "--models", str(tmp_path / "models"),
        "--out", str(tmp_path / "out"),
        "--tts-python", str(tts),
        "--avatar-python", str(render),
        "--infinitetalk-dir", str(tmp_path / "infinitetalk"),
        "--vram-command", vram_command,
    ]  # fmt: skip
    return {
        "args": args,
        "log": log,
        "out": tmp_path / "out",
        "inputs": inputs,
        "commands": {
            "tts": [str(tts), str(pilot.TTS_STAGE)],
            "avatar": [str(render), str(pilot.AVATAR_STAGE)],
            "vram": shlex.split(vram_command),
        },
    }


def _sample(sample_id, aspect, **fields):
    text = {} if "text_file" in fields else {"text": TEXT}
    return {
        "id": sample_id,
        "image": "avatar.png",
        "background": "#1f2937",
        **text,
        "voice": "feminina",
        "format": aspect,
        **fields,
    }


def _queue(env, *samples):
    """Grava a fila na pasta das entradas e devolve os argumentos do piloto com --queue."""
    queue = env["inputs"] / "fila.json"
    queue.write_text(json.dumps({"samples": list(samples)}, ensure_ascii=False), encoding="utf-8")
    return [*env["args"], "--queue", str(queue)]


def _index(out):
    return json.loads((out / "index.json").read_text(encoding="utf-8"))


def _report(out, sample_id):
    return json.loads((out / sample_id / "report.json").read_text(encoding="utf-8"))


def _events(log):
    return log.read_text().split() if log.exists() else []


def _run_events(*runs):
    """Eventos de execuções completas: cada uma termina o TTS antes de o render começar."""
    stages = ("tts:start", "tts:end", "avatar:start", "avatar:end")
    return [f"{stage}:{run}" for run in runs for stage in stages]


def _finals(out):
    return sorted(path.relative_to(out).as_posix() for path in out.rglob("final.mp4"))


def test_queue_runs_in_order_with_run_folders_sample_reports_and_index(env):
    samples = [_sample("retrato", "9:16"), _sample("paisagem", "16:9")]

    assert pilot.main([*_queue(env, *samples), "--runs", "2"]) == 0

    index = _index(env["out"])
    assert index["status"] == "ok"
    queue = env["inputs"] / "fila.json"
    assert index["queue_sha256"] == hashlib.sha256(queue.read_bytes()).hexdigest()
    assert index["samples"] == [
        {"id": "retrato", "format": "9:16", "status": "ok", "report": "retrato/report.json"},
        {"id": "paisagem", "format": "16:9", "status": "ok", "report": "paisagem/report.json"},
    ]
    for sample in samples:
        sample_id, aspect = sample["id"], sample["format"]
        report = _report(env["out"], sample_id)
        assert report["status"] == "ok"
        assert report["error"] is None
        assert (report["id"], report["format"], report["voice"]) == (sample_id, aspect, "feminina")
        assert report["recipe_status"] == "draft"
        assert report["recipe_sha256"] == hashlib.sha256(RECIPE_PATH.read_bytes()).hexdigest()
        assert report["worker_image"] == "sha256:" + "a" * 64
        assert report["network_interfaces"] == ["lo"]
        # Os dublês ficam identificados: o relatório diz quem rodou cada runtime e a VRAM.
        assert report["commands"] == env["commands"]
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
        assert report["canvas"] == list(CANVAS[aspect])
        assert report["bucket"] == BUCKETS[aspect]
        assert report["render_input"] == RENDER_INPUT[aspect]
        assert [run["load"] for run in report["runs"]] == ["cold", "warm"]
        assert report["seconds_per_video_second"]["cold"] > 0
        assert report["seconds_per_video_second"]["warm"] > 0
        for number, run in enumerate(report["runs"], start=1):
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
            assert run["canvas_cut_px"] == 0
            assert run["frames"] == 25
            final = Path(run["final_path"])
            assert final == env["out"] / sample_id / f"run-{number}" / "final.mp4"
            assert run["final_sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
            assert (run["final"]["width"], run["final"]["height"]) == CANVAS[aspect]
            assert run["final"]["pix_fmt"] == "yuv420p"
            assert run["final"]["sample_rate"] == 48000
            assert run["seconds_per_video_second"] > 0
            assert not (final.parent / "save_audio").exists()

    assert _events(env["log"]) == _run_events(
        "retrato/run-1", "retrato/run-2", "paisagem/run-1", "paisagem/run-2"
    )


def test_each_sample_runs_with_its_literal_text_voice_and_composition(env):
    # CRLF e quebra final chegam ao TTS como estão no arquivo, sem normalização.
    speech = "Primeira linha.\r\nSegunda linha, R$ 1.890.\n"
    (env["inputs"] / "fala.txt").write_bytes(speech.encode("utf-8"))
    samples = [
        _sample(
            "explicita", "16:9", text_file="fala.txt", voice="masculina", composition=COMPOSITION
        ),
        _sample("receita", "16:9", background="fundo.png"),
    ]

    assert pilot.main(_queue(env, *samples)) == 0

    calibration = RECIPE["calibration"]["composition"]["16:9"]
    with (
        Image.open(env["inputs"] / "avatar.png") as avatar,
        Image.open(env["inputs"] / "fundo.png") as background,
    ):
        # Pad: a cor do cenário ou a média da imagem de fundo.
        expected = {
            "explicita": (speech, "masculina", COMPOSITION, "sample", "#1f2937", (31, 41, 55)),
            "receita": (TEXT, "feminina", calibration, "recipe", background, (10, 20, 30)),
        }
        for sample_id, (text, voice, composition, source, scene, pad) in expected.items():
            run_dir = env["out"] / sample_id / "run-1"
            tts = json.loads((run_dir / "tts_request.json").read_text(encoding="utf-8"))
            assert tts["text"] == text
            assert tts["language"] == "pt"
            assert tts["voice"] == RECIPE["tts"]["voices"][voice]
            render = json.loads((run_dir / "avatar_request.json").read_text(encoding="utf-8"))
            assert render["format"] == "16:9"
            assert render["audio"] == tts["out_wav"]
            assert render["recipe_avatar"]["max_frame_num"] == 1000
            assert render["recipe_avatar"]["quant"] is None
            fields = ("lora", "sample_text_guide_scale", "sample_audio_guide_scale")
            for field in (*fields, "negative_prompt"):
                assert render["recipe_avatar"][field] == RECIPE["avatar"][field]
            # A composição explícita da amostra precede a calibração da receita.
            report = _report(env["out"], sample_id)
            assert report["composition"] == {**composition, "source": source}
            canvas = compose_canvas(avatar, scene, composition, CANVAS["16:9"])
            with (
                Image.open(run_dir / "canvas.png") as written,
                Image.open(render["image"]) as render_input,
            ):
                assert written.tobytes() == canvas.tobytes()
                # O render recebe o canvas estendido com a cor do cenário até a razão do bucket.
                assert render_input.size == (2160, 1080)
                assert render_input.getpixel((0, 540)) == pad
                assert render_input.crop((120, 0, 2040, 1080)).tobytes() == canvas.tobytes()
    assert _report(env["out"], "receita")["background"] == str(env["inputs"] / "fundo.png")


def test_stage_failure_is_readable_in_sample_report_and_queue_continues(env, monkeypatch):
    monkeypatch.setenv("FAKE_AVATAR_FAIL", "quebra")
    samples = [_sample("retrato", "9:16"), _sample("quebra", "9:16"), _sample("paisagem", "16:9")]

    assert pilot.main(_queue(env, *samples)) == 1

    index = _index(env["out"])
    assert index["status"] == "failed"
    assert [(entry["id"], entry["status"]) for entry in index["samples"]] == [
        ("retrato", "ok"),
        ("quebra", "failed"),
        ("paisagem", "ok"),
    ]
    report = _report(env["out"], "quebra")
    assert report["status"] == "failed"
    assert report["error"]["stage"] == "avatar"
    assert report["error"]["run"] == 1
    assert "código 3" in report["error"]["message"]
    (run,) = report["runs"]
    assert list(run["stages"]) == ["compose", "tts", "avatar"]
    assert _finals(env["out"]) == ["paisagem/run-1/final.mp4", "retrato/run-1/final.mp4"]
    assert _events(env["log"]) == [
        *_run_events("retrato/run-1"),
        "tts:start:quebra/run-1",
        "tts:end:quebra/run-1",
        "avatar:start:quebra/run-1",
        *_run_events("paisagem/run-1"),
    ]


def test_manifest_violating_commercial_policy_refused_before_any_stage(env, tmp_path, capsys):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    (lora,) = [c for c in manifest["components"] if c["id"] == "lightx2v-lora"]
    lora["commercial_use"] = False
    tampered = tmp_path / "manifest.json"
    tampered.write_text(json.dumps(manifest), encoding="utf-8")
    args = _queue(env, _sample("retrato", "9:16"))
    args[args.index("--manifest") + 1] = str(tampered)

    assert pilot.main(args) == 1

    err = capsys.readouterr().err
    assert "Manifesto recusado pela política comercial" in err
    assert "lightx2v-lora" in err
    assert not env["out"].exists() or not any(env["out"].iterdir())
    assert not env["log"].exists()


def test_audio_above_limit_fails_tts_before_render(env, monkeypatch):
    monkeypatch.setenv("FAKE_TTS_SECONDS", "1.0")

    args = _queue(env, _sample("longa", "9:16"))
    assert pilot.main([*args, "--max-audio-seconds", "0.5"]) == 1

    report = _report(env["out"], "longa")
    assert report["limits"]["max_audio_seconds"] == 0.5
    assert report["limits"]["max_frame_num"] == 13
    assert report["error"]["stage"] == "tts"
    assert "limite" in report["error"]["message"]
    assert _events(env["log"]) == ["tts:start:longa/run-1", "tts:end:longa/run-1"]
    assert _finals(env["out"]) == []


@pytest.mark.parametrize(
    "invalid, message",
    [
        ({"id": "RETRATO"}, "amostra 2 (RETRATO): id repete o da amostra 1"),
        ({"id": "../fora"}, "id '../fora' precisa ter só letras"),
        ({"image": "ausente.png"}, "image 'ausente.png' não é arquivo existente"),
        ({"voice": "infantil"}, "voice 'infantil' precisa ser feminina ou masculina"),
        ({"format": "4:3"}, "format '4:3' precisa ser 9:16 ou 16:9"),
        ({"composition": {"scale": 0.8, "x": 0.5, "y": 0.4}}, "composition.y 0.4 fora da faixa"),
        ({"compositon": COMPOSITION}, "chave desconhecida 'compositon'"),
        ({"text_file": "vazia.txt"}, "a fala está vazia"),
    ],
)
def test_invalid_queue_is_refused_before_executing_any_sample(env, capsys, invalid, message):
    (env["inputs"] / "vazia.txt").write_text(" \n", encoding="utf-8")
    samples = [_sample("retrato", "9:16"), _sample("segunda", "16:9", **invalid)]

    with pytest.raises(SystemExit) as exc:
        pilot.main(_queue(env, *samples))

    assert exc.value.code == 2
    assert message in capsys.readouterr().err
    assert _events(env["log"]) == []
    assert not env["out"].exists()


def test_used_out_is_refused_before_executing(env, capsys):
    env["out"].mkdir()
    previous = env["out"] / "index.json"
    previous.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        pilot.main(_queue(env, _sample("retrato", "9:16")))

    assert exc.value.code == 2
    assert "já foi usado" in capsys.readouterr().err
    assert previous.read_text(encoding="utf-8") == "{}"
    assert _events(env["log"]) == []


def test_pad_color_is_scene_color_or_mean_of_background_image():
    assert background_pad_color("#1f2937") == "#1f2937"
    assert background_pad_color(Image.new("RGB", (8, 8), (10, 20, 30))) == "#0a141e"


def test_render_that_would_cut_the_canvas_fails_avatar_stage(env, tmp_path):
    """Render nativo fora da razão da tela: o corte central tiraria canvas, o piloto recusa."""
    body = FAKE_AVATAR.replace('(448, 832), "16:9": (896, 448)', '(448, 896), "16:9": (896, 448)')
    args = _queue(env, _sample("larga", "9:16"))
    args[args.index("--avatar-python") + 1] = str(_script(tmp_path / "fake-avatar-wide", body))

    assert pilot.main(args) == 1

    report = _report(env["out"], "larga")
    assert report["error"]["stage"] == "avatar"
    assert "corta" in report["error"]["message"]
    (run,) = report["runs"]
    assert run["canvas_cut_px"] > 0
    assert _finals(env["out"]) == []


def test_qwen_recipe_sends_engine_transcript_and_sampler_to_tts(env, tmp_path):
    import test_recipe

    recipe = tmp_path / "recipe-qwen.json"
    recipe.write_text(json.dumps(test_recipe._recipe(test_recipe._qwen)), encoding="utf-8")
    manifest = tmp_path / "manifest-qwen.json"
    manifest.write_text(json.dumps(test_recipe.QWEN_MANIFEST), encoding="utf-8")
    args = _queue(env, _sample("qwen", "9:16", voice="masculina"))
    args[args.index("--recipe") + 1] = str(recipe)
    args[args.index("--manifest") + 1] = str(manifest)

    assert pilot.main(args) == 0

    request = json.loads((env["out"] / "qwen" / "run-1" / "tts_request.json").read_text())
    assert request["engine"] == "qwen3-tts-base"
    assert request["voice"]["transcript"] == test_recipe.FABER_TEXT
    assert request["sampler"] == test_recipe.SAMPLER


def test_default_tts_python_follows_engine():
    assert pilot.default_tts_python("qwen3-tts-base") == pilot.DEFAULT_QWEN_TTS_PYTHON
    assert pilot.default_tts_python("chatterbox-multilingual") == pilot.DEFAULT_TTS_PYTHON
