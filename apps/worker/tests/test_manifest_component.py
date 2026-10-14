import hashlib
import json
from pathlib import Path

import pytest

from avatar_worker import manifest as manifest_module
from avatar_worker.manifest import load_manifest, main

COMMIT = "0123456789abcdef0123456789abcdef01234567"
BODIES = {
    "https://huggingface.co/example/a/w.onnx": b"pesos sinteticos A",
    "https://huggingface.co/example/b/w.onnx": b"pesos sinteticos B",
    "https://huggingface.co/example/c/w.onnx": b"pesos sinteticos C",
}
MANIFEST_PATH = Path(__file__).resolve().parents[3] / "docs" / "models" / "MODEL_MANIFEST.json"
LORA = next(c for c in load_manifest(MANIFEST_PATH)["components"] if c["id"] == "lightx2v-lora")


def _component(name):
    url = f"https://huggingface.co/example/{name}/w.onnx"
    body = BODIES[url]
    return {
        "id": f"modelo-{name}",
        "kind": "model",
        "url": f"https://huggingface.co/example/{name}",
        "revision": COMMIT,
        "code_license": "MIT",
        "weights_license": "Apache-2.0",
        "commercial_use": True,
        "license_evidence": [f"https://huggingface.co/example/{name}/blob/{COMMIT}/LICENSE"],
        "files": [
            {
                "path": "w.onnx",
                "url": url,
                "sha256": hashlib.sha256(body).hexdigest(),
                "size": len(body),
            }
        ],
    }


@pytest.fixture
def downloads(monkeypatch):
    """Troca o download HTTP por uma gravação local e registra cada URL pedida."""
    requested = []

    def fake_download(url, part, size):
        requested.append(url)
        part.write_bytes(BODIES[url])
        return hashlib.sha256(BODIES[url]).hexdigest()

    monkeypatch.setattr(manifest_module, "_download", fake_download)
    return requested


def _pull(tmp_path, *components, extra=()):
    policy = tmp_path / "MODEL_MANIFEST.json"
    models = [_component(n) for n in ("a", "b", "c")]
    manifest = {"schema_version": 1, "components": [*models, *extra]}
    policy.write_text(json.dumps(manifest), encoding="utf-8")
    dest = tmp_path / "models"
    dest.mkdir()
    argv = ["pull", "--policy", str(policy), "--dest", str(dest)]
    for component in components:
        argv += ["--component", component]
    return main(argv), dest


def test_component_restricts_download_to_named(tmp_path, downloads, capsys):
    code, dest = _pull(tmp_path, "modelo-b")

    assert code == 0
    assert downloads == ["https://huggingface.co/example/b/w.onnx"]
    assert sorted(path.name for path in dest.iterdir()) == ["modelo-b"]
    assert "1 baixado(s), 0 já presente(s)" in capsys.readouterr().out


def test_component_is_repeatable(tmp_path, downloads):
    code, dest = _pull(tmp_path, "modelo-a", "modelo-c")

    assert code == 0
    assert sorted(path.name for path in dest.iterdir()) == ["modelo-a", "modelo-c"]
    assert len(downloads) == 2


def test_without_component_downloads_every_model(tmp_path, downloads):
    code, _ = _pull(tmp_path)

    assert code == 0
    assert len(downloads) == 3


def test_unknown_component_exits_1_before_any_download(tmp_path, downloads, capsys):
    code, dest = _pull(tmp_path, "modelo-a", "modelo-inexistente")

    assert code == 1
    assert downloads == []
    assert list(dest.iterdir()) == []
    assert "componente fora do manifesto: modelo-inexistente" in capsys.readouterr().err


def test_lora_with_divergent_bytes_exits_1_without_final_file(
    tmp_path, downloads, monkeypatch, capsys
):
    (lora_file,) = LORA["files"]
    monkeypatch.setitem(BODIES, lora_file["url"], b"bytes que nao sao a LoRA lightx2v")

    code, dest = _pull(tmp_path, "lightx2v-lora", extra=[LORA])

    assert code == 1
    assert downloads == [lora_file["url"]]
    assert list((dest / "lightx2v-lora").iterdir()) == []
    err = capsys.readouterr().err
    assert f"lightx2v-lora/{lora_file['path']}: sha256" in err
    assert "diferente do manifesto" in err
