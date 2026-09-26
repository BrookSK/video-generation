"""Finalização por FFmpeg: render nativo no canvas com pad da cor do cenário e perfil DAT-005."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from avatar_worker.recipe import Output

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def build_finalize_args(
    render_path: str | Path,
    audio_path: str | Path,
    out_path: str | Path,
    canvas_size: tuple[int, int],
    pad_color: str,
    output: Output,
) -> list[str]:
    """Monta a lista de argumentos do ffmpeg que junta render e áudio no canvas final.

    O render é escalado para caber em ``canvas_size`` sem esticar e completado com pad
    centralizado na cor ``pad_color`` (#RRGGBB). A duração segue as entradas: não há
    ``-shortest``. A lista é para ``subprocess.run`` sem shell.
    """
    if not (isinstance(pad_color, str) and _HEX_COLOR.fullmatch(pad_color)):
        raise ValueError(f"cor do pad precisa ser #RRGGBB ({pad_color!r})")
    width, height = canvas_size
    video_filter = ",".join(
        [
            f"fps={output.fps}",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={pad_color}",
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


def probe_output(path: str | Path) -> dict[str, Any]:
    """Lê com ffprobe o perfil do arquivo final: vídeo, áudio e durações."""
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        shell=False,
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(completed.stdout)
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
