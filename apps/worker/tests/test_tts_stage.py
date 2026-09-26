import ast
import hashlib
import importlib.util
import json
import os
import sys
import tomllib
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "apps" / "worker" / "runtimes" / "tts"
STAGE_PATH = RUNTIME / "tts_stage.py"
MANIFEST = json.loads((ROOT / "docs" / "models" / "MODEL_MANIFEST.json").read_text())

_spec = importlib.util.spec_from_file_location("tts_stage", STAGE_PATH)
tts_stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tts_stage)

TEXT = "Em 2026, a Dra. Ana Luíza Gonçalves atendeu 1.234 pacientes às 14h30: R$ 5.678,90!"
RESULT_FIELDS = {
    "audio_path",
    "duration_s",
    "sample_rate",
    "peak_vram_mb",
    "watermark_detected",
    "elapsed_s",
}


class FakeSynth:
    def __init__(self, seconds=1.5):
        self.calls = []
        self.env = {}
        self.frames = int(seconds * tts_stage.SAMPLE_RATE)

    def __call__(self, text, language, voice, models_dir):
        self.calls.append((text, language, voice, models_dir))
        self.env = {name: os.environ.get(name) for name in tts_stage.OFFLINE_ENV}
        return tts_stage.Synthesis(
            pcm16=b"\x00\x01" * self.frames,
            sample_rate=tts_stage.SAMPLE_RATE,
            peak_vram_mb=1234.5,
        )


@pytest.fixture(autouse=True)
def _clean_offline_env(monkeypatch):
    for name in tts_stage.OFFLINE_ENV:
        monkeypatch.delenv(name, raising=False)


def _request(tmp_path, voice):
    models_dir = tmp_path / "models"
    request = {
        "text": TEXT,
        "language": "pt",
        "voice": voice,
        "models_dir": str(models_dir),
        "out_wav": str(tmp_path / "out" / "speech.wav"),
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    return path, models_dir


def _voice_file(tmp_path, content=b"RIFF referencia de voz"):
    path = tmp_path / "models" / "voices" / "cliente.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return "voices/cliente.wav", hashlib.sha256(content).hexdigest()


def _main(tmp_path, request_path, synth, detected=True):
    result_path = tmp_path / "result.json"
    code = tts_stage.main(
        [str(request_path), str(result_path)],
        synthesize=synth,
        detect_watermark=lambda path: detected,
    )
    return code, result_path


def test_text_reaches_synthesizer_literally_and_result_has_six_fields(tmp_path):
    request_path, models_dir = _request(tmp_path, {"kind": "default"})
    synth = FakeSynth(seconds=1.5)

    code, result_path = _main(tmp_path, request_path, synth)

    assert code == 0
    assert synth.calls == [(TEXT, "pt", None, models_dir)]
    result = json.loads(result_path.read_text())
    assert set(result) == RESULT_FIELDS
    assert result["audio_path"] == str(tmp_path / "out" / "speech.wav")
    assert result["duration_s"] == 1.5
    assert result["sample_rate"] == 24000
    assert result["peak_vram_mb"] == 1234.5
    assert result["watermark_detected"] is True
    assert isinstance(result["elapsed_s"], float) and result["elapsed_s"] >= 0
    with wave.open(result["audio_path"], "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 24000
        assert audio.getsampwidth() == 2
        assert audio.getnframes() == 36000


def test_offline_env_is_set_before_synthesis(tmp_path):
    request_path, _ = _request(tmp_path, {"kind": "default"})
    synth = FakeSynth()

    code, _ = _main(tmp_path, request_path, synth)

    assert code == 0
    assert synth.env == {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}


def test_reference_voice_with_matching_hash_is_passed_to_synthesizer(tmp_path):
    path, sha256 = _voice_file(tmp_path)
    request_path, models_dir = _request(
        tmp_path, {"kind": "reference", "path": path, "sha256": sha256}
    )
    synth = FakeSynth()

    code, _ = _main(tmp_path, request_path, synth, detected=False)

    assert code == 0
    assert synth.calls[0][2] == models_dir / path


def test_reference_voice_with_wrong_hash_exits_1_before_synthesis(tmp_path, capsys):
    path, _ = _voice_file(tmp_path)
    request_path, _ = _request(tmp_path, {"kind": "reference", "path": path, "sha256": "0" * 64})
    synth = FakeSynth()

    code, result_path = _main(tmp_path, request_path, synth)

    assert code == 1
    assert synth.calls == []
    assert not result_path.exists()
    assert not (tmp_path / "out" / "speech.wav").exists()
    assert "sha256 da referência voices/cliente.wav diverge" in capsys.readouterr().err


@pytest.mark.parametrize(
    "voice",
    [
        {"kind": "reference", "path": "voices/cliente.wav"},
        {"kind": "reference", "path": "../fora.wav", "sha256": "0" * 64},
        {"kind": "clone"},
    ],
)
def test_invalid_voice_exits_1_before_synthesis(tmp_path, voice):
    request_path, _ = _request(tmp_path, voice)
    synth = FakeSynth()

    code, _ = _main(tmp_path, request_path, synth)

    assert code == 1
    assert synth.calls == []


def test_checkpoint_files_come_from_manifest_components():
    files = {
        (component["id"], item["path"])
        for component in MANIFEST["components"]
        for item in component["files"]
    }
    for source in tts_stage.CHECKPOINT_FILES.values():
        assert source in files
    assert tts_stage.CHECKPOINT_FILES["t3_mtl23ls_v2.safetensors"] == (
        "chatterbox-multilingual-pt-br",
        "t3_pt_br.safetensors",
    )
    assert tts_stage.CHECKPOINT_FILES["s3gen.pt"] == (
        "chatterbox-multilingual-pt-br",
        "s3gen_v3.pt",
    )


def test_chatterbox_wheel_sha256_in_lock_matches_manifest():
    lock = tomllib.loads((RUNTIME / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == "chatterbox-tts")
    component = next(c for c in MANIFEST["components"] if c["id"] == "chatterbox-tts")
    (expected,) = component["files"]

    assert package["version"] == component["version"]
    (wheel,) = package["wheels"]
    assert wheel["url"] == expected["url"]
    assert wheel["hash"] == f"sha256:{expected['sha256']}"


def test_stage_module_imports_only_stdlib_at_top_level():
    tree = ast.parse(STAGE_PATH.read_text())
    modules = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module.split(".")[0])
    assert modules <= sys.stdlib_module_names
