import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from avatar_worker.manifest import check_policy, load_manifest, main

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

REAL_MANIFEST = load_manifest(
    Path(__file__).resolve().parents[3] / "docs" / "models" / "MODEL_MANIFEST.json"
)
LORA_FILE = "Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors"
# Referência de voz derivada das fontes Kokoro reais; hash, tamanho e texto são sintéticos.
DERIVED = {
    "id": "referencias-de-teste",
    "kind": "derived",
    "code_license": "Apache-2.0",
    "weights_license": "Apache-2.0",
    "commercial_use": True,
    "license_evidence": ["https://github.com/hexgrad/kokoro/blob/x/LICENSE"],
    "derived_from": ["kokoro-code", "kokoro-82m"],
    "files": [
        {
            "path": "pf_dora.wav",
            "sha256": SHA256,
            "size": 4096,
            "provenance": {
                "model": "kokoro-82m/kokoro-v1_0.pth",
                "preset": "kokoro-82m/voices/pf_dora.pt",
                "text": "Referência sintética de voz em português.",
                "parameters": {"lang_code": "p", "sample_rate": 24000},
            },
        }
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
        (_set(1, "id", "../x"), "../x: id fora do formato"),
        (_set(1, "id", "/x"), "/x: id fora do formato"),
        (_set(1, "id", "../../tmp/escape"), "../../tmp/escape: id fora do formato"),
        (_set(1, "id", "Rembg"), "Rembg: id fora do formato"),
        (
            _set(1, "license_evidence", ["http://github.com/danielgatis/rembg/blob/x/LICENSE"]),
            "rembg: license_evidence #0: url sem https",
        ),
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


def _real_with_derived(mutate=None):
    """Manifesto real mais um derived das fontes Kokoro; mutate recebe os componentes por id."""
    manifest = copy.deepcopy(REAL_MANIFEST)
    manifest["components"].append(copy.deepcopy(DERIVED))
    if mutate:
        mutate({component["id"]: component for component in manifest["components"]})
    return manifest


def test_real_manifest_accepts_local_derived_from_kokoro_sources(tmp_path, capsys):
    path = _write(tmp_path, _real_with_derived())

    assert main(["verify", "--policy", str(path)]) == 0
    out = capsys.readouterr().out
    assert "referencias-de-teste (derived)" in out
    assert "origem kokoro-code, kokoro-82m, 1 arquivo(s)" in out


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda c: c["lightx2v-lora"].update(weights_license="CC-BY-NC-4.0"),
            ["lightx2v-lora: weights_license 'CC-BY-NC-4.0' não é permitida"],
        ),
        (
            lambda c: c["lightx2v-lora"].update(weights_license=None),
            ["lightx2v-lora: weights_license None não é permitida"],
        ),
        (
            lambda c: c["lightx2v-lora"].pop("license_evidence"),
            ["lightx2v-lora: license_evidence precisa ser uma lista não vazia de URLs https"],
        ),
        (
            lambda c: c["lightx2v-lora"].update(kind="derived"),
            [
                "lightx2v-lora: derived_from precisa listar componentes não derivados",
                f"lightx2v-lora: arquivo {LORA_FILE}: derivado local não tem url de download",
                f"lightx2v-lora: arquivo {LORA_FILE} sem provenance",
            ],
        ),
        (
            lambda c: c["referencias-de-teste"].update(weights_license="CC-BY-NC-4.0"),
            ["referencias-de-teste: weights_license 'CC-BY-NC-4.0' não é permitida"],
        ),
        (
            lambda c: c["referencias-de-teste"].update(
                derived_from=["referencias-de-teste", "kokoro-82m-v2"]
            ),
            [
                "derived_from 'referencias-de-teste' não é componente não derivado do manifesto",
                "derived_from 'kokoro-82m-v2' não é componente não derivado do manifesto",
            ],
        ),
        (
            lambda c: c["referencias-de-teste"]["files"][0]["provenance"].update(
                text=" ", parameters={}
            ),
            [
                "referencias-de-teste: arquivo pf_dora.wav sem provenance.text",
                "referencias-de-teste: arquivo pf_dora.wav sem provenance.parameters",
            ],
        ),
        (
            lambda c: c["referencias-de-teste"]["files"][0]["provenance"].update(
                model=f"lightx2v-lora/{LORA_FILE}"
            ),
            [f"provenance.model 'lightx2v-lora/{LORA_FILE}' não é arquivo de derived_from"],
        ),
        (
            lambda c: c["referencias-de-teste"]["files"][0].update(path="../pf_dora.wav"),
            ["arquivo ../pf_dora.wav: caminho fora de referencias-de-teste/"],
        ),
    ],
    ids=[
        "lora-nao-comercial",
        "lora-sem-licenca",
        "lora-sem-evidencia",
        "lora-como-derivado",
        "derivado-nao-comercial",
        "origem-derivada-ou-ausente",
        "proveniencia-incompleta",
        "proveniencia-fora-da-origem",
        "caminho-fora-do-componente",
    ],
)
def test_real_lora_and_derived_refusals_are_named(tmp_path, capsys, mutate, expected):
    path = _write(tmp_path, _real_with_derived(mutate))

    assert main(["verify", "--policy", str(path)]) == 1
    err = capsys.readouterr().err
    for message in expected:
        assert message in err


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


# Gravação humana CC0 e a referência PCM16 convertida dela; hashes e textos sintéticos.
RECORDING = {
    "id": "gravacao-de-teste",
    "kind": "model",
    "url": "https://github.com/OHF-Voice/voice-datasets",
    "revision": COMMIT,
    "code_license": "CC0-1.0",
    "weights_license": "CC0-1.0",
    "commercial_use": True,
    "license_evidence": ["https://github.com/OHF-Voice/voice-datasets/blob/x/README.md"],
    "files": [
        {
            "path": "pt_BR/locutor/0000000001.mp3",
            "url": "https://raw.githubusercontent.com/OHF-Voice/voice-datasets/x/0000000001.mp3",
            "sha256": SHA256,
            "size": 512,
        }
    ],
}
CONVERTED = {
    "id": "referencias-convertidas",
    "kind": "derived",
    "code_license": "CC0-1.0",
    "weights_license": "CC0-1.0",
    "commercial_use": True,
    "license_evidence": ["https://github.com/OHF-Voice/voice-datasets/blob/x/README.md"],
    "derived_from": ["gravacao-de-teste"],
    "files": [
        {
            "path": "locutor.wav",
            "sha256": SHA256,
            "size": 1024,
            "provenance": {
                "source": "gravacao-de-teste/pt_BR/locutor/0000000001.mp3",
                "text": "Transcrição da gravação de referência.",
                "parameters": {"sample_rate": 24000, "pcm": "s16le"},
            },
        }
    ],
}


def _with_recording(mutate=None):
    manifest = _manifest()
    manifest["components"] += [copy.deepcopy(RECORDING), copy.deepcopy(CONVERTED)]
    if mutate:
        mutate({component["id"]: component for component in manifest["components"]})
    return manifest


def test_cc0_recording_and_reference_converted_from_it_are_accepted():
    assert check_policy(_with_recording()) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda c: c["gravacao-de-teste"].update(weights_license="CC-BY-NC-4.0"),
            "gravacao-de-teste: weights_license 'CC-BY-NC-4.0' não é permitida",
        ),
        (
            lambda c: c["referencias-convertidas"]["files"][0]["provenance"].update(
                source="gravacao-de-teste/pt_BR/outro/0000000002.mp3"
            ),
            "provenance.source 'gravacao-de-teste/pt_BR/outro/0000000002.mp3' não é arquivo "
            "de derived_from",
        ),
        (
            lambda c: c["referencias-convertidas"]["files"][0]["provenance"].pop("source"),
            "provenance.model None não é arquivo de derived_from",
        ),
    ],
    ids=["gravacao-nao-comercial", "origem-fora-da-gravacao", "sem-origem-citada"],
)
def test_converted_reference_refusals_are_named(mutate, expected):
    violations = check_policy(_with_recording(mutate))

    assert any(expected in violation for violation in violations), violations


def _cc_by(components):
    for component in components.values():
        if component["id"] in ("gravacao-de-teste", "referencias-convertidas"):
            component.update(code_license="CC-BY-4.0", weights_license="CC-BY-4.0")
            component["attribution"] = "Corpus de teste, Autora et al., 2022."


def test_cc_by_recording_with_attribution_is_accepted():
    assert check_policy(_with_recording(_cc_by)) == []


def test_cc_by_without_attribution_is_refused():
    def mutate(components):
        _cc_by(components)
        del components["referencias-convertidas"]["attribution"]

    assert check_policy(_with_recording(mutate)) == [
        "referencias-convertidas: licença com atribuição exige o campo attribution"
    ]
