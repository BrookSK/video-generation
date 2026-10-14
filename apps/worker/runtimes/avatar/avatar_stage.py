"""Estágio avatar_engine: request.json vira o MP4 do InfiniteTalk e result.json.

Uso: python avatar_stage.py <request.json> <result.json>

Roda com o Python 3.10 do runtime isolado. O topo só importa a biblioteca padrão; torch
e o InfiniteTalk rodam no subprocesso de generate_infinitetalk.py.
"""

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

FORMATS = ("9:16", "16:9")
OFFLINE_ENV = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
# get_attn_map_with_target do InfiniteTalk usa @torch.compile; o Triton precisa de compilador C
# em tempo de execução, que a imagem não tem. Com o dynamo desligado a função roda em eager.
SUBPROCESS_ENV = {**{name: "1" for name in OFFLINE_ENV}, "TORCHDYNAMO_DISABLE": "1"}
REQUEST_PATHS = ("image", "audio", "models_dir", "infinitetalk_dir", "out_dir")
RECIPE_FIELDS = ("size", "sample_steps", "mode", "motion_frame", "max_frame_num", "prompt")
# Sempre explícitas: os defaults do CLI (texto 5.0, áudio 4.0) não são os da receita.
GUIDE_FIELDS = ("sample_text_guide_scale", "sample_audio_guide_scale")

# Pesos em /models/<componente>/<arquivo do manifesto>.
WAN_DIR = "wan2.1-i2v-14b-480p"
WAV2VEC_DIR = "chinese-wav2vec2-base"
INFINITETALK_WEIGHTS = "infinitetalk-weights/single/infinitetalk.safetensors"


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
    check_profile(avatar)
    return request


def _finite_positive(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def check_profile(avatar: dict[str, Any]) -> None:
    """Recusa o perfil que a imagem não roda ou que o CLI fixado ignoraria, sem trocar de perfil."""
    if avatar.get("quant") is not None:
        raise StageError(
            f"quant {avatar['quant']!r} não roda nesta imagem: a quantização compila a extensão "
            "CUDA do optimum-quanto na primeira inferência e a imagem não tem nvcc; use quant null"
        )
    negative = avatar.get("negative_prompt")
    if negative is not None and (not isinstance(negative, str) or negative.strip()):
        raise StageError(
            "negative_prompt não é aceito: o generate_infinitetalk.py fixado (50aa0a94) não tem "
            "esse argumento"
        )
    steps = avatar["sample_steps"]
    if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
        raise StageError(f"sample_steps precisa ser inteiro positivo (recebido {steps!r})")
    for key in GUIDE_FIELDS:
        if not _finite_positive(avatar.get(key)):
            raise StageError(f"{key} precisa ser número finito e positivo ({avatar.get(key)!r})")
    if "lora" not in avatar:
        raise StageError("request.recipe_avatar sem lora (null para perfil sem LoRA)")
    lora = avatar["lora"]
    if lora is None:
        return
    if not isinstance(lora, dict) or not all(
        isinstance(lora.get(key), str) and lora[key] for key in ("component", "file", "sha256")
    ):
        raise StageError("recipe_avatar.lora precisa de component, file e sha256")
    relative = PurePosixPath(lora["component"], lora["file"])
    if relative.is_absolute() or ".." in relative.parts:
        raise StageError(f"recipe_avatar.lora fora de models_dir: {relative}")
    if not _finite_positive(lora.get("scale")):
        raise StageError(f"lora.scale precisa ser número finito e positivo ({lora.get('scale')!r})")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def lora_path(request: dict[str, Any]) -> Path | None:
    """LoRA em models_dir/<componente>/<arquivo>, ou None no perfil declarado sem LoRA."""
    lora = request["recipe_avatar"]["lora"]
    if lora is None:
        return None
    return Path(request["models_dir"]) / lora["component"] / lora["file"]


def verify_lora(request: dict[str, Any]) -> None:
    """Confere arquivo e sha256 da LoRA antes do gerador; nunca roda sem ela."""
    path = lora_path(request)
    if path is None:
        return
    if not path.is_file():
        raise StageError(f"LoRA ausente: {path}")
    expected = request["recipe_avatar"]["lora"]["sha256"].lower()
    actual = sha256_file(path)
    if actual != expected:
        raise StageError(
            f"sha256 da LoRA {path.name} diverge: esperado {expected}, obtido {actual}"
        )


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
    args += [
        "--size",
        avatar["size"],
        "--sample_steps",
        str(avatar["sample_steps"]),
        "--sample_text_guide_scale",
        str(avatar["sample_text_guide_scale"]),
        "--sample_audio_guide_scale",
        str(avatar["sample_audio_guide_scale"]),
        "--mode",
        avatar["mode"],
        "--motion_frame",
        str(avatar["motion_frame"]),
        "--max_frame_num",
        str(avatar["max_frame_num"]),
    ]
    lora = lora_path(request)
    if lora is not None:
        args += ["--lora_dir", str(lora), "--lora_scale", str(avatar["lora"]["scale"])]
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
    # Caminhos relativos são do processo chamador, não do cwd isolado do gerador.
    request = {**request, **{key: str(Path(request[key]).resolve()) for key in REQUEST_PATHS}}
    verify_lora(request)
    input_json, save_file = output_paths(request)
    input_json.parent.mkdir(parents=True, exist_ok=True)
    input_json.write_text(
        json.dumps(build_input_json(request), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    script = Path(request["infinitetalk_dir"]) / "generate_infinitetalk.py"
    env = dict(os.environ, **SUBPROCESS_ENV)
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
