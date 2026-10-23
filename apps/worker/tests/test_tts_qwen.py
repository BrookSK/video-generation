import hashlib
import importlib.util
import json
import sys
import tomllib
import types
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
STAGE_PATH = ROOT / "apps" / "worker" / "runtimes" / "tts" / "tts_stage.py"
QWEN_RUNTIME = ROOT / "apps" / "worker" / "runtimes" / "qwen-tts"
MANIFEST = json.loads((ROOT / "docs" / "models" / "MODEL_MANIFEST.json").read_text())

_spec = importlib.util.spec_from_file_location("tts_stage_qwen", STAGE_PATH)
tts_stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tts_stage)

TEXT = "Quarto: verifique os é-pê-is, as ferramentas e os riscos de poeira e queda. R$ 1.890,00!"
TRANSCRIPT = (
    "Os descontos chegam a 78% e correspondem aos impostos que incidem sobre as mercadorias."
)
EOS = 2150
SAMPLER = {
    "seed": 20261015,
    "temperature": 0.9,
    "top_p": 1.0,
    "top_k": 50,
    "repetition_penalty": 1.5,
    "repetition_window": 64,
    "max_new_tokens": 512,
}


class FakeQwen:
    """Dublê do qwen_tts e do torch: o caminho de generate_voice_clone até talker.generate.

    O generate_voice_clone real repassa os parâmetros do talker para talker.generate e decodifica
    os códigos em float32 a 24 kHz; aqui o talker devolve as sequências pedidas pelo teste.
    """

    def __init__(self, sequences, wav=None):
        self.sequences = np.asarray(sequences, dtype=np.int64)
        self.wav = np.linspace(-1.2, 1.2, 4800, dtype=np.float32) if wav is None else wav
        self.loaded = None
        self.clone = None
        self.talker_kwargs = None
        self.seeds = []
        self.decoded = False

    def install(self, monkeypatch):
        fake = self

        class Talker:
            def generate(self, **kwargs):
                fake.talker_kwargs = kwargs
                return types.SimpleNamespace(sequences=fake.sequences)

        class Model:
            def __init__(self):
                self.talker = Talker()
                self.config = types.SimpleNamespace(
                    talker_config=types.SimpleNamespace(codec_eos_token_id=EOS)
                )

        class Qwen3TTSModel:
            def __init__(self):
                self.model = Model()

            @classmethod
            def from_pretrained(cls, path, **kwargs):
                fake.loaded = (path, kwargs)
                return cls()

            def generate_voice_clone(self, **kwargs):
                fake.clone = kwargs
                self.model.talker.generate(
                    inputs_embeds=None,
                    max_new_tokens=kwargs["max_new_tokens"],
                    repetition_penalty=kwargs["repetition_penalty"],
                    temperature=kwargs["temperature"],
                )
                fake.decoded = True
                return [fake.wav], 24000

        torch = types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda: False),
            manual_seed=fake.seeds.append,
            bfloat16="bfloat16",
            float32="float32",
        )
        monkeypatch.setitem(sys.modules, "torch", torch)
        monkeypatch.setitem(
            sys.modules, "qwen_tts", types.SimpleNamespace(Qwen3TTSModel=Qwen3TTSModel)
        )
        monkeypatch.setitem(
            sys.modules, "transformers", types.SimpleNamespace(LogitsProcessorList=list)
        )
        return self


def _weights(models_dir):
    for name in tts_stage.QWEN_FILES:
        path = models_dir / tts_stage.QWEN_COMPONENT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"peso sintetico")


def _request(tmp_path, **changes):
    models_dir = tmp_path / "models"
    reference = models_dir / "qwen-voice-references" / "faber.wav"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_bytes(b"RIFF referencia humana")
    _weights(models_dir)
    request = {
        "engine": "qwen3-tts-base",
        "text": TEXT,
        "language": "pt",
        "voice": {
            "kind": "reference",
            "path": "qwen-voice-references/faber.wav",
            "sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "transcript": TRANSCRIPT,
        },
        "sampler": dict(SAMPLER),
        "models_dir": str(models_dir),
        "out_wav": str(tmp_path / "out" / "speech.wav"),
    }
    request.update(changes)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    return path, models_dir


def _run(tmp_path, request_path):
    watermark_calls = []
    code = tts_stage.main(
        [str(request_path), str(tmp_path / "result.json")],
        detect_watermark=lambda path: watermark_calls.append(path) or True,
    )
    return code, watermark_calls


def test_qwen_receives_literal_text_reference_transcript_and_approved_sampler(
    tmp_path, monkeypatch
):
    fake = FakeQwen([[11, 12, EOS]]).install(monkeypatch)
    request_path, models_dir = _request(tmp_path)

    code, _ = _run(tmp_path, request_path)

    assert code == 0
    path, load = fake.loaded
    assert path == str(models_dir / "qwen3-tts-12hz-1.7b-base")
    assert load["local_files_only"] is True
    assert load["device_map"] == "cpu"
    assert fake.clone == {
        "text": TEXT,
        "language": "Portuguese",
        "ref_audio": str(models_dir / "qwen-voice-references" / "faber.wav"),
        "ref_text": TRANSCRIPT,
        "do_sample": True,
        "temperature": 0.9,
        "top_k": 50,
        "top_p": 1.0,
        "repetition_penalty": 1.0,
        "subtalker_dosample": True,
        "subtalker_temperature": 0.9,
        "subtalker_top_k": 50,
        "subtalker_top_p": 1.0,
        "max_new_tokens": 512,
    }
    assert fake.seeds == [20261015]


def test_talker_gets_windowed_penalty_instead_of_native_one(tmp_path, monkeypatch):
    fake = FakeQwen([[11, EOS]]).install(monkeypatch)
    request_path, _ = _request(tmp_path)

    code, _ = _run(tmp_path, request_path)

    assert code == 0
    assert fake.talker_kwargs["repetition_penalty"] == 1.0
    (penalty,) = fake.talker_kwargs["logits_processor"]
    assert isinstance(penalty, tts_stage.WindowedRepetitionPenalty)
    assert (penalty.penalty, penalty.window) == (1.5, 64)


def test_result_has_null_watermark_and_unaltered_pcm16(tmp_path, monkeypatch):
    fake = FakeQwen([[11, EOS]]).install(monkeypatch)
    request_path, _ = _request(tmp_path)

    code, watermark_calls = _run(tmp_path, request_path)

    assert code == 0
    assert watermark_calls == []
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["watermark_detected"] is None
    assert result["sample_rate"] == 24000
    assert result["duration_s"] == 0.2
    with wave.open(result["audio_path"], "rb") as audio:
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype=np.int16)
    expected = (np.clip(fake.wav, -1.0, 1.0) * 32767).astype(np.int16)
    assert np.array_equal(pcm, expected)


@pytest.mark.parametrize(
    "sequences",
    [
        pytest.param([[11] * 512], id="limite-sem-eos"),
        pytest.param([[EOS, 11]], id="eos-nao-terminal"),
        pytest.param([[]], id="vazio"),
        pytest.param([[11, EOS], [11, EOS]], id="lote-inesperado"),
    ],
)
def test_talker_without_terminal_eos_publishes_nothing(tmp_path, monkeypatch, capsys, sequences):
    fake = FakeQwen(sequences).install(monkeypatch)
    request_path, _ = _request(tmp_path)

    code, _ = _run(tmp_path, request_path)

    assert code == 1
    assert fake.decoded is False
    assert not (tmp_path / "out" / "speech.wav").exists()
    assert not (tmp_path / "result.json").exists()
    assert "talker" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"voice": {"kind": "default"}}, "não tem voz padrão"),
        ({"engine": "kokoro"}, "request.engine precisa ser um de"),
        ({"language": "en"}, "idioma 'en' sem nome no Qwen"),
        ({"sampler": {k: v for k, v in SAMPLER.items() if k != "seed"}}, "request.sampler"),
        ({"sampler": {**SAMPLER, "top_k": 50.5}}, "request.sampler.top_k inválido"),
    ],
    ids=["voz-padrao", "engine-desconhecida", "idioma", "sampler-incompleto", "top-k-fracionario"],
)
def test_invalid_qwen_request_exits_1_before_loading(
    tmp_path, monkeypatch, capsys, changes, message
):
    fake = FakeQwen([[11, EOS]]).install(monkeypatch)
    request_path, _ = _request(tmp_path, **changes)

    code, _ = _run(tmp_path, request_path)

    assert code == 1
    assert fake.loaded is None
    assert message in capsys.readouterr().err


def test_missing_transcript_exits_1_before_loading(tmp_path, monkeypatch, capsys):
    fake = FakeQwen([[11, EOS]]).install(monkeypatch)
    request_path, _ = _request(tmp_path)
    request = json.loads(request_path.read_text())
    del request["voice"]["transcript"]
    request_path.write_text(json.dumps(request), encoding="utf-8")

    code, _ = _run(tmp_path, request_path)

    assert code == 1
    assert fake.loaded is None
    assert "transcrição da referência" in capsys.readouterr().err


def test_missing_weight_is_named_without_loading(tmp_path, monkeypatch, capsys):
    fake = FakeQwen([[11, EOS]]).install(monkeypatch)
    request_path, models_dir = _request(tmp_path)
    (models_dir / "qwen3-tts-12hz-1.7b-base" / "speech_tokenizer" / "model.safetensors").unlink()

    code, _ = _run(tmp_path, request_path)

    assert code == 1
    assert fake.loaded is None
    assert "speech_tokenizer/model.safetensors" in capsys.readouterr().err


def test_windowed_penalty_follows_mlx_rule():
    penalty = tts_stage.WindowedRepetitionPenalty(1.5, 3)
    scores = np.array([[3.0, -3.0, 6.0, -6.0, 9.0]])
    # O token 4 saiu da janela dos 3 últimos; 1 aparece duas vezes e é penalizado uma vez.
    input_ids = np.array([[4, 1, 2, 1]])

    out = penalty(input_ids, scores)

    assert np.allclose(out, [[3.0, -4.5, 4.0, -6.0, 9.0]])


def test_windowed_penalty_ignores_empty_history():
    scores = np.array([[3.0, -3.0]])

    out = tts_stage.WindowedRepetitionPenalty(1.5, 64)(np.zeros((1, 0), dtype=np.int64), scores)

    assert np.array_equal(out, [[3.0, -3.0]])


def test_qwen_files_and_wheel_come_from_manifest():
    components = {component["id"]: component for component in MANIFEST["components"]}
    weights = {entry["path"] for entry in components["qwen3-tts-12hz-1.7b-base"]["files"]}
    assert set(tts_stage.QWEN_FILES) == weights

    lock = tomllib.loads((QWEN_RUNTIME / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == "qwen-tts")
    (expected,) = components["qwen-tts"]["files"]
    assert package["version"] == components["qwen-tts"]["version"]
    (wheel,) = package["wheels"]
    assert wheel["url"] == expected["url"]
    assert wheel["hash"] == f"sha256:{expected['sha256']}"
