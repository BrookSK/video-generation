"""Piloto do pipeline: recorte, canvas, TTS, render e finalização com tempo e VRAM por estágio.

Uso: python -m avatar_worker.pilot --recipe ... --out <dir>

TTS e render rodam por subprocesso nos runtimes isolados, um de cada vez. Uma thread amostra
a VRAM a cada 0,5 s e registra o pico de cada estágio. O relatório fica em <out>/report.json;
falha de estágio grava o erro nele e sai 1 sem gerar final.mp4.
"""

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from PIL import Image

from avatar_worker.canvas import compose_canvas
from avatar_worker.cutout import ensure_alpha
from avatar_worker.finalize import build_finalize_args, probe_output, run_finalize
from avatar_worker.recipe import FORMATS, FPS, VOICES, Recipe, RecipeError, load_recipe

RUNTIMES_DIR = Path(__file__).resolve().parents[2] / "runtimes"
TTS_STAGE = RUNTIMES_DIR / "tts" / "tts_stage.py"
AVATAR_STAGE = RUNTIMES_DIR / "avatar" / "avatar_stage.py"
DEFAULT_TTS_PYTHON = RUNTIMES_DIR / "tts" / ".venv" / "bin" / "python"
DEFAULT_AVATAR_PYTHON = RUNTIMES_DIR / "avatar" / ".venv" / "bin" / "python"
DEFAULT_INFINITETALK_DIR = Path("/opt/infinitetalk")
DEFAULT_VRAM_COMMAND = "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
VRAM_INTERVAL_S = 0.5
NET_DIR = Path("/sys/class/net")
AVATAR_FIELDS = (
    "engine",
    "profile",
    "size",
    "sample_steps",
    "mode",
    "max_frame_num",
    "motion_frame",
    "quant",
    "num_persistent_param_in_dit",
    "prompt",
)

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


class StageError(RuntimeError):
    """Um runtime saiu com erro ou um resultado foi recusado."""


class StageFailure(Exception):
    """Falha de um estágio nomeado; o piloto grava o erro no relatório e sai 1."""

    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message


def _describe(exc: BaseException) -> str:
    message = str(exc) or type(exc).__name__
    stderr = getattr(exc, "stderr", None)
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    if stderr:
        message += "\n" + "\n".join(stderr.strip().splitlines()[-10:])
    return message


class StageMeter:
    """Mede segundos e pico de VRAM por estágio com uma thread que roda o comando de VRAM."""

    def __init__(self, command: list[str], interval: float):
        self._command = command
        self._interval = interval
        self._lock = threading.Lock()
        self._stage_id = 0
        self._active = False
        self._peak: float | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self) -> "StageMeter":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()

    def _read(self) -> float | None:
        try:
            completed = subprocess.run(
                self._command, shell=False, check=True, capture_output=True, text=True, timeout=10
            )
            values = [float(line) for line in completed.stdout.split()]
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        return sum(values) if values else None

    def _sample(self) -> None:
        with self._lock:
            if not self._active:
                return
            stage_id = self._stage_id
        value = self._read()
        with self._lock:
            if value is not None and self._active and stage_id == self._stage_id:
                self._peak = value if self._peak is None else max(self._peak, value)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._sample()

    @contextmanager
    def measure(self, stages: dict[str, Any], name: str) -> Iterator[None]:
        """Registra em stages[name] segundos e pico de VRAM; erro vira StageFailure(name)."""
        entry = stages.setdefault(name, {})
        with self._lock:
            self._stage_id += 1
            self._active = True
            self._peak = None
        started = time.monotonic()
        self._sample()
        try:
            yield
        except StageFailure:
            raise
        except Exception as exc:
            raise StageFailure(name, _describe(exc)) from exc
        finally:
            self._sample()
            with self._lock:
                self._active = False
                peak = self._peak
            entry.update(seconds=round(time.monotonic() - started, 3), vram_peak_mb=peak)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _network_interfaces() -> list[str] | None:
    if not NET_DIR.is_dir():
        return None
    return sorted(entry.name for entry in NET_DIR.iterdir())


def _pad_color(background: str | Image.Image) -> str:
    """Cor do pad: a do cenário, ou a cor média da imagem de fundo."""
    if isinstance(background, str):
        return background
    mean = background.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    return "#{:02x}{:02x}{:02x}".format(*mean)


def _run_stage(
    python: Path, script: Path, request: dict[str, Any], work_dir: Path, name: str
) -> dict[str, Any]:
    """Roda o adaptador no Python do runtime, sem shell, e devolve o result.json."""
    request_path = work_dir / f"{name}_request.json"
    result_path = work_dir / f"{name}_result.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    completed = subprocess.run(
        [str(python), str(script), str(request_path), str(result_path)], shell=False, check=False
    )
    if completed.returncode != 0:
        raise StageError(f"{script.name} saiu com código {completed.returncode}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def _voice_request(recipe: Recipe, voice: str) -> dict[str, Any]:
    spec = recipe.tts.voices[voice]
    request: dict[str, Any] = {"kind": spec.kind}
    if spec.kind == "reference":
        request.update(path=spec.path, sha256=spec.sha256)
    return request


def _run_once(
    args: argparse.Namespace,
    recipe: Recipe,
    meter: StageMeter,
    avatar: Image.Image,
    background: str | Image.Image,
    aspect: str,
    run: dict[str, Any],
    text: str,
    limits: dict[str, Any],
) -> None:
    stages: dict[str, Any] = run["stages"]
    work_dir = args.out / aspect.replace(":", "x") / f"run-{run['run']}"
    work_dir.mkdir(parents=True, exist_ok=True)
    canvas_path = work_dir / "canvas.png"
    final_path = work_dir / "final.mp4"

    with meter.measure(stages, "compose"):
        canvas = compose_canvas(avatar, background, args.composition[aspect], recipe.canvas[aspect])
        canvas.save(canvas_path)

    with meter.measure(stages, "tts"):
        tts = _run_stage(
            args.tts_python,
            TTS_STAGE,
            {
                "text": text,
                "language": recipe.tts.language,
                "models_dir": str(args.models),
                "out_wav": str(work_dir / "speech.wav"),
                "voice": _voice_request(recipe, args.voice),
            },
            work_dir,
            "tts",
        )
        stages["tts"]["runtime_peak_vram_mb"] = tts.get("peak_vram_mb")
        run["audio_seconds"] = tts["duration_s"]
        run["watermark_detected"] = tts["watermark_detected"]
        limit = limits["max_audio_seconds"]
        if tts["duration_s"] > limit:
            raise StageError(f"áudio de {tts['duration_s']} s acima do limite de {limit} s")

    with meter.measure(stages, "avatar"):
        render = _run_stage(
            args.avatar_python,
            AVATAR_STAGE,
            {
                "image": str(canvas_path),
                "audio": tts["audio_path"],
                "format": aspect,
                "models_dir": str(args.models),
                "infinitetalk_dir": str(args.infinitetalk_dir),
                "out_dir": str(work_dir),
                "recipe_avatar": {
                    **{field: getattr(recipe.avatar, field) for field in AVATAR_FIELDS},
                    "max_frame_num": limits["max_frame_num"],
                },
            },
            work_dir,
            "avatar",
        )
        # O InfiniteTalk deixa embeddings e WAV em save_audio/; a limpeza é de quem chama.
        shutil.rmtree(work_dir / "save_audio", ignore_errors=True)
        run["native_width"] = render["native_width"]
        run["native_height"] = render["native_height"]
        run["frames"] = render["frames"]

    with meter.measure(stages, "finalize"):
        finalize_args = build_finalize_args(
            render["video_path"],
            tts["audio_path"],
            final_path,
            recipe.canvas[aspect],
            _pad_color(background),
            recipe.output,
        )
        try:
            run_finalize(finalize_args)
            profile = probe_output(final_path)
        except Exception:
            final_path.unlink(missing_ok=True)
            raise

    run["final"] = profile
    run["final_path"] = str(final_path)
    run["final_sha256"] = _sha256(final_path)
    run["compute_seconds"] = round(sum(stage["seconds"] for stage in stages.values()), 3)
    video_seconds = profile["duration"]
    run["seconds_per_video_second"] = (
        round(run["compute_seconds"] / video_seconds, 3) if video_seconds else None
    )


def _ratios(runs: list[dict[str, Any]]) -> dict[str, float | None]:
    ratios = [run.get("seconds_per_video_second") for run in runs]
    warm = [ratio for ratio in ratios[1:] if ratio is not None]
    return {
        "cold": ratios[0] if ratios else None,
        "warm": round(sum(warm) / len(warm), 3) if warm else None,
    }


def _write_report(out: Path, report: dict[str, Any]) -> None:
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_pilot(args: argparse.Namespace, recipe: Recipe, text: str) -> int:
    max_audio_seconds = args.max_audio_seconds or recipe.limits.max_audio_seconds
    report: dict[str, Any] = {
        "status": "running",
        "recipe": recipe.name,
        "recipe_status": recipe.status,
        "recipe_sha256": _sha256(args.recipe),
        "avatar_profile": recipe.avatar.profile,
        "worker_image": os.environ.get("WORKER_IMAGE_DIGEST"),
        "network_interfaces": _network_interfaces(),
        "vram_command": args.vram_command,
        "text": {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "chars": len(text)},
        "voice": args.voice,
        "limits": {
            "max_audio_seconds": max_audio_seconds,
            "recipe_max_audio_seconds": recipe.limits.max_audio_seconds,
            "max_frame_num": math.ceil(max_audio_seconds * FPS),
        },
        "cutout": {},
        "formats": {},
        "error": None,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    aspect, run_number = None, None
    with StageMeter(args.vram_command, VRAM_INTERVAL_S) as meter:
        try:
            with meter.measure(report["cutout"], "cutout"):
                background = args.background
                if not _HEX_COLOR.fullmatch(background):
                    background = Image.open(background)
                with Image.open(args.image) as image:
                    avatar = ensure_alpha(image)
            for aspect in args.formats:
                runs: list[dict[str, Any]] = []
                report["formats"][aspect] = {
                    "canvas": list(recipe.canvas[aspect]),
                    "bucket": list(recipe.avatar.buckets[aspect]),
                    "runs": runs,
                }
                for run_number in range(1, args.runs + 1):
                    run = {
                        "run": run_number,
                        "load": "cold" if run_number == 1 else "warm",
                        "stages": {},
                    }
                    runs.append(run)
                    _run_once(
                        args, recipe, meter, avatar, background, aspect, run, text, report["limits"]
                    )
                report["formats"][aspect]["seconds_per_video_second"] = _ratios(runs)
        except StageFailure as exc:
            report["status"] = "failed"
            report["error"] = {
                "stage": exc.stage,
                "format": aspect,
                "run": run_number,
                "message": exc.message,
            }
            _write_report(args.out, report)
            print(f"piloto falhou no estágio {exc}", file=sys.stderr)
            return 1
    report["status"] = "ok"
    _write_report(args.out, report)
    print(f"piloto concluído: {args.out / 'report.json'}")
    return 0


def _parse_formats(value: str) -> list[str]:
    formats = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in formats if item not in FORMATS]
    if not formats or unknown or len(set(formats)) != len(formats):
        raise argparse.ArgumentTypeError(f"formatos precisam vir de {', '.join(FORMATS)}")
    return formats


def _parse_composition(value: str) -> dict[str, Any]:
    try:
        composition = json.loads(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"composition não é JSON: {exc}") from exc
    if not isinstance(composition, dict):
        raise argparse.ArgumentTypeError("composition precisa ser um objeto por formato")
    return composition


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("precisa ser inteiro >= 1")
    return number


def _positive_float(value: str) -> float:
    number = float(value)
    if not number > 0:
        raise argparse.ArgumentTypeError("precisa ser número positivo")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="avatar_worker.pilot", description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True, help="arquivo RECIPE-vN.json")
    parser.add_argument("--manifest", type=Path, required=True, help="MODEL_MANIFEST.json")
    parser.add_argument("--models", type=Path, required=True, help="diretório dos pesos")
    parser.add_argument("--image", type=Path, required=True, help="imagem autorizada do avatar")
    parser.add_argument("--background", required=True, help="cor #RRGGBB ou imagem de fundo")
    parser.add_argument(
        "--composition",
        type=_parse_composition,
        required=True,
        help='JSON de scenes.composition, ex. {"9:16": {"scale": 0.8, "x": 0.5, "y": 1.0}}',
    )
    parser.add_argument("--text-file", type=Path, required=True, help="fala em UTF-8")
    parser.add_argument("--voice", choices=VOICES, required=True)
    parser.add_argument("--formats", type=_parse_formats, default=list(FORMATS))
    parser.add_argument(
        "--runs", type=_positive_int, default=1, help="a primeira é fria, as seguintes quentes"
    )
    parser.add_argument(
        "--max-audio-seconds",
        type=_positive_float,
        help="só calibração; substitui o limite da receita e fica no relatório",
    )
    parser.add_argument("--out", type=Path, required=True, help="diretório de saída")
    parser.add_argument("--tts-python", type=Path, default=DEFAULT_TTS_PYTHON)
    parser.add_argument("--avatar-python", type=Path, default=DEFAULT_AVATAR_PYTHON)
    parser.add_argument("--infinitetalk-dir", type=Path, default=DEFAULT_INFINITETALK_DIR)
    parser.add_argument("--vram-command", type=shlex.split, default=DEFAULT_VRAM_COMMAND)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for aspect in args.formats:
        if not isinstance(args.composition.get(aspect), dict):
            parser.error(f"composition sem o objeto do formato {aspect}")
    if not _HEX_COLOR.fullmatch(args.background) and not Path(args.background).is_file():
        parser.error(f"fundo precisa ser cor #RRGGBB ou imagem existente ({args.background!r})")
    text = args.text_file.read_text(encoding="utf-8").rstrip("\r\n")
    if not text.strip():
        parser.error("a fala está vazia")
    try:
        recipe = load_recipe(args.recipe, args.manifest)
    except RecipeError as exc:
        print(f"Receita recusada:\n{exc}", file=sys.stderr)
        return 1
    return run_pilot(args, recipe, text)


if __name__ == "__main__":
    sys.exit(main())
