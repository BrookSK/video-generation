"""Montagem da aula no supervisor CPU: abertura, cenas em ordem com corte seco e encerramento.

Só FFmpeg e Pillow, sem GPU: o FFmpeg roda sem shell, sem hwaccel nem nvenc e com
CUDA_VISIBLE_DEVICES vazio. A cena nunca é escalada: resolução diferente do formato da aula
falha com OUTPUT_INVALID. O arquivo final é conferido por ffprobe antes de ser entregue.
"""

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from avatar_worker.finalize import parse_output, probe_args
from avatar_worker.process import ProcessFailure, run_process
from avatar_worker.video import GenerationFailure, _faststart, file_sha256

CANVAS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
FPS = 25
CARD_SECONDS = 3.0
FADE_SECONDS = 0.5
AUDIO_RATE = 48000
# Mesmo perfil de exportação da receita de vídeo (docs/models/RECIPE-v1.json).
VIDEO_CODEC = "libx264"
PIX_FMT = "yuv420p"
CRF = 18
PRESET = "medium"
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"
# Logo nunca ampliado; se for maior, cabe nesta fração do canvas.
LOGO_MAX_WIDTH = 0.6
LOGO_MAX_HEIGHT = 0.35
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass(frozen=True)
class LessonResult:
    files: dict[str, Path]
    duration: float


def _invalid(message: str) -> GenerationFailure:
    return GenerationFailure("OUTPUT_INVALID", message)


def _no_gpu_env() -> dict[str, str]:
    return {**os.environ, "CUDA_VISIBLE_DEVICES": ""}


def _probe(path: Path, work: Path, name: str, check: Callable[[], None]) -> dict[str, Any]:
    report = work / f"{name}-probe.json"
    run_process(probe_args(path), check, report, env=_no_gpu_env())
    return json.loads(report.read_text())


def _scene_profile(
    position: int, path: Path, size: tuple[int, int], work: Path, check: Callable[[], None]
) -> float:
    """Confere a cena e devolve a duração do vídeo; resolução diferente nunca é ajustada."""
    try:
        data = _probe(path, work, f"scene-{position}", check)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
        width, height = int(video["width"]), int(video["height"])
        duration = float(video.get("duration") or data["format"]["duration"])
    except (ProcessFailure, OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise _invalid(f"A cena {position} não contém um vídeo válido.") from exc
    if (width, height) != size:
        raise _invalid(
            f"A cena {position} tem resolução {width}x{height}, diferente de "
            f"{size[0]}x{size[1]} do formato da aula."
        )
    if not has_audio or not math.isfinite(duration) or duration <= 0:
        raise _invalid(f"A cena {position} não tem áudio ou duração válida.")
    return duration


def draw_card(
    logo_path: Path, background: str, accent: str, size: tuple[int, int]
) -> Image.Image:
    """Quadro da abertura e do encerramento: fundo, logo centralizado e faixa de destaque.

    O logo mantém a proporção e nunca é ampliado; maior que a área máxima, ele é reduzido.
    A faixa fica centralizada logo abaixo do logo, e o conjunto fica no centro do quadro.
    """
    width, height = size
    try:
        with Image.open(logo_path) as source:
            logo = ImageOps.exif_transpose(source).convert("RGBA")
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError) as exc:
        raise GenerationFailure("INPUT_INVALID", "O logo da aula não pôde ser lido.") from exc
    fit = min(1.0, width * LOGO_MAX_WIDTH / logo.width, height * LOGO_MAX_HEIGHT / logo.height)
    if fit < 1.0:
        logo = logo.resize(
            (max(1, round(logo.width * fit)), max(1, round(logo.height * fit))),
            Image.Resampling.LANCZOS,
        )
    band_w, band_h = round(width * 0.25), max(4, round(height * 0.008))
    gap = round(height * 0.03)
    top = (height - (logo.height + gap + band_h)) // 2
    card = Image.new("RGB", size, background)
    card.paste(logo, ((width - logo.width) // 2, top), logo)
    band_top = top + logo.height + gap
    card.paste(accent, ((width - band_w) // 2, band_top, (width + band_w) // 2, band_top + band_h))
    return card


def build_assemble_args(
    card: Path, scenes: list[tuple[Path, float]], background: str, out_path: Path
) -> list[str]:
    """Argumentos do ffmpeg: abertura, cenas na ordem e encerramento, com corte seco.

    Abertura e encerramento são o quadro por 3 s com fade de 0,5 s a partir da cor de fundo
    e áudio silencioso. O áudio de cada cena é completado com silêncio ou cortado até a
    duração do vídeo dela, para as cenas seguintes não deslizarem. Lista para uso sem shell.
    """
    color = "0x" + background.removeprefix("#")
    card_input = ["-loop", "1", "-framerate", str(FPS), "-t", str(CARD_SECONDS), "-i", str(card)]
    silence = ["-f", "lavfi", "-t", str(CARD_SECONDS), "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error", *card_input, *silence]
    for path, _ in scenes:
        args += ["-i", str(path)]
    args += [*card_input, *silence]
    fade_out = CARD_SECONDS - FADE_SECONDS
    card_video = (
        f"fps={FPS},format={PIX_FMT},setsar=1,"
        f"fade=t=in:st=0:d={FADE_SECONDS}:color={color},"
        f"fade=t=out:st={fade_out}:d={FADE_SECONDS}:color={color}"
    )
    audio = f"aresample={AUDIO_RATE},aformat=channel_layouts=stereo"
    closing = 2 + len(scenes)
    filters = [f"[0:v]{card_video}[v0]", f"[1:a]{audio}[a0]"]
    for index, (_, duration) in enumerate(scenes, start=1):
        source = index + 1
        filters.append(f"[{source}:v:0]fps={FPS},format={PIX_FMT},setsar=1[v{index}]")
        filters.append(f"[{source}:a:0]{audio},apad,atrim=0:{duration:.6f}[a{index}]")
    last = len(scenes) + 1
    filters.append(f"[{closing}:v]{card_video}[v{last}]")
    filters.append(f"[{closing + 1}:a]{audio}[a{last}]")
    segments = "".join(f"[v{i}][a{i}]" for i in range(last + 1))
    filters.append(f"{segments}concat=n={last + 1}:v=1:a=1[v][a]")
    return [
        *args,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-r",
        str(FPS),
        "-fps_mode",
        "cfr",
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        PRESET,
        "-crf",
        str(CRF),
        "-pix_fmt",
        PIX_FMT,
        "-c:a",
        AUDIO_CODEC,
        "-ar",
        str(AUDIO_RATE),
        "-b:a",
        AUDIO_BITRATE,
        "-movflags",
        "+faststart",
        str(out_path),
    ]


def _validate_final(
    profile: dict[str, Any], path: Path, size: tuple[int, int], expected: float, junctions: int
) -> None:
    tolerance = junctions / FPS
    duration = profile.get("video_duration")
    audio = profile.get("audio_duration")
    if not all(isinstance(v, int | float) and math.isfinite(v) for v in (duration, audio)):
        raise _invalid("A aula montada não tem duração válida.")
    if (
        (profile["width"], profile["height"]) != size
        or (profile["video_codec"], profile["pix_fmt"], profile["r_frame_rate"])
        != ("h264", PIX_FMT, f"{FPS}/1")
        or (profile["audio_codec"], profile["sample_rate"]) != (AUDIO_CODEC, AUDIO_RATE)
        or abs(duration - expected) > tolerance
        or abs(audio - expected) > tolerance
        or not _faststart(path)
    ):
        raise _invalid("A aula montada não atende ao perfil de exportação.")


def assemble_lesson(
    payload: Mapping[str, Any],
    scene_paths: Mapping[int, Path],
    logo_path: Path,
    work_dir: Path,
    check: Callable[[], None],
) -> LessonResult:
    """Monta final.mp4 e manifest.json em work_dir a partir das cenas baixadas.

    ``scene_paths`` vai da posição da cena ao final.mp4 dela. Falhas viram GenerationFailure
    com mensagem em português; cancelamento de lease (via ``check``) passa adiante.
    """
    check()
    try:
        size = CANVAS[payload["aspect_ratio"]]
        background, accent = payload["background_color"], payload["accent_color"]
        if not (_HEX_COLOR.fullmatch(background) and _HEX_COLOR.fullmatch(accent)):
            raise ValueError("cor da identidade inválida")
        ordered = sorted(payload["scenes"], key=lambda scene: scene["position"])
        paths = [scene_paths[scene["position"]] for scene in ordered]
    except (KeyError, TypeError, ValueError) as exc:
        raise GenerationFailure(
            "INPUT_INVALID", "O pedido de montagem da aula está inválido."
        ) from exc
    if not ordered:
        raise GenerationFailure("INPUT_INVALID", "A aula não tem cenas para montar.")
    work = work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    files = {"final.mp4": work / "final.mp4", "manifest.json": work / "manifest.json"}

    durations = [
        _scene_profile(scene["position"], path, size, work, check)
        for scene, path in zip(ordered, paths, strict=True)
    ]
    card = work / "card.png"
    draw_card(logo_path, background, accent, size).save(card)
    check()
    try:
        scenes = list(zip(paths, durations, strict=True))
        run_process(
            build_assemble_args(card, scenes, background, files["final.mp4"]),
            check,
            work / "assemble.log",
            env=_no_gpu_env(),
        )
    except ProcessFailure as exc:
        raise _invalid("Falha do FFmpeg ao montar a aula.") from exc
    expected = 2 * CARD_SECONDS + sum(durations)
    try:
        final = parse_output(_probe(files["final.mp4"], work, "final", check))
    except (ProcessFailure, OSError, ValueError, KeyError, StopIteration) as exc:
        raise _invalid("A aula montada está incompleta.") from exc
    _validate_final(final, files["final.mp4"], size, expected, junctions=len(ordered) + 1)

    manifest = {
        "schema_version": 1,
        "lesson_id": payload.get("lesson_id"),
        "aspect_ratio": payload["aspect_ratio"],
        "background_color": background,
        "accent_color": accent,
        "logo_sha256": hashlib.sha256(logo_path.read_bytes()).hexdigest(),
        "card_seconds": CARD_SECONDS,
        "scenes": [
            {
                "position": scene["position"],
                "shot": scene.get("shot"),
                "seconds": duration,
                "sha256": file_sha256(path, check),
            }
            for scene, path, duration in zip(ordered, paths, durations, strict=True)
        ],
        "expected_seconds": expected,
        "final": final,
        "files": {"final.mp4": file_sha256(files["final.mp4"], check)},
    }
    files["manifest.json"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    check()
    return LessonResult(files=files, duration=final["video_duration"])
