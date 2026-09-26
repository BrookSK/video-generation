import pytest
from PIL import Image, ImageChops

from avatar_worker import cutout
from avatar_worker.canvas import compose_canvas
from avatar_worker.cutout import CutoutError, ensure_alpha

BACKGROUND = "#1f2937"
BACKGROUND_RGB = (31, 41, 55)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
FORMATS = {
    "9:16": ((1080, 1920), {"scale": 0.8, "x": 0.5, "y": 1.0}),
    "16:9": ((1920, 1080), {"scale": 0.9, "x": 0.5, "y": 1.0}),
}


def _avatar(width=300, height=600):
    """Avatar opaco: metade de cima vermelha, metade de baixo azul."""
    avatar = Image.new("RGBA", (width, height), (*BLUE, 255))
    avatar.paste((*RED, 255), (0, 0, width, height // 2))
    return avatar


def _avatar_box(canvas):
    return ImageChops.difference(canvas, Image.new("RGB", canvas.size, BACKGROUND_RGB)).getbbox()


@pytest.mark.parametrize("aspect", FORMATS)
def test_canvas_has_format_size_and_background_corners(aspect):
    size, composition = FORMATS[aspect]
    canvas = compose_canvas(_avatar(), BACKGROUND, composition, size)

    assert canvas.size == size
    assert canvas.mode == "RGB"
    width, height = size
    for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        assert canvas.getpixel(corner) == BACKGROUND_RGB


@pytest.mark.parametrize("aspect", FORMATS)
def test_avatar_height_is_scale_of_canvas_with_original_proportion(aspect):
    size, composition = FORMATS[aspect]
    width, height = size
    avatar = _avatar()
    canvas = compose_canvas(avatar, BACKGROUND, composition, size)

    left, top, right, bottom = _avatar_box(canvas)
    expected_height = round(composition["scale"] * height)
    assert bottom - top == expected_height
    assert right - left == round(avatar.width * expected_height / avatar.height)
    assert bottom == round(composition["y"] * height)
    assert (left + right) / 2 == pytest.approx(composition["x"] * width, abs=1)


def test_transparent_avatar_pixels_show_background():
    avatar = _avatar()
    avatar.paste((0, 0, 0, 0), (0, 0, 300, 300))
    size, composition = FORMATS["9:16"]
    canvas = compose_canvas(avatar, BACKGROUND, composition, size)

    assert canvas.getpixel((540, 500)) == BACKGROUND_RGB
    assert canvas.getpixel((540, 1100)) == BACKGROUND_RGB
    assert canvas.getpixel((540, 1800)) == BLUE


def test_background_image_is_covered_and_centered():
    stripes = Image.new("RGB", (400, 100), BLUE)
    stripes.paste(RED, (0, 0, 100, 100))
    stripes.paste(RED, (300, 0, 400, 100))
    transparent = Image.new("RGBA", (10, 10), (0, 0, 0, 0))

    for size, composition in FORMATS.values():
        canvas = compose_canvas(transparent, stripes, composition, size)
        width, height = size
        assert canvas.size == size
        for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
            assert canvas.getpixel(corner) == BLUE


def test_avatar_leaving_canvas_is_cut_at_the_edge_not_stretched():
    size = (1080, 1920)
    avatar = _avatar(width=200)
    canvas = compose_canvas(avatar, BACKGROUND, {"scale": 1.2, "x": 0.5, "y": 1.1}, size)

    left, top, right, bottom = _avatar_box(canvas)
    assert (top, bottom) == (0, 1920)
    assert right - left == 768
    # Avatar de 2304 px com topo em -192: a troca de vermelho para azul fica em 960.
    assert canvas.getpixel((540, 950)) == RED
    assert canvas.getpixel((540, 970)) == BLUE


def test_invalid_background_color_is_refused():
    with pytest.raises(ValueError, match="#RRGGBB"):
        compose_canvas(_avatar(), "azul", FORMATS["9:16"][1], (1080, 1920))


class _FakeSession:
    def __init__(self, calls, name):
        calls.append(name)

    def predict(self, img, *args, **kwargs):
        mask = Image.new("L", img.size, 0)
        mask.paste(255, (img.width // 4, 0, img.width * 3 // 4, img.height))
        return [mask]


def _factory(calls):
    return lambda name: _FakeSession(calls, name)


def test_rgba_with_transparency_is_returned_without_cutout():
    calls = []
    image = _avatar()
    image.putpixel((0, 0), (0, 0, 0, 0))

    assert ensure_alpha(image, _factory(calls)) is image
    assert calls == []


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_image_without_useful_alpha_is_cut_with_birefnet_portrait(mode):
    calls = []
    image = _avatar().convert(mode)

    result = ensure_alpha(image, _factory(calls))

    assert calls == ["birefnet-portrait"]
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((150, 0)) == (*RED, 255)


def test_local_session_opens_only_birefnet_portrait_from_u2net_home(tmp_path, monkeypatch):
    calls = []
    (tmp_path / "birefnet-portrait.onnx").write_bytes(b"onnx")
    monkeypatch.setenv("U2NET_HOME", str(tmp_path))
    monkeypatch.setattr(cutout, "new_session", _factory(calls))

    ensure_alpha(_avatar().convert("RGB"))

    assert calls == ["birefnet-portrait"]


@pytest.mark.parametrize("home", [None, "empty"])
def test_local_session_refuses_missing_model_without_download(home, tmp_path, monkeypatch):
    if home is None:
        monkeypatch.delenv("U2NET_HOME", raising=False)
    else:
        monkeypatch.setenv("U2NET_HOME", str(tmp_path))
    monkeypatch.setattr(cutout, "new_session", lambda name: pytest.fail("não pode abrir sessão"))

    with pytest.raises(CutoutError):
        ensure_alpha(_avatar().convert("RGB"))
