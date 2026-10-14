import copy
import hashlib
import importlib.util
import json
import os
import socket
import wave
from pathlib import Path

import pytest

from avatar_worker.manifest import check_policy, load_manifest

ROOT = Path(__file__).resolve().parents[3]
TOOL_PATH = ROOT / "apps" / "worker" / "runtimes" / "voices" / "voice_references.py"
COMPONENTS = {
    component["id"]: component
    for component in load_manifest(ROOT / "docs" / "models" / "MODEL_MANIFEST.json")["components"]
}
PRESETS = ("pf_dora", "pm_alex")

_spec = importlib.util.spec_from_file_location("voice_references", TOOL_PATH)
voice_references = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(voice_references)


class FakeSynth:
    """Sintetizador injetado: um segundo de áudio por preset; registra o ambiente da geração."""

    def __init__(self, same_audio=False):
        self.same_audio = same_audio
        self.calls = []
        self.env = None
        self.network = None

    def __call__(self, models_dir, text, presets, code_revision):
        self.calls.append((models_dir, text, presets, code_revision))
        self.env = {name: os.environ.get(name) for name in voice_references.OFFLINE_ENV}
        try:
            socket.create_connection(("127.0.0.1", 9), timeout=0.1)
        except OSError as exc:
            self.network = str(exc)
        return {
            preset: voice_references.Synthesis(
                pcm16=bytes([0 if self.same_audio else index + 1, 0]) * 24000,
                sample_rate=24000,
            )
            for index, preset in enumerate(presets)
        }


@pytest.fixture
def sources(tmp_path):
    """Fontes kokoro-82m sintéticas em models/ e um manifesto com seus tamanhos e hashes."""
    source = copy.deepcopy(COMPONENTS["kokoro-82m"])
    models = tmp_path / "models"
    for entry in source["files"]:
        body = f"fonte sintetica {entry['path']}".encode()
        path = models / "kokoro-82m" / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        entry.update(sha256=hashlib.sha256(body).hexdigest(), size=len(body))
    manifest = {"schema_version": 1, "components": [COMPONENTS["kokoro-code"], source]}
    manifest_path = tmp_path / "MODEL_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, models, manifest


def _run(sources, synth):
    manifest_path, models, _ = sources
    argv = ["--manifest", str(manifest_path), "--models", str(models)]
    return voice_references.main(argv, synthesize=synth)


def test_generates_distinct_mono_24khz_wavs_offline_with_valid_provenance(sources, capsys):
    _, models, manifest = sources
    synth = FakeSynth()

    assert _run(sources, synth) == 0

    (call,) = synth.calls
    code_revision = COMPONENTS["kokoro-code"]["revision"]
    assert call[1:] == (voice_references.TEXT, PRESETS, code_revision)
    assert synth.env == {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    assert "rede bloqueada" in synth.network
    component = json.loads(capsys.readouterr().out)
    registered = {**manifest, "components": [*manifest["components"], component]}
    assert check_policy(registered) == []
    source_files = manifest["components"][1]["files"]
    source_hashes = {f"kokoro-82m/{entry['path']}": entry["sha256"] for entry in source_files}
    for entry, preset in zip(component["files"], PRESETS, strict=True):
        wav_path = models / "kokoro-voice-references" / entry["path"]
        with wave.open(str(wav_path), "rb") as audio:
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == 24000
            assert audio.getnframes() == 24000
        assert entry["sha256"] == hashlib.sha256(wav_path.read_bytes()).hexdigest()
        assert entry["size"] == wav_path.stat().st_size
        provenance = entry["provenance"]
        assert provenance["preset"] == f"kokoro-82m/voices/{preset}.pt"
        assert provenance["text"] == voice_references.TEXT
        assert provenance["parameters"]["seed"] == voice_references.SEED
        assert provenance["revisions"] == {
            "kokoro-code": code_revision,
            "kokoro-82m": COMPONENTS["kokoro-82m"]["revision"],
        }
        assert provenance["sources"] == {
            label: source_hashes[label]
            for label in (provenance["model"], provenance["preset"], "kokoro-82m/config.json")
        }
    assert component["files"][0]["sha256"] != component["files"][1]["sha256"]


@pytest.mark.parametrize(
    ("relative", "tamper", "expected"),
    [
        ("voices/pm_alex.pt", lambda body: body[::-1], "kokoro-82m/voices/pm_alex.pt: sha256"),
        ("kokoro-v1_0.pth", lambda body: body[:-1], "kokoro-82m/kokoro-v1_0.pth: 30 bytes"),
    ],
    ids=["preset-adulterado", "modelo-truncado"],
)
def test_divergent_source_is_refused_before_the_model(sources, capsys, relative, tamper, expected):
    _, models, _ = sources
    path = models / "kokoro-82m" / relative
    path.write_bytes(tamper(path.read_bytes()))
    synth = FakeSynth()

    assert _run(sources, synth) == 1

    assert synth.calls == []
    assert not (models / "kokoro-voice-references").exists()
    assert expected in capsys.readouterr().err


def test_identical_voices_are_refused_without_writing(sources, capsys):
    _, models, _ = sources

    assert _run(sources, FakeSynth(same_audio=True)) == 1

    assert not (models / "kokoro-voice-references").exists()
    assert "geraram áudios iguais" in capsys.readouterr().err
