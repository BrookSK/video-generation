"""Composição do canvas: avatar com alfa sobre fundo de cor ou imagem, pelo enquadramento."""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from PIL import Image, ImageOps

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def _background(background: str | Image.Image, size: tuple[int, int]) -> Image.Image:
    if isinstance(background, Image.Image):
        return ImageOps.fit(background.convert("RGB"), size, Image.Resampling.LANCZOS)
    if isinstance(background, str) and _HEX_COLOR.fullmatch(background):
        return Image.new("RGB", size, background)
    raise ValueError(f"fundo precisa ser cor #RRGGBB ou imagem ({background!r})")


def compose_canvas(
    avatar_rgba: Image.Image,
    background: str | Image.Image,
    composition: Mapping[str, float],
    size: tuple[int, int],
) -> Image.Image:
    """Cola o avatar pelo alfa sobre o fundo e devolve a imagem RGB no tamanho do canvas.

    ``composition`` segue ``scenes.composition``: ``scale`` é a altura do avatar sobre a
    altura do canvas, ``x`` o centro horizontal e ``y`` a base, em frações do canvas.
    O fundo em imagem é ajustado por cover e centralizado. O avatar mantém a proporção;
    o que sai do canvas é cortado na borda, nunca esticado.
    """
    width, height = size
    scale = composition["scale"]
    if scale <= 0:
        raise ValueError(f"scale precisa ser positivo ({scale!r})")

    canvas = _background(background, size)
    avatar = avatar_rgba.convert("RGBA")
    avatar_height = round(scale * height)
    avatar_width = round(avatar.width * avatar_height / avatar.height)
    avatar = avatar.resize((avatar_width, avatar_height), Image.Resampling.LANCZOS)
    left = round(composition["x"] * width - avatar_width / 2)
    top = round(composition["y"] * height) - avatar_height
    canvas.paste(avatar, (left, top), avatar)
    return canvas


@dataclass(frozen=True)
class BucketFrame:
    """Imagem entregue ao render: o canvas centralizado numa tela com a razão exata do bucket.

    ``size`` é a tela estendida, ``offset`` a posição do canvas nela e ``canvas_cut_px`` o
    que o corte central do InfiniteTalk tira do canvas, em pixels do canvas.
    """

    size: tuple[int, int]
    offset: tuple[int, int]
    canvas_cut_px: int


def centercrop_geometry(
    source_size: tuple[int, int], bucket: tuple[int, int]
) -> tuple[float, int, int]:
    """Reproduz resize_and_centercrop do InfiniteTalk no commit do manifesto.

    A imagem é escalada por max(escala da altura, escala da largura), com ceil no tamanho,
    e cortada no centro com o round do torchvision. Devolve a escala e o corte à esquerda e
    no topo, em pixels da imagem escalada.
    """
    source_w, source_h = source_size
    bucket_w, bucket_h = bucket
    scale = max(bucket_h / source_h, bucket_w / source_w)
    final_w, final_h = math.ceil(scale * source_w), math.ceil(scale * source_h)
    return scale, int(round((final_w - bucket_w) / 2.0)), int(round((final_h - bucket_h) / 2.0))


def canvas_cut(
    frame_size: tuple[int, int],
    offset: tuple[int, int],
    canvas_size: tuple[int, int],
    bucket: tuple[int, int],
) -> int:
    """Maior corte, em pixels do canvas, que o render aplica a um lado do canvas na tela."""
    scale, crop_left, crop_top = centercrop_geometry(frame_size, bucket)
    left, top = offset
    width, height = canvas_size
    bucket_w, bucket_h = bucket
    cuts = (
        crop_left - left * scale,
        crop_top - top * scale,
        (left + width) * scale - (crop_left + bucket_w),
        (top + height) * scale - (crop_top + bucket_h),
    )
    return math.ceil(max(0.0, *cuts) / scale)


def bucket_frame(canvas_size: tuple[int, int], bucket: tuple[int, int]) -> BucketFrame:
    """Menor tela com a razão exata do bucket em que o render não corta o canvas.

    O pad de cada eixo é múltiplo de 4, para a posição do canvas ficar par e o crop do
    FFmpeg em yuv420p não arredondar.
    """
    width, height = canvas_size
    divisor = math.gcd(*bucket)
    unit_w, unit_h = bucket[0] // divisor, bucket[1] // divisor
    start = max(math.ceil(width / unit_w), math.ceil(height / unit_h))
    for units in range(start, start + 64):
        size = (unit_w * units, unit_h * units)
        pad_w, pad_h = size[0] - width, size[1] - height
        if pad_w % 4 or pad_h % 4:
            continue
        offset = (pad_w // 2, pad_h // 2)
        if canvas_cut(size, offset, canvas_size, bucket) == 0:
            return BucketFrame(size=size, offset=offset, canvas_cut_px=0)
    raise ValueError(f"sem tela na razão do bucket {bucket} para o canvas {canvas_size}")


def extend_to_bucket(canvas: Image.Image, frame: BucketFrame, pad_color: str) -> Image.Image:
    """Completa o canvas com a cor do pad até a tela do bucket, sem escalar o conteúdo."""
    extended = _background(pad_color, frame.size)
    extended.paste(canvas, frame.offset)
    return extended
