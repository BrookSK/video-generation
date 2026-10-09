"""Finalização por FFmpeg: render nativo de volta ao canvas, pad da cor do cenário e DAT-005."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from avatar_worker.canvas import BucketFrame
from avatar_worker.recipe import Output

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def build_finalize_args(
    render_path: str | Path,
    audio_path: str | Path,
    out_path: str | Path,
    canvas_size: tuple[int, int],
    pad_color: str,
    output: Output,
    frame: BucketFrame,
) -> list[str]:
    """Monta a lista de argumentos do ffmpeg que junta render e áudio no canvas final.

    O render volta ao tamanho da tela estendida ``frame.size`` sem esticar, com pad
    centralizado na cor ``pad_color`` (#RRGGBB) se a proporção diferir. Depois o crop tira
    só a área estendida e devolve ``canvas_size`` a partir de ``frame.offset``. A duração
    segue as entradas: não há ``-shortest``. A lista é para ``subprocess.run`` sem shell.
    """
    if not (isinstance(pad_color, str) and _HEX_COLOR.fullmatch(pad_color)):
        raise ValueError(f"cor do pad precisa ser #RRGGBB ({pad_color!r})")
    width, height = canvas_size
    frame_w, frame_h = frame.size
    left, top = frame.offset
    video_filter = ",".join(
        [
            f"fps={output.fps}",
            f"scale={frame_w}:{frame_h}:force_original_aspect_ratio=decrease:flags=lanczos",
            f"pad={frame_w}:{frame_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color}",
            f"crop={width}:{height}:{left}:{top}",
            "setsar=1",
            f"format={output.pix_fmt}",
        ]
    )
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(render_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        video_filter,
        "-fps_mode",
        "cfr",
        "-c:v",
        output.video_codec,
        "-preset",
        output.preset,
        "-crf",
        str(output.crf),
        "-pix_fmt",
        output.pix_fmt,
        "-c:a",
        output.audio_codec,
        "-ar",
        str(output.audio_sample_rate),
        "-b:a",
        output.audio_bitrate,
        "-movflags",
        "+faststart",
        str(out_path),
    ]


def run_finalize(args: list[str]) -> None:
    """Executa a finalização sem shell; falha do ffmpeg lança CalledProcessError."""
    subprocess.run(args, shell=False, check=True, capture_output=True)


def _duration(value: Any) -> float | None:
    return float(value) if value is not None else None


def probe_args(path: str | Path) -> list[str]:
    return [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]


def probe_output(path: str | Path) -> dict[str, Any]:
    """Lê com ffprobe o perfil do arquivo final: vídeo, áudio e durações."""
    completed = subprocess.run(
        probe_args(path), shell=False, check=True, capture_output=True, text=True
    )
    return parse_output(json.loads(completed.stdout))


def parse_output(data: dict[str, Any]) -> dict[str, Any]:
    """Interpreta o mesmo perfil para piloto e inspeção cancelável do worker."""
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
    return {
        "width": video["width"],
        "height": video["height"],
        "video_codec": video["codec_name"],
        "pix_fmt": video["pix_fmt"],
        "r_frame_rate": video["r_frame_rate"],
        "audio_codec": audio["codec_name"],
        "sample_rate": int(audio["sample_rate"]),
        "video_duration": _duration(video.get("duration")),
        "audio_duration": _duration(audio.get("duration")),
        "duration": _duration(data["format"].get("duration")),
    }
