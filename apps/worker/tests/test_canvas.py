import math
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from avatar_worker import cutout
from avatar_worker.canvas import bucket_frame, canvas_cut, compose_canvas, extend_to_bucket
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


# Buckets de wan/utils/multitalk_utils.py do InfiniteTalk no commit 50aa0a94 do manifesto:
# chave altura/largura, valor [[altura, largura], 1].
ASPECT_RATIO_627 = {
    "0.26": ([320, 1216], 1), "0.38": ([384, 1024], 1), "0.50": ([448, 896], 1),
    "0.67": ([512, 768], 1), "0.82": ([576, 704], 1), "1.00": ([640, 640], 1),
    "1.22": ([704, 576], 1), "1.50": ([768, 512], 1), "1.86": ([832, 448], 1),
    "2.00": ([896, 448], 1), "2.50": ([960, 384], 1), "2.83": ([1088, 384], 1),
    "3.60": ([1152, 320], 1), "3.80": ([1216, 320], 1), "4.00": ([1280, 320], 1),
}  # fmt: skip
ASPECT_RATIO_960 = {
    "0.22": ([448, 2048], 1), "0.29": ([512, 1792], 1), "0.36": ([576, 1600], 1),
    "0.45": ([640, 1408], 1), "0.55": ([704, 1280], 1), "0.63": ([768, 1216], 1),
    "0.76": ([832, 1088], 1), "0.88": ([896, 1024], 1), "1.00": ([960, 960], 1),
    "1.14": ([1024, 896], 1), "1.31": ([1088, 832], 1), "1.50": ([1152, 768], 1),
    "1.58": ([1216, 768], 1), "1.82": ([1280, 704], 1), "1.91": ([1344, 704], 1),
    "2.20": ([1408, 640], 1), "2.30": ([1472, 640], 1), "2.67": ([1536, 576], 1),
    "2.89": ([1664, 576], 1), "3.62": ([1856, 512], 1), "3.75": ([1920, 512], 1),
}  # fmt: skip
PROFILES = {"infinitetalk-480": ASPECT_RATIO_627, "infinitetalk-720": ASPECT_RATIO_960}
CANVAS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
MODELS_DIR = Path(__file__).resolve().parents[3] / "docs" / "models"


def _infinitetalk(source_size, profile):
    """Oráculo do InfiniteTalk (wan/multitalk.py, generate): bucket de razão mais próxima e
    resize_and_centercrop (escala max com ceil, corte central com round do torchvision).

    Devolve o bucket (largura, altura) e quanto do retângulo de origem cada lado perde,
    em pixels de origem: esquerda, topo, direita, base."""
    src_w, src_h = source_size
    table = PROFILES[profile]
    ratio = src_h / src_w
    closest = sorted(table, key=lambda key: abs(float(key) - ratio))[0]
    target_h, target_w = table[closest][0]
    scale = max(target_h / src_h, target_w / src_w)
    final_h, final_w = math.ceil(scale * src_h), math.ceil(scale * src_w)
    top = int(round((final_h - target_h) / 2.0))
    left = int(round((final_w - target_w) / 2.0))
    return (target_w, target_h), scale, (left, top, left + target_w, top + target_h)


def _content_cut(frame_size, offset, canvas_size, profile):
    bucket, scale, (left, top, right, bottom) = _infinitetalk(frame_size, profile)
    x, y = offset
    width, height = canvas_size
    cuts = (
        left / scale - x,
        top / scale - y,
        (x + width) - right / scale,
        (y + height) - bottom / scale,
    )
    return bucket, cuts


def _profile_bucket(profile, aspect):
    bucket, _, _ = _infinitetalk(CANVAS[aspect], profile)
    return bucket


def test_recipe_buckets_are_infinitetalk_480_choice_for_each_canvas():
    from avatar_worker.recipe import load_recipe

    recipe = load_recipe(MODELS_DIR / "RECIPE-v1.json", MODELS_DIR / "MODEL_MANIFEST.json")
    assert recipe.avatar.size == "infinitetalk-480"
    for aspect, canvas in CANVAS.items():
        assert recipe.canvas[aspect] == canvas
        assert recipe.avatar.buckets[aspect] == _profile_bucket("infinitetalk-480", aspect)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("aspect", CANVAS)
def test_canvas_sent_directly_to_render_loses_its_edges(profile, aspect):
    canvas = CANVAS[aspect]
    bucket, cuts = _content_cut(canvas, (0, 0), canvas, profile)

    assert max(cuts) > 1
    assert canvas_cut(canvas, (0, 0), canvas, bucket) == math.ceil(max(cuts))


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("aspect", CANVAS)
def test_bucket_frame_keeps_whole_canvas_through_infinitetalk_crop(profile, aspect):
    canvas = CANVAS[aspect]
    bucket = _profile_bucket(profile, aspect)
    frame = bucket_frame(canvas, bucket)
    (frame_w, frame_h), (x, y) = frame.size, frame.offset

    assert frame_w * bucket[1] == frame_h * bucket[0]
    assert 0 <= x and x + canvas[0] <= frame_w
    assert 0 <= y and y + canvas[1] <= frame_h
    assert x % 2 == 0 and y % 2 == 0
    chosen, cuts = _content_cut(frame.size, frame.offset, canvas, profile)
    assert chosen == bucket
    assert all(cut <= 0 for cut in cuts), cuts
    assert frame.canvas_cut_px == 0
    assert canvas_cut(frame.size, frame.offset, canvas, bucket) == 0


def test_extend_to_bucket_pads_with_scene_color_and_keeps_canvas_pixels():
    canvas = Image.new("RGB", (1080, 1920), RED)
    canvas.paste(BLUE, (0, 0, 1, 1))
    frame = bucket_frame((1080, 1920), (448, 832))

    extended = extend_to_bucket(canvas, frame, BACKGROUND)

    assert extended.size == frame.size
    x, y = frame.offset
    assert extended.getpixel((0, 0)) == BACKGROUND_RGB
    assert extended.getpixel((frame.size[0] - 1, frame.size[1] - 1)) == BACKGROUND_RGB
    assert extended.getpixel((x, y)) == BLUE
    assert extended.getpixel((x + 1079, y + 1919)) == RED
    assert extended.crop((x, y, x + 1080, y + 1920)).tobytes() == canvas.tobytes()


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
