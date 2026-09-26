"""Piloto real no servidor GPU do cliente, com pesos em PILOT_MODELS e imagem em PILOT_IMAGE."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gpu

ROOT = Path(__file__).resolve().parents[3]
RECIPE_PATH = ROOT / "docs" / "models" / "RECIPE-v1.json"
MANIFEST_PATH = ROOT / "docs" / "models" / "MODEL_MANIFEST.json"
COMPOSITION = {
    "9:16": {"scale": 0.8, "x": 0.5, "y": 1.0},
    "16:9": {"scale": 0.9, "x": 0.5, "y": 1.0},
}
CANVAS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
SPEECH = (
    "Olá, eu sou a Mariana Albuquerque, da Construtora Horizonte. No dia 15 de março de 2027 "
    "entregamos 1.250 apartamentos em São José dos Campos, com parcelas a partir de R$ 1.890 "
    "por mês. Não perca: ligue para 0800 721 4400 ou fale com o Ricardo Tavares pelo site."
)


def test_real_pilot_generates_both_formats_with_measurements(tmp_path):
    models = os.environ.get("PILOT_MODELS")
    image = os.environ.get("PILOT_IMAGE")
    if not (models and image and Path(models).is_dir() and Path(image).is_file()):
        pytest.skip("PILOT_MODELS e PILOT_IMAGE precisam apontar para os pesos e a imagem")
    text_file = tmp_path / "fala.txt"
    text_file.write_text(SPEECH, encoding="utf-8")
    out = tmp_path / "out"

    completed = subprocess.run(
        [
            sys.executable, "-m", "avatar_worker.pilot",
            "--recipe", str(RECIPE_PATH),
            "--manifest", str(MANIFEST_PATH),
            "--models", models,
            "--image", image,
            "--background", "#1f2937",
            "--composition", json.dumps(COMPOSITION),
            "--text-file", str(text_file),
            "--voice", "feminina",
            "--formats", "9:16,16:9",
            "--out", str(out),
        ],
        shell=False,
        check=False,
    )  # fmt: skip

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert completed.returncode == 0, report["error"]
    assert report["status"] == "ok"
    assert report["text"]["chars"] == len(SPEECH)
    assert set(report["formats"]) == {"9:16", "16:9"}
    for aspect, summary in report["formats"].items():
        (run,) = summary["runs"]
        assert list(run["stages"]) == ["compose", "tts", "avatar", "finalize"]
        assert run["stages"]["avatar"]["vram_peak_mb"] > 0
        assert run["stages"]["tts"]["vram_peak_mb"] > 0
        assert 0 < run["audio_seconds"] <= report["limits"]["max_audio_seconds"]
        assert run["watermark_detected"] is True
        assert run["frames"] > 0
        assert (run["final"]["width"], run["final"]["height"]) == CANVAS[aspect]
        assert run["final"]["video_codec"] == "h264"
        assert run["final"]["pix_fmt"] == "yuv420p"
        assert run["final"]["sample_rate"] == 48000
        final = Path(run["final_path"])
        assert run["final_sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
        assert summary["seconds_per_video_second"]["cold"] > 0
