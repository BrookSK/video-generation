import copy
import json
import subprocess
import sys

import pytest

from avatar_worker.manifest import check_policy, main

COMMIT = "0123456789abcdef0123456789abcdef01234567"
SHA256 = "a" * 64

VALID_MANIFEST = {
    "schema_version": 1,
    "components": [
        {
            "id": "infinitetalk-weights",
            "kind": "model",
            "url": "https://huggingface.co/MeiGen-AI/InfiniteTalk",
            "revision": COMMIT,
            "code_license": "Apache-2.0",
            "weights_license": "apache-2.0",
            "commercial_use": True,
            "license_evidence": ["https://huggingface.co/MeiGen-AI/InfiniteTalk/blob/main/LICENSE"],
            "files": [
                {
                    "path": "single/infinitetalk.safetensors",
                    "url": "https://huggingface.co/MeiGen-AI/InfiniteTalk/resolve/x/w.safetensors",
                    "sha256": SHA256,
                    "size": 1024,
                }
            ],
        },
        {
            "id": "rembg",
            "kind": "code",
            "url": "https://github.com/danielgatis/rembg",
            "revision": COMMIT,
            "code_license": "MIT",
            "weights_license": None,
            "commercial_use": True,
            "license_evidence": ["https://github.com/danielgatis/rembg/blob/x/LICENSE.txt"],
            "files": [],
        },
        {
            "id": "flash-attn-wheel",
            "kind": "wheel",
            "url": "https://github.com/Dao-AILab/flash-attention",
            "revision": "2.7.4.post1",
            "code_license": "BSD-3-Clause",
            "weights_license": None,
            "commercial_use": True,
            "license_evidence": ["https://github.com/Dao-AILab/flash-attention/blob/x/LICENSE"],
            "files": [
                {
                    "path": "flash_attn-2.7.4.post1-cp310-cp310-linux_x86_64.whl",
                    "url": "https://github.com/Dao-AILab/flash-attention/releases/download/x.whl",
                    "sha256": SHA256,
                    "size": 2048,
                }
            ],
        },
    ],
}


def _manifest(mutate=None):
    manifest = copy.deepcopy(VALID_MANIFEST)
    if mutate:
        mutate(manifest)
    return manifest


def _write(tmp_path, manifest):
    path = tmp_path / "MODEL_MANIFEST.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _set(index, key, value):
    def mutate(manifest):
        manifest["components"][index][key] = value

    return mutate


def _set_file(index, key, value):
    def mutate(manifest):
        manifest["components"][index]["files"][0][key] = value

    return mutate


def _drop_file_key(index, key):
    def mutate(manifest):
        del manifest["components"][index]["files"][0][key]

    return mutate


def _duplicate_first(manifest):
    manifest["components"].append(copy.deepcopy(manifest["components"][0]))


def _add_component(component_id, url):
    def mutate(manifest):
        extra = copy.deepcopy(manifest["components"][1])
        extra["id"] = component_id
        extra["url"] = url
        manifest["components"].append(extra)

    return mutate


def test_valid_manifest_passes(tmp_path, capsys):
    path = _write(tmp_path, _manifest())

    assert check_policy(_manifest()) == []
    assert main(["verify", "--policy", str(path)]) == 0
    out = capsys.readouterr().out
    assert "infinitetalk-weights (model)" in out
    assert "flash-attn-wheel (wheel)" in out
    assert "Manifesto aceito: 3 componente(s)." in out


def test_module_entry_point_exit_codes(tmp_path):
    command = [sys.executable, "-m", "avatar_worker.manifest", "verify", "--policy"]
    good = _write(tmp_path, _manifest())
    ok = subprocess.run([*command, str(good)], capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stderr

    bad = _write(tmp_path, _manifest(_set(0, "weights_license", "CC-BY-NC-4.0")))
    refused = subprocess.run([*command, str(bad)], capture_output=True, text=True, check=False)
    assert refused.returncode == 1
    assert "infinitetalk-weights: weights_license 'CC-BY-NC-4.0'" in refused.stderr


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            _set(0, "weights_license", "CC-BY-NC-4.0"),
            "infinitetalk-weights: weights_license 'CC-BY-NC-4.0' não é permitida",
        ),
        (_set(0, "weights_license", None), "infinitetalk-weights: weights_license None"),
        (_set(1, "code_license", "CC-BY-NC-4.0"), "rembg: code_license 'CC-BY-NC-4.0'"),
        (_set(1, "code_license", "GPL-3.0"), "rembg: code_license 'GPL-3.0'"),
        (_set(0, "commercial_use", False), "commercial_use diferente de true"),
        (_set(1, "commercial_use", "true"), "rembg: commercial_use diferente de true"),
        (
            _set(0, "revision", "main"),
            "infinitetalk-weights: revision 'main' não é commit de 40 hexadecimais",
        ),
        (_set(1, "revision", "v0.1.7"), "rembg: revision 'v0.1.7' não é commit"),
        (_set(2, "revision", ">=2.7"), "flash-attn-wheel: wheel sem versão exata"),
        (_set(2, "revision", "2.7.*"), "flash-attn-wheel: wheel sem versão exata"),
        (
            _drop_file_key(0, "sha256"),
            "infinitetalk-weights: arquivo single/infinitetalk.safetensors sem sha256",
        ),
        (_set_file(0, "sha256", "abc"), "infinitetalk-weights: arquivo single/"),
        (_drop_file_key(2, "size"), "flash-attn-wheel: arquivo flash_attn-2.7.4.post1"),
        (_set(0, "files", []), "infinitetalk-weights: componente model sem arquivo"),
        (_set(2, "files", []), "flash-attn-wheel: componente wheel sem arquivo"),
        (_set(1, "url", "http://github.com/danielgatis/rembg"), "rembg: url sem https"),
        (_set_file(0, "url", "http://example.com/w"), "safetensors: url sem https"),
        (_duplicate_first, "infinitetalk-weights: id duplicado"),
        (_set(1, "id", ""), "componente #1: sem id"),
        (_set(1, "kind", "dataset"), "rembg: kind 'dataset' fora de model, code, wheel"),
        (
            _add_component("bria-rmbg", "https://huggingface.co/briaai/RMBG-2.0"),
            "bria-rmbg: bria-rmbg é proibido",
        ),
        (
            _add_component("face-detector", "https://github.com/deepinsight/InsightFace"),
            "face-detector: insightface é proibido",
        ),
        (
            _set_file(0, "path", "models/bria-rmbg.onnx"),
            "infinitetalk-weights: bria-rmbg é proibido (models/bria-rmbg.onnx)",
        ),
    ],
)
def test_policy_violation_is_named_and_exits_1(tmp_path, capsys, mutate, expected):
    path = _write(tmp_path, _manifest(mutate))

    assert main(["verify", "--policy", str(path)]) == 1
    err = capsys.readouterr().err
    assert "Manifesto recusado" in err
    assert expected in err


def test_license_comparison_ignores_case():
    manifest = _manifest(_set(1, "code_license", "bsd-2-clause"))

    assert check_policy(manifest) == []


def test_wrong_schema_version_is_refused():
    violations = check_policy(_manifest(lambda m: m.update(schema_version=2)))

    assert violations == ["schema_version 2 diferente de 1"]


def test_unreadable_manifest_exits_1(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")

    assert main(["verify", "--policy", str(path)]) == 1
    assert "não foi possível ler" in capsys.readouterr().err
