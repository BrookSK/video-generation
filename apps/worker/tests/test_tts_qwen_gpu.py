"""Estágio Qwen real com os pesos de PILOT_MODELS e o Python do runtime qwen-tts."""

import json
import os
import subprocess
import wave
from pathlib import Path

import pytest

from avatar_worker.pilot import DEFAULT_QWEN_TTS_PYTHON, TTS_STAGE

pytestmark = pytest.mark.gpu

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = json.loads((ROOT / "docs" / "models" / "MODEL_MANIFEST.json").read_text())
FABER = next(
    entry
    for component in MANIFEST["components"]
    if component["id"] == "qwen-voice-references"
    for entry in component["files"]
    if entry["path"] == "faber.wav"
)
TEXT = "No dia 15 de março de 2027 entregamos 1.250 apartamentos, com parcelas de R$ 1.890."
SAMPLER = {
    "seed": 20261015,
    "temperature": 0.9,
    "top_p": 1.0,
    "top_k": 50,
    "repetition_penalty": 1.5,
    "repetition_window": 64,
    "max_new_tokens": 512,
}


def test_real_qwen_stage_finishes_with_eos_and_null_watermark(tmp_path):
    models = os.environ.get("PILOT_MODELS")
    python = Path(os.environ.get("QWEN_TTS_PYTHON", DEFAULT_QWEN_TTS_PYTHON))
    if not (models and Path(models).is_dir() and python.is_file()):
        pytest.skip("PILOT_MODELS e o Python do runtime qwen-tts precisam existir")
    request = {
        "engine": "qwen3-tts-base",
        "text": TEXT,
        "language": "pt",
        "voice": {
            "kind": "reference",
            "path": "qwen-voice-references/faber.wav",
            "sha256": FABER["sha256"],
            "transcript": FABER["provenance"]["text"],
        },
        "sampler": SAMPLER,
        "models_dir": models,
        "out_wav": str(tmp_path / "speech.wav"),
    }
    request_path, result_path = tmp_path / "request.json", tmp_path / "result.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

    completed = subprocess.run(
        [str(python), str(TTS_STAGE), str(request_path), str(result_path)], check=False
    )

    assert completed.returncode == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["watermark_detected"] is None
    assert result["sample_rate"] == 24000
    # 512 tokens a 12,5 Hz: a fala com EOS termina antes de 40,96 s.
    assert 1.0 < result["duration_s"] < 512 / 12.5
    with wave.open(result["audio_path"], "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24000)
