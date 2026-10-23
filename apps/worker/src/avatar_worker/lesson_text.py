"""Texto na tela da aula: legenda literal, tempo pelo áudio e desenho com Pillow.

A legenda é o texto da cena, cortado só em fronteira de palavra: a junção dos trechos é
idêntica ao texto. O tempo vem dos intervalos de fala detectados por ``silencedetect``: as
palavras são distribuídas por eles e um trecho nunca atravessa uma pausa. Só cena sem fala
detectada tem o tempo dividido pelos caracteres. Legenda e
tópicos viram PNGs transparentes, aplicados depois com ``overlay`` (o FFmpeg local não tem
``drawtext`` nem ``ass``). A fonte é a Manrope Bold, sob a SIL Open Font License 1.1
(``fonts/Manrope-OFL.txt``).
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from avatar_worker.process import run_process

FONT_PATH = Path(__file__).with_name("fonts") / "Manrope-Bold.ttf"
MAX_SUBTITLE_LINES = 2
# Fim de frase: pontuação final, com aspas ou parêntese de fechamento logo depois.
_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’»)\]]*$")
_WORD = re.compile(r"\S+\s*")
_SILENCE_START = re.compile(r"silence_start: (-?\d+(?:\.\d+)?)")
_SILENCE_END = re.compile(r"silence_end: (-?\d+(?:\.\d+)?)")
SILENCE_NOISE = "-35dB"
SILENCE_SECONDS = 0.25
MIN_SPEECH_SECONDS = 0.05
# O trecho fica na tela até o próximo começar ou este tempo depois da última palavra.
SUBTITLE_HOLD_SECONDS = 0.5
# Pontuação no fim da palavra: preferência para cortar a fala ali, maior em fim de frase.
_PAUSE_MARK = re.compile(r"[,;:.!?…]+[\"'”’»)\]]*$")
PUNCTUATION_BONUS = 0.1
SENTENCE_BONUS = 0.3

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Layout:
    """Áreas fixas por formato, em pixels do canvas (esquerda, topo, direita, base)."""

    subtitle_width: int
    subtitle_bottom: int
    subtitle_size: int
    topics_size: int
    topics: Box
    topics_with_image: Box
    image: Box
    pip: Box


# 16:9: tópicos na coluna da direita; 9:16: tópicos acima da legenda.
LAYOUTS: dict[str, Layout] = {
    "16:9": Layout(
        subtitle_width=1600,
        subtitle_bottom=1032,
        subtitle_size=46,
        topics_size=34,
        topics=(1300, 48, 1872, 840),
        topics_with_image=(1300, 394, 1872, 840),
        image=(48, 48, 1276, 840),
        pip=(1300, 48, 1872, 370),
    ),
    "9:16": Layout(
        subtitle_width=960,
        subtitle_bottom=1760,
        subtitle_size=50,
        topics_size=38,
        topics=(48, 900, 1032, 1528),
        topics_with_image=(48, 968, 684, 1528),
        image=(48, 96, 1032, 940),
        pip=(708, 968, 1032, 1544),
    ),
}


@dataclass(frozen=True)
class Chunk:
    """Trecho da legenda: ``text`` é a fatia literal do texto; ``lines``, o que aparece."""

    text: str
    lines: tuple[str, ...]
    sentence: int
    words: int = 0
    start: float = 0.0
    end: float = 0.0


@cache
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def text_color(background: str) -> tuple[int, int, int]:
    """Branco ou quase preto, o que tiver mais contraste com a cor de fundo da identidade."""
    r, g, b = (value / 255 for value in _rgb(background))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (17, 17, 17) if luminance > 0.55 else (255, 255, 255)


def _words(text: str) -> list[str]:
    """Palavras com o espaço que vem depois; o espaço inicial vai junto da primeira."""
    words = _WORD.findall(text)
    if words:
        words[0] = text[: len(text) - len(text.lstrip())] + words[0]
    return words


def _wrap(words: list[str], size: int, max_width: int) -> list[list[str]]:
    """Linhas pela largura medida com a fonte; uma palavra larga demais fica sozinha."""
    lines: list[list[str]] = []
    for word in words:
        if (
            lines
            and font(size).getlength(" ".join(w.strip() for w in [*lines[-1], word])) <= max_width
        ):
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def split_subtitles(text: str, aspect: str, groups: list[int] | None = None) -> list[Chunk]:
    """Divide em frases pela pontuação e cada frase em trechos de até duas linhas.

    ``groups`` dá o intervalo de fala de cada palavra; um trecho não junta palavras de
    intervalos diferentes.
    """
    layout = LAYOUTS[aspect]
    max_width = layout.subtitle_width - 2 * _padding(layout.subtitle_size)
    words = _words(text)
    groups = groups or [0] * len(words)
    segments: list[tuple[int, list[str]]] = []
    sentence, starts = 0, True
    for index, word in enumerate(words):
        if starts or groups[index] != groups[index - 1]:
            segments.append((sentence, []))
        segments[-1][1].append(word)
        starts = bool(_SENTENCE_END.search(word.strip()))
        sentence += starts
    chunks = []
    for sentence, segment in segments:
        lines = _wrap(segment, layout.subtitle_size, max_width)
        for first in range(0, len(lines), MAX_SUBTITLE_LINES):
            group = lines[first : first + MAX_SUBTITLE_LINES]
            chunks.append(
                Chunk(
                    text="".join(word for line in group for word in line),
                    lines=tuple(" ".join(word.strip() for word in line) for line in group),
                    sentence=sentence,
                    words=sum(len(line) for line in group),
                )
            )
    return chunks


def parse_silences(log: str, duration: float) -> list[tuple[float, float]]:
    """Intervalos de silêncio do log do ``silencedetect``; silêncio sem fim vai até o final."""
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in log.splitlines():
        if (found := _SILENCE_START.search(line)) is not None:
            start = max(0.0, float(found.group(1)))
        elif (found := _SILENCE_END.search(line)) is not None and start is not None:
            silences.append((start, min(duration, float(found.group(1)))))
            start = None
    if start is not None:
        silences.append((start, duration))
    return silences


def speech_intervals(
    silences: list[tuple[float, float]], duration: float
) -> list[tuple[float, float]]:
    """Complemento dos silêncios dentro da cena, sem intervalos curtos demais."""
    speech, cursor = [], 0.0
    for start, end in sorted(silences):
        if start - cursor >= MIN_SPEECH_SECONDS:
            speech.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor >= MIN_SPEECH_SECONDS:
        speech.append((cursor, duration))
    return speech


def _merge_speech(speech: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    """Une os intervalos separados pelas menores pausas até sobrarem ``limit``."""
    speech = list(speech)
    while len(speech) > limit:
        gap = min(range(len(speech) - 1), key=lambda i: speech[i + 1][0] - speech[i][1])
        speech[gap : gap + 2] = [(speech[gap][0], speech[gap + 1][1])]
    return speech


def _cut_bonus(word: str) -> float:
    word = word.strip()
    if _SENTENCE_END.search(word):
        return SENTENCE_BONUS
    return PUNCTUATION_BONUS if _PAUSE_MARK.search(word) else 0.0


def _group_words(
    weights: list[int], bonuses: list[float], speech: list[tuple[float, float]]
) -> list[int]:
    """Intervalo de fala de cada palavra, em ordem e sem intervalo vazio.

    Programação dinâmica: o custo de um grupo é a diferença entre sua parte dos caracteres
    e a parte do tempo de fala do intervalo; cortar depois de pontuação dá bônus.
    """
    words, intervals = len(weights), len(speech)
    prefix = [0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)
    talk = sum(end - start for start, end in speech)
    shares = [(end - start) / talk for start, end in speech]
    inf = float("inf")
    cost = [[inf] * (words + 1) for _ in range(intervals + 1)]
    back = [[0] * (words + 1) for _ in range(intervals + 1)]
    cost[0][0] = 0.0
    for j in range(1, intervals + 1):
        for i in range(j, words - (intervals - j) + 1):
            for p in range(j - 1, i):
                if cost[j - 1][p] == inf:
                    continue
                value = cost[j - 1][p] + abs((prefix[i] - prefix[p]) / prefix[-1] - shares[j - 1])
                if j < intervals:
                    value -= bonuses[i - 1]
                if value < cost[j][i]:
                    cost[j][i], back[j][i] = value, p
    groups, i = [0] * words, words
    for j in range(intervals, 0, -1):
        p = back[j][i]
        groups[p:i] = [j - 1] * (i - p)
        i = p
    return groups


def _word_times(
    weights: list[int], groups: list[int], speech: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Dentro do seu intervalo de fala, cada palavra tem tempo proporcional aos caracteres."""
    times: list[tuple[float, float]] = []
    for index, (start, end) in enumerate(speech):
        members = [weight for weight, group in zip(weights, groups, strict=True) if group == index]
        cursor, total = start, sum(members)
        for weight in members:
            finish = cursor + (end - start) * weight / total
            times.append((cursor, finish))
            cursor = finish
    return times


def time_chunks(
    text: str, aspect: str, speech: list[tuple[float, float]], duration: float
) -> tuple[list[Chunk], str]:
    """Trechos da legenda com tempo pela fala; sem fala detectada, pelos caracteres na cena
    inteira. Devolve os trechos e o método usado."""
    words = _words(text)
    weights = [max(1, len(word.strip())) for word in words]
    if speech and words:
        speech, method = _merge_speech(speech, len(words)), "silence"
        groups = _group_words(weights, [_cut_bonus(word) for word in words], speech)
    else:
        speech, method = [(0.0, duration)], "characters"
        groups = [0] * len(words)
    times = _word_times(weights, groups, speech)
    timed, first = [], 0
    for chunk in split_subtitles(text, aspect, groups):
        last = first + chunk.words - 1
        timed.append(replace(chunk, start=times[first][0], end=times[last][1]))
        first = last + 1
    for index, chunk in enumerate(timed):
        limit = timed[index + 1].start if index + 1 < len(timed) else duration
        timed[index] = replace(
            chunk, end=max(chunk.end, min(limit, chunk.end + SUBTITLE_HOLD_SECONDS))
        )
    return timed, method


def detect_speech(
    media: Path,
    duration: float,
    work: Path,
    name: str,
    check: Callable[[], None],
    env: Mapping[str, str],
) -> list[tuple[float, float]]:
    """Roda ``silencedetect`` no áudio da cena e devolve os intervalos de fala."""
    log = work / f"{name}-silence.log"
    run_process(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-v", "info", "-i", str(media),
            "-map", "0:a:0", "-af", f"silencedetect=noise={SILENCE_NOISE}:d={SILENCE_SECONDS}",
            "-f", "null", "-",
        ],
        check,
        log,
        env=env,
    )  # fmt: skip
    return speech_intervals(parse_silences(log.read_text("utf-8", "replace"), duration), duration)


def _padding(size: int) -> int:
    return round(size * 0.6)


def _line_height(size: int) -> int:
    return round(size * 1.3)


def draw_subtitle(
    chunk: Chunk, aspect: str, background: str, accent: str
) -> tuple[Image.Image, int, int]:
    """PNG transparente do trecho, recortado na caixa; devolve a imagem e a posição (x, y).

    Caixa na cor de fundo da identidade, faixa fina na cor de destaque e texto no tom de
    maior contraste. Palavra mais larga que a caixa reduz a fonte do trecho, sem cortar.
    """
    layout = LAYOUTS[aspect]
    size, pad = layout.subtitle_size, _padding(layout.subtitle_size)
    while (
        size > 12
        and max(font(size).getlength(line) for line in chunk.lines)
        > layout.subtitle_width - 2 * pad
    ):
        size -= 2
    line_h = _line_height(size)
    text_w = max(round(font(size).getlength(line)) for line in chunk.lines)
    width = min(layout.subtitle_width, text_w + 2 * pad)
    bar = max(4, size // 10)
    height = bar + pad + line_h * len(chunk.lines) + pad // 2
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=size // 3, fill=(*_rgb(background), 225)
    )
    draw.rectangle((0, 0, width - 1, bar - 1), fill=(*_rgb(accent), 255))
    for index, line in enumerate(chunk.lines):
        y = bar + pad // 2 + index * line_h + (line_h - size) // 2
        draw.text(
            (width / 2, y), line, font=font(size), fill=(*text_color(background), 255), anchor="mt"
        )
    canvas_w = 1920 if aspect == "16:9" else 1080
    return image, (canvas_w - width) // 2, layout.subtitle_bottom - height


def draw_topics(
    topics: list[str], aspect: str, background: str, accent: str, with_image: bool
) -> tuple[Image.Image, int, int]:
    """PNG dos tópicos: caixa na cor de fundo, marcador na cor de destaque e texto exato.

    No 16:9 a caixa fica na coluna da direita, presa ao topo; no 9:16 fica acima da legenda,
    presa à base. Tópico longo quebra em linhas pela largura, sem trocar palavras.
    """
    layout = LAYOUTS[aspect]
    left, top, right, bottom = layout.topics_with_image if with_image else layout.topics
    size, pad = layout.topics_size, _padding(layout.topics_size)
    marker = round(size * 0.45)
    indent = marker + round(size * 0.5)
    while True:
        wrapped = [_wrap(_words(topic), size, right - left - 2 * pad - indent) for topic in topics]
        line_h, gap = _line_height(size), round(size * 0.45)
        rows = sum(len(lines) for lines in wrapped)
        height = 2 * pad + rows * line_h + gap * (len(topics) - 1)
        if height <= bottom - top or size <= 16:
            break
        size -= 2
    height = min(height, bottom - top)
    image = Image.new("RGBA", (right - left, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, right - left - 1, height - 1), radius=size // 2, fill=(*_rgb(background), 225)
    )
    y, ink = pad, (*text_color(background), 255)
    for lines in wrapped:
        mark_top = y + (line_h - marker) // 2
        draw.rectangle(
            (pad, mark_top, pad + marker - 1, mark_top + marker - 1), fill=(*_rgb(accent), 255)
        )
        for line in lines:
            text = " ".join(word.strip() for word in line)
            draw.text(
                (pad + indent, y + (line_h - size) // 2),
                text,
                font=font(size),
                fill=ink,
                anchor="lt",
            )
            y += line_h
        y += gap
    return image, left, top if aspect == "16:9" else bottom - height
