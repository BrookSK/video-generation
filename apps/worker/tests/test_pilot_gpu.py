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
# Um formato por amostra, com a calibração da receita e uma voz em cada.
SAMPLES = [("retrato", "9:16", "feminina"), ("paisagem", "16:9", "masculina")]
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
    queue = tmp_path / "fila.json"
    samples = [
        {
            "id": sample_id,
            "image": image,
            "background": "#1f2937",
            "text": SPEECH,
            "voice": voice,
            "format": aspect,
        }
        for sample_id, aspect, voice in SAMPLES
    ]
    queue.write_text(json.dumps({"samples": samples}, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"

    completed = subprocess.run(
        [
            sys.executable, "-m", "avatar_worker.pilot",
            "--recipe", str(RECIPE_PATH),
            "--manifest", str(MANIFEST_PATH),
            "--models", models,
            "--queue", str(queue),
            "--out", str(out),
        ],
        shell=False,
        check=False,
    )  # fmt: skip

    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    reports = [
        json.loads((out / entry["report"]).read_text(encoding="utf-8"))
        for entry in index["samples"]
    ]
    assert completed.returncode == 0, [report["error"] for report in reports]
    assert index["status"] == "ok"
    assert [(report["id"], report["format"], report["voice"]) for report in reports] == SAMPLES
    for report in reports:
        aspect = report["format"]
        assert report["status"] == "ok"
        assert report["composition"]["source"] == "recipe"
        assert report["text"]["chars"] == len(SPEECH)
        (run,) = report["runs"]
        assert list(run["stages"]) == ["compose", "tts", "avatar", "finalize"]
        assert run["stages"]["avatar"]["vram_peak_mb"] > 0
        assert run["stages"]["tts"]["vram_peak_mb"] > 0
        assert 0 < run["audio_seconds"] <= report["limits"]["max_audio_seconds"]
        assert run["watermark_detected"] is True
        assert run["frames"] > 0
        assert run["canvas_cut_px"] == 0
        assert report["render_input"]["canvas_cut_px"] == 0
        assert (run["final"]["width"], run["final"]["height"]) == CANVAS[aspect]
        assert run["final"]["video_codec"] == "h264"
        assert run["final"]["pix_fmt"] == "yuv420p"
        assert run["final"]["sample_rate"] == 48000
        final = Path(run["final_path"])
        assert run["final_sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
        assert report["seconds_per_video_second"]["cold"] > 0
