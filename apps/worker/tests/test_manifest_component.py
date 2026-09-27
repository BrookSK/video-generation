import hashlib
import json

import pytest

from avatar_worker import manifest as manifest_module
from avatar_worker.manifest import main

COMMIT = "0123456789abcdef0123456789abcdef01234567"
BODIES = {
    "https://huggingface.co/example/a/w.onnx": b"pesos sinteticos A",
    "https://huggingface.co/example/b/w.onnx": b"pesos sinteticos B",
    "https://huggingface.co/example/c/w.onnx": b"pesos sinteticos C",
}


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


def _pull(tmp_path, *components):
    policy = tmp_path / "MODEL_MANIFEST.json"
    manifest = {"schema_version": 1, "components": [_component(n) for n in ("a", "b", "c")]}
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
