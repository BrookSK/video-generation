"""Estágio avatar_engine: request.json vira o MP4 do InfiniteTalk e result.json.

Uso: python avatar_stage.py <request.json> <result.json>

Roda com o Python 3.10 do runtime isolado. O topo só importa a biblioteca padrão; torch
e o InfiniteTalk rodam no subprocesso de generate_infinitetalk.py.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

FORMATS = ("9:16", "16:9")
OFFLINE_ENV = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
REQUEST_PATHS = ("image", "audio", "models_dir", "infinitetalk_dir", "out_dir")
RECIPE_FIELDS = ("size", "sample_steps", "mode", "motion_frame", "max_frame_num", "prompt")

# Pesos em /models/<componente>/<arquivo do manifesto>.
WAN_DIR = "wan2.1-i2v-14b-480p"
WAV2VEC_DIR = "chinese-wav2vec2-base"
INFINITETALK_WEIGHTS = "infinitetalk-weights/single/infinitetalk.safetensors"
# O InfiniteTalk lê t5_<quant>.safetensors e o mapa .json no mesmo diretório deste arquivo.
QUANT_WEIGHTS = "infinitetalk-weights/quant_models/infinitetalk_single_{quant}.safetensors"


class StageError(Exception):
    """Pedido inválido ou render falho; o estágio sai com código 1."""


def read_request(path: Path) -> dict[str, Any]:
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StageError(f"request.json ilegível: {exc}") from exc
    if not isinstance(request, dict):
        raise StageError("request.json precisa ser um objeto")
    for key in REQUEST_PATHS:
        value = request.get(key)
        if not isinstance(value, str) or not value.strip():
            raise StageError(f"request.{key} precisa ser texto não vazio")
    if request.get("format") not in FORMATS:
        raise StageError(f"request.format precisa ser um de {', '.join(FORMATS)}")
    avatar = request.get("recipe_avatar")
    if not isinstance(avatar, dict):
        raise StageError("request.recipe_avatar precisa ser um objeto")
    missing = [key for key in RECIPE_FIELDS if avatar.get(key) is None]
    if missing:
        raise StageError(f"request.recipe_avatar sem {', '.join(missing)}")
    return request


def output_paths(request: dict[str, Any]) -> tuple[Path, Path]:
    """Devolve o input_json e o --save_file (sem .mp4) dentro de out_dir."""
    out_dir = Path(request["out_dir"])
    tag = request["format"].replace(":", "x")
    return out_dir / f"infinitetalk_input_{tag}.json", out_dir / f"avatar_{tag}"


def build_input_json(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": request["recipe_avatar"]["prompt"],
        "cond_video": request["image"],
        "cond_audio": {"person1": request["audio"]},
    }


def build_args(request: dict[str, Any]) -> list[str]:
    """Argumentos de generate_infinitetalk.py vindos da receita e de caminhos em models_dir."""
    avatar = request["recipe_avatar"]
    models_dir = Path(request["models_dir"])
    input_json, save_file = output_paths(request)
    args = [
        "--ckpt_dir",
        str(models_dir / WAN_DIR),
        "--wav2vec_dir",
        str(models_dir / WAV2VEC_DIR),
        "--infinitetalk_dir",
        str(models_dir / INFINITETALK_WEIGHTS),
    ]
    quant = avatar.get("quant")
    if quant is not None:
        args += [
            "--quant",
            quant,
            "--quant_dir",
            str(models_dir / QUANT_WEIGHTS.format(quant=quant)),
        ]
    args += [
        "--size",
        avatar["size"],
        "--sample_steps",
        str(avatar["sample_steps"]),
        "--mode",
        avatar["mode"],
        "--motion_frame",
        str(avatar["motion_frame"]),
        "--max_frame_num",
        str(avatar["max_frame_num"]),
    ]
    persistent = avatar.get("num_persistent_param_in_dit")
    if persistent is not None:
        args += ["--num_persistent_param_in_dit", str(persistent)]
    args += ["--input_json", str(input_json), "--save_file", str(save_file)]
    return args


def probe_video(path: Path) -> tuple[int, int, int]:
    """Largura, altura e quadros do primeiro fluxo de vídeo, lidos com ffprobe."""
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=width,height,nb_read_packets",
            "-of",
            "json",
            str(path),
        ],
        shell=False,
        check=True,
        capture_output=True,
        text=True,
    )
    (stream,) = json.loads(completed.stdout)["streams"]
    return int(stream["width"]), int(stream["height"]), int(stream["nb_read_packets"])


def run(request_path: Path, result_path: Path) -> dict[str, Any]:
    started = time.monotonic()
    request = read_request(request_path)
    input_json, save_file = output_paths(request)
    input_json.parent.mkdir(parents=True, exist_ok=True)
    input_json.write_text(
        json.dumps(build_input_json(request), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    script = Path(request["infinitetalk_dir"]) / "generate_infinitetalk.py"
    env = dict(os.environ, **{name: "1" for name in OFFLINE_ENV})
    # cwd em out_dir: o InfiniteTalk grava save_audio/ relativo ao diretório atual.
    completed = subprocess.run(
        [sys.executable, str(script), *build_args(request)],
        shell=False,
        cwd=input_json.parent,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise StageError(f"generate_infinitetalk.py saiu com código {completed.returncode}")
    video = save_file.with_name(save_file.name + ".mp4")
    if not video.is_file():
        raise StageError(f"MP4 do InfiniteTalk ausente: {video}")
    width, height, frames = probe_video(video)
    result = {
        "video_path": str(video),
        "native_width": width,
        "native_height": height,
        "frames": frames,
        "elapsed_s": round(time.monotonic() - started, 3),
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("uso: avatar_stage.py <request.json> <result.json>", file=sys.stderr)
        return 2
    try:
        run(Path(args[0]), Path(args[1]))
    except (StageError, subprocess.CalledProcessError) as exc:
        print(f"avatar_stage: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
