"""Piloto do pipeline: fila de amostras com recorte, canvas, TTS, render e finalização.

Uso: python -m avatar_worker.pilot --recipe ... --queue <fila.json> --out <dir>

A fila é {"samples": [...]}. Cada amostra declara id, image, background (#RRGGBB ou imagem), a
fala em text ou em text_file (UTF-8, lido sem normalização), voice, format e, se quiser,
composition {scale, x, y}, que precede calibration.composition da receita. Caminhos relativos
partem da pasta da fila. A fila inteira é validada antes de executar, e --out já usado é recusado.

As amostras rodam na ordem da fila. TTS e render rodam por subprocesso nos runtimes isolados, um
de cada vez. Uma thread amostra a VRAM a cada 0,5 s e registra o pico de cada estágio. Cada
amostra grava <out>/<id>/run-N e <out>/<id>/report.json; <out>/index.json guarda a ordem e o
status. Falha de estágio fica no relatório da amostra, sem final.mp4; a fila segue e o comando
sai 1.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from avatar_worker.canvas import (
    BucketFrame,
    background_pad_color,
    bucket_frame,
    canvas_cut,
    compose_canvas,
    extend_to_bucket,
)
from avatar_worker.cutout import ensure_alpha
from avatar_worker.finalize import build_finalize_args, probe_output, run_finalize
from avatar_worker.manifest import check_policy, load_manifest
from avatar_worker.recipe import (
    COMPOSITION_RANGES,
    FORMATS,
    FPS,
    VOICES,
    Recipe,
    RecipeError,
    load_recipe,
)

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
    "lora",
    "sample_text_guide_scale",
    "sample_audio_guide_scale",
    "prompt",
    "negative_prompt",
)

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_SAMPLE_FIELDS = (
    "id",
    "image",
    "background",
    "text",
    "text_file",
    "voice",
    "format",
    "composition",
)
# O id vira a pasta <out>/<id>: sem separador de caminho nem ponto.
_SAMPLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class StageError(RuntimeError):
    """Um runtime saiu com erro ou um resultado foi recusado."""


class StageFailure(Exception):
    """Falha de um estágio nomeado; o piloto grava o erro no relatório da amostra e segue."""

    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message


class QueueError(Exception):
    """Fila recusada antes de executar; problems lista cada regra violada em português."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Sample:
    """Amostra validada da fila, com os caminhos já resolvidos a partir da pasta da fila."""

    id: str
    image: Path
    background: str | Path
    text: str
    voice: str
    format: str
    composition: dict[str, Any] | None


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
    sample: Sample,
    avatar: Image.Image,
    background: str | Image.Image,
    composition: dict[str, Any],
    frame: BucketFrame,
    run: dict[str, Any],
    limits: dict[str, Any],
) -> None:
    stages: dict[str, Any] = run["stages"]
    aspect = sample.format
    work_dir = args.out / sample.id / f"run-{run['run']}"
    work_dir.mkdir()
    canvas_path = work_dir / "canvas.png"
    render_input_path = work_dir / "render_input.png"
    final_path = work_dir / "final.mp4"
    canvas_size = recipe.canvas[aspect]
    pad_color = background_pad_color(background)

    with meter.measure(stages, "compose"):
        canvas = compose_canvas(avatar, background, composition, canvas_size)
        canvas.save(canvas_path)
        # O InfiniteTalk corta no centro o que sobra da razão do bucket; na razão exata não
        # sobra nada do canvas para cortar.
        extend_to_bucket(canvas, frame, pad_color).save(render_input_path)

    with meter.measure(stages, "tts"):
        tts = _run_stage(
            args.tts_python,
            TTS_STAGE,
            {
                "text": sample.text,
                "language": recipe.tts.language,
                "models_dir": str(args.models),
                "out_wav": str(work_dir / "speech.wav"),
                "voice": _voice_request(recipe, sample.voice),
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
                "image": str(render_input_path),
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
        native = (render["native_width"], render["native_height"])
        run["canvas_cut_px"] = canvas_cut(frame.size, frame.offset, canvas_size, native)
        if run["canvas_cut_px"]:
            raise StageError(
                f"render nativo {native[0]}x{native[1]} corta {run['canvas_cut_px']} px do canvas"
            )

    with meter.measure(stages, "finalize"):
        finalize_args = build_finalize_args(
            render["video_path"],
            tts["audio_path"],
            final_path,
            canvas_size,
            pad_color,
            recipe.output,
            frame,
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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_sample(
    args: argparse.Namespace,
    recipe: Recipe,
    meter: StageMeter,
    context: dict[str, Any],
    sample: Sample,
) -> dict[str, Any]:
    """Roda as execuções da amostra e grava <out>/<id>/report.json, com o erro se falhar."""
    aspect = sample.format
    if sample.composition is None:
        composition, source = dict(recipe.calibration.composition[aspect]), "recipe"
    else:
        composition, source = sample.composition, "sample"
    frame = bucket_frame(recipe.canvas[aspect], recipe.avatar.buckets[aspect])
    runs: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "status": "ok",
        "id": sample.id,
        "format": aspect,
        "voice": sample.voice,
        "image": str(sample.image),
        "background": str(sample.background),
        "composition": {**composition, "source": source},
        "text": {
            "sha256": hashlib.sha256(sample.text.encode("utf-8")).hexdigest(),
            "chars": len(sample.text),
        },
        **context,
        "cutout": {},
        "canvas": list(recipe.canvas[aspect]),
        "bucket": list(recipe.avatar.buckets[aspect]),
        "render_input": {
            "size": list(frame.size),
            "canvas_offset": list(frame.offset),
            "canvas_cut_px": frame.canvas_cut_px,
        },
        "runs": runs,
        "seconds_per_video_second": None,
        "error": None,
    }
    (args.out / sample.id).mkdir()
    run_number = None
    try:
        with meter.measure(report["cutout"], "cutout"):
            background: str | Image.Image
            if isinstance(sample.background, Path):
                with Image.open(sample.background) as image:
                    background = image.convert("RGB")
            else:
                background = sample.background
            with Image.open(sample.image) as image:
                avatar = ensure_alpha(image)
        for run_number in range(1, args.runs + 1):
            run = {"run": run_number, "load": "cold" if run_number == 1 else "warm", "stages": {}}
            runs.append(run)
            _run_once(
                args,
                recipe,
                meter,
                sample,
                avatar,
                background,
                composition,
                frame,
                run,
                context["limits"],
            )
    except StageFailure as exc:
        report["status"] = "failed"
        report["error"] = {"stage": exc.stage, "run": run_number, "message": exc.message}
        print(f"amostra {sample.id} falhou no estágio {exc}", file=sys.stderr)
    report["seconds_per_video_second"] = _ratios(runs)
    _write_json(args.out / sample.id / "report.json", report)
    return report


def run_pilot(args: argparse.Namespace, recipe: Recipe, samples: list[Sample]) -> int:
    max_audio_seconds = args.max_audio_seconds or recipe.limits.max_audio_seconds
    context: dict[str, Any] = {
        "recipe": recipe.name,
        "recipe_status": recipe.status,
        "recipe_sha256": _sha256(args.recipe),
        "avatar_profile": recipe.avatar.profile,
        "worker_image": os.environ.get("WORKER_IMAGE_DIGEST"),
        "network_interfaces": _network_interfaces(),
        # Quem roda cada runtime e mede a VRAM: um dublê de teste fica identificado no relatório.
        "commands": {
            "tts": [str(args.tts_python), str(TTS_STAGE)],
            "avatar": [str(args.avatar_python), str(AVATAR_STAGE)],
            "vram": args.vram_command,
        },
        "limits": {
            "max_audio_seconds": max_audio_seconds,
            "recipe_max_audio_seconds": recipe.limits.max_audio_seconds,
            "max_frame_num": math.ceil(max_audio_seconds * FPS),
        },
    }
    index: dict[str, Any] = {
        "status": "running",
        "queue": str(args.queue),
        "queue_sha256": _sha256(args.queue),
        **context,
        "samples": [
            {
                "id": sample.id,
                "format": sample.format,
                "status": "pending",
                "report": f"{sample.id}/report.json",
            }
            for sample in samples
        ],
    }
    index_path = args.out / "index.json"
    args.out.mkdir(parents=True, exist_ok=True)
    with StageMeter(args.vram_command, VRAM_INTERVAL_S) as meter:
        for sample, entry in zip(samples, index["samples"], strict=True):
            entry["status"] = "running"
            _write_json(index_path, index)
            entry["status"] = _run_sample(args, recipe, meter, context, sample)["status"]
    failed = [entry["id"] for entry in index["samples"] if entry["status"] == "failed"]
    index["status"] = "failed" if failed else "ok"
    _write_json(index_path, index)
    if failed:
        print(f"fila concluída com falha em {', '.join(failed)}: {index_path}", file=sys.stderr)
        return 1
    print(f"fila concluída: {index_path}")
    return 0


def _queue_file(value: Any, base: Path) -> Path | None:
    """Arquivo existente da amostra; caminho relativo parte da pasta da fila."""
    if not isinstance(value, str) or not value:
        return None
    path = base / value
    return path if path.is_file() else None


def _sample_text(entry: dict[str, Any], base: Path, problems: list[str]) -> str | None:
    """Fala literal de text ou de text_file, sem mexer em bordas nem em quebras de linha."""
    if ("text" in entry) == ("text_file" in entry):
        problems.append("declare a fala em text ou em text_file, só em um dos dois")
        return None
    if "text" in entry:
        text = entry["text"]
        if not isinstance(text, str):
            problems.append("text precisa ser texto")
            return None
    else:
        path = _queue_file(entry["text_file"], base)
        if path is None:
            problems.append(
                f"text_file {entry['text_file']!r} não é arquivo existente a partir de {base}"
            )
            return None
        try:
            # Decodifica os bytes: read_text trocaria \r\n por \n.
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"text_file {entry['text_file']!r} não está em UTF-8")
            return None
    if not text.strip():
        problems.append("a fala está vazia")
        return None
    return text


def _composition_problems(composition: Any) -> list[str]:
    """Mesmas chaves e faixas de scenes.composition e de calibration.composition."""
    if not isinstance(composition, dict) or set(composition) != set(COMPOSITION_RANGES):
        return [f"composition precisa ter exatamente {', '.join(COMPOSITION_RANGES)}"]
    return [
        f"composition.{key} {composition[key]!r} fora da faixa de {low:g} a {high:g}"
        for key, (low, high) in COMPOSITION_RANGES.items()
        if isinstance(composition[key], bool)
        or not isinstance(composition[key], int | float)
        or not low <= composition[key] <= high
    ]


def _check_sample(entry: Any, base: Path) -> tuple[Sample | None, list[str]]:
    """Confere uma amostra da fila; sem problemas, devolve-a com os caminhos resolvidos."""
    if not isinstance(entry, dict):
        return None, ["precisa ser um objeto"]
    problems = [f"chave desconhecida {key!r}" for key in entry if key not in _SAMPLE_FIELDS]
    sample_id = entry.get("id")
    if not (isinstance(sample_id, str) and _SAMPLE_ID.fullmatch(sample_id)):
        problems.append(
            f"id {sample_id!r} precisa ter só letras, dígitos, - e _, começando por letra ou dígito"
        )
    image = _queue_file(entry.get("image"), base)
    if image is None:
        problems.append(f"image {entry.get('image')!r} não é arquivo existente a partir de {base}")
    background = entry.get("background")
    if not (isinstance(background, str) and _HEX_COLOR.fullmatch(background)):
        background = _queue_file(background, base)
        if background is None:
            problems.append(
                f"background {entry.get('background')!r} precisa ser cor #RRGGBB "
                f"ou arquivo existente a partir de {base}"
            )
    text = _sample_text(entry, base, problems)
    voice, aspect = entry.get("voice"), entry.get("format")
    if voice not in VOICES:
        problems.append(f"voice {voice!r} precisa ser {' ou '.join(VOICES)}")
    if aspect not in FORMATS:
        problems.append(f"format {aspect!r} precisa ser {' ou '.join(FORMATS)}")
    composition = entry.get("composition")
    if composition is not None:
        problems.extend(_composition_problems(composition))
    if problems:
        return None, problems
    return Sample(sample_id, image, background, text, voice, aspect, composition), []


def load_queue(path: Path) -> list[Sample]:
    """Valida a fila inteira antes de qualquer execução; lança QueueError com os problemas."""
    try:
        raw = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise QueueError([f"não foi possível ler a fila {path}: {exc}"]) from exc
    entries = raw.get("samples") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries or set(raw) != {"samples"}:
        raise QueueError(['a fila precisa ser {"samples": [...]} com ao menos uma amostra'])
    samples: list[Sample] = []
    problems: list[str] = []
    first_by_id: dict[str, int] = {}
    for number, entry in enumerate(entries, start=1):
        sample, sample_problems = _check_sample(entry, path.parent)
        sample_id = entry.get("id") if isinstance(entry, dict) else None
        label = f"amostra {number}"
        if isinstance(sample_id, str):
            label += f" ({sample_id})"
            # <out>/<id> não pode colidir nem em sistema de arquivos que ignora maiúsculas.
            first = first_by_id.setdefault(sample_id.casefold(), number)
            if first != number:
                sample_problems.append(f"id repete o da amostra {first}")
        problems.extend(f"{label}: {problem}" for problem in sample_problems)
        if sample is not None:
            samples.append(sample)
    if problems:
        raise QueueError(problems)
    return samples


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
    parser.add_argument(
        "--queue",
        type=Path,
        required=True,
        help="fila JSON de amostras; uma amostra é uma fila de um item",
    )
    parser.add_argument(
        "--runs",
        type=_positive_int,
        default=1,
        help="execuções por amostra; a primeira é fria, as seguintes quentes",
    )
    parser.add_argument(
        "--max-audio-seconds",
        type=_positive_float,
        help="só calibração; substitui o limite da receita e fica no relatório",
    )
    parser.add_argument("--out", type=Path, required=True, help="diretório de saída novo ou vazio")
    parser.add_argument("--tts-python", type=Path, default=DEFAULT_TTS_PYTHON)
    parser.add_argument("--avatar-python", type=Path, default=DEFAULT_AVATAR_PYTHON)
    parser.add_argument("--infinitetalk-dir", type=Path, default=DEFAULT_INFINITETALK_DIR)
    parser.add_argument("--vram-command", type=shlex.split, default=DEFAULT_VRAM_COMMAND)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        samples = load_queue(args.queue)
    except QueueError as exc:
        problems = "\n".join(f"- {problem}" for problem in exc.problems)
        parser.error(f"fila recusada com {len(exc.problems)} problema(s):\n{problems}")
    if args.out.exists() and not (args.out.is_dir() and not any(args.out.iterdir())):
        parser.error(f"--out {args.out} já foi usado; escolha um diretório novo ou vazio")
    try:
        policy_problems = check_policy(load_manifest(args.manifest))
    except (OSError, ValueError) as exc:
        policy_problems = [f"não foi possível ler o manifesto {args.manifest}: {exc}"]
    if policy_problems:
        problems = "\n".join(f"- {problem}" for problem in policy_problems)
        print(f"Manifesto recusado pela política comercial:\n{problems}", file=sys.stderr)
        return 1
    try:
        recipe = load_recipe(args.recipe, args.manifest)
    except RecipeError as exc:
        print(f"Receita recusada:\n{exc}", file=sys.stderr)
        return 1
    return run_pilot(args, recipe, samples)


if __name__ == "__main__":
    sys.exit(main())
