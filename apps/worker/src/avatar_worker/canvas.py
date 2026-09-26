"""Composição do canvas: avatar com alfa sobre fundo de cor ou imagem, pelo enquadramento."""

import re
from collections.abc import Mapping

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
