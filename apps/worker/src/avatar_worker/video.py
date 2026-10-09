"""Tentativa de vídeo: recipe do job, processos isolados, FFmpeg e manifesto factual."""

import hashlib
import json
import math
import shlex
import wave
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from avatar_worker.canvas import (
    background_pad_color,
    bucket_frame,
    canvas_cut,
    compose_canvas,
    extend_to_bucket,
)
from avatar_worker.finalize import build_finalize_args, parse_output, probe_args
from avatar_worker.manifest import check_policy, load_manifest
from avatar_worker.pilot import (
    AVATAR_FIELDS,
    AVATAR_STAGE,
    DEFAULT_AVATAR_PYTHON,
    DEFAULT_INFINITETALK_DIR,
    DEFAULT_TTS_PYTHON,
    DEFAULT_VRAM_COMMAND,
    TTS_STAGE,
    VRAM_INTERVAL_S,
    StageFailure,
    StageMeter,
)
from avatar_worker.process import ProcessFailure, run_process
from avatar_worker.recipe import RecipeError, recipe_from_mapping

MANIFEST_PATH = Path(__file__).resolve().parents[4] / "docs/models/MODEL_MANIFEST.json"


class GenerationFailure(Exception):
    """Falha classificável; a mensagem é segura para exibir na API/painel."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = code == "TRANSIENT"


@dataclass(frozen=True)
class VideoRuntime:
    models_dir: Path = Path("/models")
    manifest_path: Path = MANIFEST_PATH
    tts_python: Path = DEFAULT_TTS_PYTHON
    avatar_python: Path = DEFAULT_AVATAR_PYTHON
    infinitetalk_dir: Path = DEFAULT_INFINITETALK_DIR
    tts_script: Path = TTS_STAGE
    avatar_script: Path = AVATAR_STAGE

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "VideoRuntime":
        defaults = cls()
        return cls(
            **{
                key: Path(env.get(name, str(getattr(defaults, key)))).resolve()
                for key, name in (
                    ("models_dir", "MODELS_DIR"),
                    ("manifest_path", "MODEL_MANIFEST"),
                    ("tts_python", "TTS_PYTHON"),
                    ("avatar_python", "AVATAR_PYTHON"),
                    ("infinitetalk_dir", "INFINITETALK_DIR"),
                )
            }
        )


@dataclass(frozen=True)
class VideoResult:
    files: dict[str, Path]
    stage_timings: dict[str, float]
    peak_vram_mb: int | None


def file_sha256(path: Path, check: Callable[[], None]) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            check()
            digest.update(block)
    check()
    return digest.hexdigest()


def _output_path(value: Any, work: Path, expected: Path | None = None) -> Path:
    if not isinstance(value, str):
        raise GenerationFailure("OUTPUT_INVALID", "O estágio não entregou o arquivo esperado.")
    path = Path(value).resolve()
    if not path.is_relative_to(work) or not path.is_file() or (expected and path != expected):
        raise GenerationFailure("OUTPUT_INVALID", "O estágio entregou um arquivo inválido.")
    return path


def _stage_result(
    python: Path, script: Path, request: dict, name: str, work: Path, check: Callable[[], None]
) -> dict:
    request_path, result_path = work / f"{name}_request.json", work / f"{name}_result.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    run_process(
        [str(python), str(script), str(request_path), str(result_path)],
        check,
        work / f"{name}.log",
        cwd=work,
    )
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("result não é objeto")
        return result
    except (OSError, ValueError) as exc:
        raise GenerationFailure(
            "OUTPUT_INVALID", "O estágio não entregou resultado válido."
        ) from exc


def _audio_duration(path: Path, sample_rate: int) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (
                1,
                2,
                sample_rate,
            ):
                raise ValueError("perfil WAV inválido")
            frames = audio.getnframes()
            # Não confiar no tamanho informado no header ou no result.json.
            actual = 0
            for block in iter(lambda: audio.readframes(16384), b""):
                actual += len(block)
            if actual != frames * 2 or frames == 0:
                raise ValueError("WAV incompleto")
            return frames / sample_rate
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        raise GenerationFailure(
            "OUTPUT_INVALID", "O áudio gerado está inválido ou incompleto."
        ) from exc


def _native_video(path: Path, work: Path, check: Callable[[], None]) -> dict:
    report = work / "native-probe.json"
    try:
        run_process(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_packets",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            check,
            report,
        )
        data = json.loads(report.read_text())
        (stream,) = data["streams"]
        return {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "frames": int(stream["nb_read_packets"]),
            "duration": float(stream.get("duration", data["format"]["duration"])),
        }
    except (ProcessFailure, OSError, ValueError, KeyError, TypeError) as exc:
        raise GenerationFailure("OUTPUT_INVALID", "O render não contém vídeo válido.") from exc


def _faststart(path: Path) -> bool:
    size = path.stat().st_size
    boxes = []
    with path.open("rb") as handle:
        while handle.tell() + 8 <= size:
            offset = handle.tell()
            header = handle.read(8)
            length, kind = int.from_bytes(header[:4], "big"), header[4:]
            header_size = 8
            if length == 1:
                length = int.from_bytes(handle.read(8), "big")
                header_size = 16
            elif length == 0:
                length = size - offset
            if length < header_size or offset + length > size:
                return False
            if kind in (b"moov", b"mdat"):
                boxes.append(kind)
                if len(boxes) == 2:
                    return boxes == [b"moov", b"mdat"]
            handle.seek(offset + length)
    return False


def _validate_final(
    profile: dict, path: Path, size: tuple, audio_seconds: float, limit: int
) -> None:
    durations = [profile.get(key) for key in ("video_duration", "audio_duration")]
    if not all(isinstance(v, int | float) and math.isfinite(v) and v > 0 for v in durations):
        raise GenerationFailure("OUTPUT_INVALID", "O vídeo final não tem duração válida.")
    if (
        (profile["width"], profile["height"]) != size
        or (profile["video_codec"], profile["pix_fmt"], profile["r_frame_rate"])
        != ("h264", "yuv420p", "25/1")
        or (profile["audio_codec"], profile["sample_rate"]) != ("aac", 48000)
        or durations[0] < audio_seconds - 0.08
        or durations[0] > limit + 0.08
        or abs(durations[1] - audio_seconds) > 0.1
        or not _faststart(path)
    ):
        raise GenerationFailure(
            "OUTPUT_INVALID", "O vídeo final não atende ao perfil de exportação."
        )


def generate_video(
    payload: Mapping[str, Any],
    inputs: Mapping[str, Path],
    work_dir: Path,
    runtime: VideoRuntime,
    check: Callable[[], None],
    set_stage: Callable[[str], None],
) -> VideoResult:
    """Nenhuma escolha de modelo/default local substitui a receita persistida do job."""
    check()
    try:
        manifest = load_manifest(runtime.manifest_path)
        if check_policy(manifest):
            raise RecipeError(["manifesto recusado"])
        recipe = recipe_from_mapping(payload["recipe_spec"], manifest, require_frozen=True)
        aspect = payload["aspect_ratio"]
        size = recipe.canvas[aspect]
        voice = recipe.tts.voices[payload["voice"]]
        text = payload["script_text"]
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > recipe.limits.max_script_chars
        ):
            raise ValueError("texto fora do limite")
        frame = bucket_frame(size, recipe.avatar.buckets[aspect])
    except (RecipeError, KeyError, TypeError, ValueError) as exc:
        raise GenerationFailure(
            "INPUT_INVALID", "O pedido ou a receita de geração está inválido."
        ) from exc
    work = work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    files = {
        name: work / name for name in ("audio.wav", "render.mp4", "final.mp4", "manifest.json")
    }
    stages: dict[str, dict] = {}
    attempt: dict[str, Any] = {
        "schema_version": 1,
        "recipe_id": payload["recipe_id"],
        "recipe": payload["recipe_spec"],
        "aspect_ratio": aspect,
        "voice": payload["voice"],
        "script_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "stages": stages,
        "files": {},
    }

    def checkpoint():
        files["manifest.json"].write_text(
            json.dumps(attempt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    with StageMeter(shlex.split(DEFAULT_VRAM_COMMAND), VRAM_INTERVAL_S) as meter:

        @contextmanager
        def stage(name):
            check()
            set_stage(name)
            attempt["stage"] = name
            checkpoint()
            try:
                with meter.measure(stages, name):
                    yield
            finally:
                checkpoint()

        try:
            with stage("compose"):
                try:
                    with Image.open(inputs["avatar"]) as source:
                        if source.mode != "RGBA":
                            raise ValueError("avatar sem alfa preparado")
                        avatar = source.copy()
                    background: str | Image.Image = payload["background_color"]
                    if inputs.get("background") is not None:
                        with Image.open(inputs["background"]) as image:
                            background = image.convert("RGB")
                    pad = background_pad_color(background)
                    canvas = compose_canvas(
                        avatar, background, payload["composition"][aspect], size
                    )
                    canvas.save(work / "canvas.png")
                    extend_to_bucket(canvas, frame, pad).save(work / "render_input.png")
                except (OSError, UnidentifiedImageError, ValueError, KeyError, TypeError) as exc:
                    raise GenerationFailure(
                        "INPUT_INVALID", "O avatar ou cenário está inválido."
                    ) from exc
            with stage("tts"):
                voice_request = {"kind": voice.kind}
                if voice.kind == "reference":
                    voice_request.update(path=voice.path, sha256=voice.sha256)
                tts = _stage_result(
                    runtime.tts_python,
                    runtime.tts_script,
                    {
                        "text": text,
                        "language": recipe.tts.language,
                        "models_dir": str(runtime.models_dir),
                        "out_wav": str(files["audio.wav"]),
                        "voice": voice_request,
                    },
                    "tts",
                    work,
                    check,
                )
                _output_path(tts.get("audio_path"), work, files["audio.wav"])
                duration = _audio_duration(files["audio.wav"], recipe.tts.sample_rate)
                if duration > recipe.limits.max_audio_seconds:
                    raise GenerationFailure(
                        "INPUT_INVALID", "A fala gerada supera o limite de duração."
                    )
                attempt["audio_seconds"] = duration
                attempt["watermark_detected"] = tts.get("watermark_detected")
                peak = tts.get("peak_vram_mb")
                if isinstance(peak, int | float) and math.isfinite(peak) and peak >= 0:
                    stages["tts"]["runtime_peak_vram_mb"] = peak
                attempt["files"]["audio.wav"] = file_sha256(files["audio.wav"], check)
            with stage("render"):
                rendered = _stage_result(
                    runtime.avatar_python,
                    runtime.avatar_script,
                    {
                        "image": str(work / "render_input.png"),
                        "audio": str(files["audio.wav"]),
                        "format": aspect,
                        "models_dir": str(runtime.models_dir),
                        "infinitetalk_dir": str(runtime.infinitetalk_dir),
                        "out_dir": str(work),
                        "recipe_avatar": {
                            field: getattr(recipe.avatar, field) for field in AVATAR_FIELDS
                        },
                    },
                    "render",
                    work,
                    check,
                )
                native = _output_path(rendered.get("video_path"), work)
                profile = _native_video(native, work, check)
                if (
                    profile["duration"] < duration - 0.08
                    or profile["frames"] <= 0
                    or canvas_cut(
                        frame.size, frame.offset, size, (profile["width"], profile["height"])
                    )
                ):
                    raise GenerationFailure(
                        "OUTPUT_INVALID", "O render corta o enquadramento ou a fala."
                    )
                if native != files["render.mp4"]:
                    native.replace(files["render.mp4"])
                attempt["native"] = profile
                attempt["files"]["render.mp4"] = file_sha256(files["render.mp4"], check)
            with stage("finalize"):
                run_process(
                    build_finalize_args(
                        files["render.mp4"],
                        files["audio.wav"],
                        files["final.mp4"],
                        size,
                        pad,
                        recipe.output,
                        frame,
                    ),
                    check,
                    work / "finalize.log",
                )
                try:
                    report = work / "final-probe.json"
                    run_process(probe_args(files["final.mp4"]), check, report)
                    final = parse_output(json.loads(report.read_text()))
                    _validate_final(
                        final, files["final.mp4"], size, duration, recipe.limits.max_audio_seconds
                    )
                except (ProcessFailure, OSError, KeyError, ValueError, StopIteration) as exc:
                    raise GenerationFailure(
                        "OUTPUT_INVALID", "O vídeo final está incompleto."
                    ) from exc
                attempt["final"] = final
                attempt["files"]["final.mp4"] = file_sha256(files["final.mp4"], check)
        except StageFailure as exc:
            cause = exc.__cause__
            if isinstance(cause, GenerationFailure):
                raise cause from None
            if isinstance(cause, ProcessFailure):
                if "out of memory" in cause.diagnostic.lower():
                    raise GenerationFailure(
                        "OUT_OF_MEMORY", "A GPU não tem memória para esta geração."
                    ) from exc
                code = "OUTPUT_INVALID" if exc.stage == "finalize" else "RENDER_FAILED"
                raise GenerationFailure(
                    code, "Falha no estágio de geração de voz ou vídeo."
                ) from exc
            # Preserva cancelamento de lease e erros inesperados para o supervisor.
            if cause is not None:
                raise cause from None
            raise
    check()
    attempt["stage"] = "upload"
    checkpoint()
    peaks = [
        value
        for entry in stages.values()
        for key in ("vram_peak_mb", "runtime_peak_vram_mb")
        if isinstance(value := entry.get(key), int | float)
    ]
    return VideoResult(
        files=files,
        stage_timings={name: values["seconds"] for name, values in stages.items()},
        peak_vram_mb=math.ceil(max(peaks)) if peaks else None,
    )
