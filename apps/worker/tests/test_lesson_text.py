"""Legenda e tópicos da aula: texto literal, quebra por largura, tempo pelo áudio e cores."""

import os
import subprocess
from pathlib import Path

import pytest

from avatar_worker.lesson_text import (
    LAYOUTS,
    MAX_SUBTITLE_LINES,
    detect_speech,
    draw_subtitle,
    draw_topics,
    font,
    parse_silences,
    speech_intervals,
    split_subtitles,
    text_color,
    time_chunks,
)

BACKGROUND = "#0B2545"
ACCENT = "#F2A541"
LONG = (
    "Antes de qualquer demolição, isole a área com fita zebrada e placas de aviso, "
    "confira se a rede elétrica foi desligada no quadro geral e chame o técnico responsável "
    "para assinar a liberação. Depois disso, use capacete, luvas, óculos e botina com biqueira!"
)


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def near(pixel, expected, tolerance=3) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, expected, strict=False))


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
@pytest.mark.parametrize(
    "text",
    [
        LONG,
        "  Espaços  duplos,\nquebra de linha e\tTAB. Fim sem ponto",
        "Palavraenormesemespacosquepassadalarguradacaixadelegendaeprecisaficarsozinhanalinha ok.",
    ],
)
def test_trechos_juntos_sao_o_texto_literal_com_ate_duas_linhas(aspect, text):
    chunks = split_subtitles(text, aspect)

    assert "".join(chunk.text for chunk in chunks) == text
    assert all(1 <= len(chunk.lines) <= MAX_SUBTITLE_LINES for chunk in chunks)
    shown = " ".join(line for chunk in chunks for line in chunk.lines).split()
    assert shown == text.split()


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
def test_quebra_pela_largura_medida_com_a_fonte(aspect):
    layout = LAYOUTS[aspect]
    chunks = split_subtitles(LONG, aspect)

    assert len(chunks) > 2
    limit = layout.subtitle_width - 2 * round(layout.subtitle_size * 0.6)
    for chunk in chunks:
        for line in chunk.lines:
            assert font(layout.subtitle_size).getlength(line) <= limit
    # Cada trecho cabe numa frase: o primeiro termina em ponto, o último em exclamação.
    assert [chunk.sentence for chunk in chunks] == sorted(chunk.sentence for chunk in chunks)
    assert {chunk.sentence for chunk in chunks} == {0, 1}


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
def test_legenda_usa_as_cores_da_identidade(aspect):
    chunk = split_subtitles("Isolar a área antes de começar.", aspect)[0]

    image, x, y = draw_subtitle(chunk, aspect, BACKGROUND, ACCENT)

    width = 1920 if aspect == "16:9" else 1080
    assert x == (width - image.width) // 2
    assert y + image.height == LAYOUTS[aspect].subtitle_bottom
    assert near(image.getpixel((image.width // 2, 1)), (*rgb(ACCENT), 255))
    assert near(image.getpixel((8, image.height // 2)), (*rgb(BACKGROUND), 225))
    colors = {pixel[:3] for pixel in image.getdata() if pixel[3] == 255}
    assert text_color(BACKGROUND) == (255, 255, 255)
    assert (255, 255, 255) in colors


def test_texto_escuro_sobre_fundo_claro():
    chunk = split_subtitles("Texto sobre fundo claro.", "16:9")[0]

    image, _, _ = draw_subtitle(chunk, "16:9", "#F1F2F7", ACCENT)

    assert text_color("#F1F2F7") == (17, 17, 17)
    assert (17, 17, 17) in {pixel[:3] for pixel in image.getdata() if pixel[3] == 255}


@pytest.mark.parametrize(
    ("aspect", "with_image"), [("16:9", False), ("16:9", True), ("9:16", False), ("9:16", True)]
)
def test_topicos_na_area_do_formato_com_marcador_de_destaque(aspect, with_image):
    layout = LAYOUTS[aspect]
    topics = [
        "Isolar a área",
        "Usar EPI",
        "Conferir a rede elétrica no quadro geral antes de iniciar o trabalho",
    ]

    image, x, y = draw_topics(topics, aspect, BACKGROUND, ACCENT, with_image)

    left, top, right, bottom = layout.topics_with_image if with_image else layout.topics
    assert (x, image.width) == (left, right - left)
    assert top <= y and y + image.height <= bottom
    if aspect == "16:9":
        assert y == top
    else:
        assert y + image.height == bottom
    assert near(image.getpixel((6, image.height // 2)), (*rgb(BACKGROUND), 225))
    accent = sum(1 for pixel in image.getdata() if near(pixel, (*rgb(ACCENT), 255)))
    assert accent > 3 * 10  # um marcador por tópico


def test_silencios_viram_intervalos_de_fala():
    log = "\n".join(
        [
            "[silencedetect @ 0x1] silence_start: 0",
            "[silencedetect @ 0x1] silence_end: 0.2 | silence_duration: 0.2",
            "[silencedetect @ 0x1] silence_start: 1.5",
            "[silencedetect @ 0x1] silence_end: 2.1 | silence_duration: 0.6",
            "[silencedetect @ 0x1] silence_start: 3.9",
        ]
    )

    silences = parse_silences(log, 4.0)

    assert silences == [(0.0, 0.2), (1.5, 2.1), (3.9, 4.0)]
    assert speech_intervals(silences, 4.0) == [(0.2, 1.5), (2.1, 3.9)]


def _speech_audio(path: Path, pattern: list[tuple[str, float]]) -> Path:
    """WAV com tom (fala) e silêncio nas durações dadas."""
    inputs, labels = [], []
    for index, (kind, seconds) in enumerate(pattern):
        source = f"sine=frequency=440:sample_rate=48000:duration={seconds}"
        if kind == "silencio":
            source = f"anullsrc=r=48000:cl=mono,atrim=0:{seconds}"
        inputs += ["-f", "lavfi", "-i", source]
        labels.append(f"[{index}:a]")
    graph = "".join(labels) + f"concat=n={len(pattern)}:v=0:a=1[a]"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[a]",
            str(path),
        ],
        check=True,
    )
    return path


def test_trechos_ficam_dentro_da_frase_falada(tmp_path):
    text = (
        "Primeira frase curta. Segunda frase, um pouco maior que a primeira e com mais palavras "
        "para quebrar em linhas e talvez em mais de um trecho de legenda na tela. Terceira!"
    )
    pattern = [
        ("silencio", 0.3),
        ("fala", 1.2),
        ("silencio", 0.6),
        ("fala", 2.5),
        ("silencio", 0.6),
        ("fala", 0.7),
        ("silencio", 0.4),
    ]
    audio = _speech_audio(tmp_path / "cena.wav", pattern)
    duration = sum(seconds for _, seconds in pattern)

    speech = detect_speech(audio, duration, tmp_path, "cena", lambda: None, os.environ)
    chunks, method = time_chunks(split_subtitles(text, "9:16"), speech, duration)

    assert method == "silence"
    assert len(speech) == 3
    expected = [(0.3, 1.5), (2.1, 4.6), (5.2, 5.9)]
    for (start, end), (want_start, want_end) in zip(speech, expected, strict=True):
        assert abs(start - want_start) < 0.1 and abs(end - want_end) < 0.1
    assert len(chunks) > 3
    for chunk in chunks:
        start, end = speech[chunk.sentence]
        assert start <= chunk.start < chunk.end <= end + 1e-6
    assert "".join(chunk.text for chunk in chunks) == text


def test_intervalos_que_nao_casam_usam_os_caracteres_na_cena_inteira():
    text = "Uma frase. Outra frase. Mais uma."
    chunks = split_subtitles(text, "16:9")

    timed, method = time_chunks(chunks, [(0.5, 3.0)], 6.0)

    assert method == "characters"
    assert timed[0].start == 0.0 and timed[-1].end == 6.0
    for previous, current in zip(timed, timed[1:], strict=False):
        assert previous.end == current.start
    assert "".join(chunk.text for chunk in timed) == text
