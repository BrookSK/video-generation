"""Áudio fixado na calibração não pode ser regenerado nem trocado antes do render."""

import hashlib
import io
import json
import wave
from pathlib import Path

import pytest
import test_pilot as base

from avatar_worker import pilot


@pytest.fixture
def env(tmp_path, monkeypatch):
    return base.env.__wrapped__(tmp_path, monkeypatch)


def _wav(*, channels=1, rate=24000, width=2, frames=24000):
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.writeframes(b"\x12" * frames * channels * width)
    return output.getvalue()


def _reviewed(env, tmp_path):
    directory = tmp_path / "reviewed"
    directory.mkdir()
    audio = _wav()
    (directory / "speech.wav").write_bytes(audio)
    request = {
        "text": base.TEXT,
        "language": "pt",
        "voice": base.RECIPE["tts"]["voices"]["feminina"],
        "models_dir": "/remote/models",
        "out_wav": "/remote/not-accessible/speech.wav",
    }
    result = {
        "audio_path": request["out_wav"],
        "duration_s": 1.0,
        "sample_rate": 24000,
        "watermark_detected": True,
        "peak_vram_mb": 4795.3,
        "elapsed_s": 40.0,
    }
    for name, value in (("tts_request.json", request), ("tts_result.json", result)):
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    digest = hashlib.sha256(audio).hexdigest()
    args = [
        *base._queue(env, base._sample("fixed", "9:16")),
        "--reviewed-tts-dir",
        str(directory),
        "--reviewed-audio-sha256",
        digest,
    ]
    return directory, audio, digest, args


def test_render_receives_exact_reviewed_bytes_even_if_source_changes(env, tmp_path, monkeypatch):
    directory, audio, digest, args = _reviewed(env, tmp_path)
    capture_audio = (
        'pathlib.Path(request["out_dir"], "render-audio-seen.wav").write_bytes('
        'pathlib.Path(request["audio"]).read_bytes())\n'
    )
    render = base._script(tmp_path / "capture-avatar", capture_audio + base.FAKE_AVATAR)
    args[args.index("--avatar-python") + 1] = str(render)
    original = pilot.ensure_alpha

    def replace_source(image):
        (directory / "speech.wav").write_bytes(b"changed after validation")
        return original(image)

    monkeypatch.setattr(pilot, "ensure_alpha", replace_source)

    assert pilot.main(args) == 0

    run_dir = env["out"] / "fixed" / "run-1"
    assert (run_dir / "render-audio-seen.wav").read_bytes() == audio
    assert (run_dir / "speech.wav").read_bytes() == audio
    assert base._events(env["log"]) == ["avatar:start:fixed/run-1", "avatar:end:fixed/run-1"]
    request = json.loads((run_dir / "tts_request.json").read_text())
    result = json.loads((run_dir / "tts_result.json").read_text())
    render_request = json.loads((run_dir / "avatar_request.json").read_text())
    assert request["out_wav"] == result["audio_path"] == render_request["audio"]
    assert Path(render_request["audio"]) == run_dir / "speech.wav"
    assert result["duration_s"] == 1.0
    run = base._report(env["out"], "fixed")["runs"][0]
    assert run["audio_source"] == {
        "kind": "reviewed",
        "directory": str(directory),
        "sha256": digest,
    }
    assert run["stages"]["tts"]["source"] == "reviewed"
    assert run["audio_seconds"] == 1.0
    assert run["watermark_detected"] is True


@pytest.mark.parametrize(
    "filename, field, value, message",
    [
        ("tts_request.json", "text", base.TEXT + " ", "text"),
        ("tts_request.json", "language", "en", "language"),
        ("tts_request.json", "voice", {"kind": "default"}, "voice"),
        ("tts_result.json", "sample_rate", 48000, "sample_rate"),
        ("tts_result.json", "duration_s", float("nan"), "duration_s"),
        ("tts_result.json", "watermark_detected", False, "watermark_detected"),
    ],
)
def test_incompatible_metadata_is_rejected_before_output_or_runtime(
    env, tmp_path, capsys, filename, field, value, message
):
    directory, _, _, args = _reviewed(env, tmp_path)
    path = directory / filename
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        pilot.main(args)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err
    assert not env["out"].exists()
    assert base._events(env["log"]) == []


@pytest.mark.parametrize(
    "audio, message",
    [
        (_wav(channels=2), "mono"),
        (_wav(rate=16000), "24000"),
        (_wav(width=1), "16 bits"),
        (_wav()[:-2], "incompleto"),
    ],
    ids=["stereo", "wrong-rate", "wrong-width", "truncated"],
)
def test_invalid_wav_is_rejected_before_output_or_runtime(env, tmp_path, capsys, audio, message):
    directory, _, _, args = _reviewed(env, tmp_path)
    (directory / "speech.wav").write_bytes(audio)
    args[-1] = hashlib.sha256(audio).hexdigest()

    with pytest.raises(SystemExit) as exc:
        pilot.main(args)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err
    assert not env["out"].exists()
    assert base._events(env["log"]) == []


def test_hash_is_required_to_match_the_audio_before_output(env, tmp_path, capsys):
    _, _, _, args = _reviewed(env, tmp_path)
    args[-1] = "0" * 64

    with pytest.raises(SystemExit) as exc:
        pilot.main(args)

    assert exc.value.code == 2
    assert "SHA-256" in capsys.readouterr().err
    assert not env["out"].exists()
    assert base._events(env["log"]) == []


def test_reviewed_audio_above_effective_limit_is_rejected_before_output(env, tmp_path, capsys):
    _, _, _, args = _reviewed(env, tmp_path)

    with pytest.raises(SystemExit) as exc:
        pilot.main([*args, "--max-audio-seconds", "0.5"])

    assert exc.value.code == 2
    assert "limite" in capsys.readouterr().err
    assert not env["out"].exists()
    assert base._events(env["log"]) == []


def test_reviewed_mode_rejects_ambiguous_options_before_output(env, tmp_path, capsys):
    directory, _, digest, args = _reviewed(env, tmp_path)
    invalid_options = [
        (1, args[:-2]),
        (1, [*args[:-4], "--reviewed-audio-sha256", digest]),
        (1, [*args, "--runs", "2"]),
        (2, args),
    ]
    for count, invalid in invalid_options:
        base._queue(env, *(base._sample(f"sample{n}", "9:16") for n in range(count)))
        with pytest.raises(SystemExit) as exc:
            pilot.main(invalid)

        assert exc.value.code == 2
        assert "revisado" in capsys.readouterr().err
        assert not env["out"].exists()
        assert base._events(env["log"]) == []


def test_without_reviewed_flags_the_original_tts_flow_is_preserved(env):
    assert pilot.main(base._queue(env, base._sample("original", "9:16"))) == 0
    assert base._events(env["log"]) == base._run_events("original/run-1")
    assert "audio_source" not in base._report(env["out"], "original")["runs"][0]


def _qwen_reviewed(env, tmp_path, watermark):
    import test_recipe

    directory, _, _, args = _reviewed(env, tmp_path)
    recipe = test_recipe._recipe(test_recipe._qwen)
    recipe_path = tmp_path / "recipe-qwen.json"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
    manifest = tmp_path / "manifest-qwen.json"
    manifest.write_text(json.dumps(test_recipe.QWEN_MANIFEST), encoding="utf-8")
    args[args.index("--recipe") + 1] = str(recipe_path)
    args[args.index("--manifest") + 1] = str(manifest)
    request = json.loads((directory / "tts_request.json").read_text())
    request.update(
        engine="qwen3-tts-base",
        voice=recipe["tts"]["voices"]["feminina"],
        sampler=test_recipe.SAMPLER,
    )
    (directory / "tts_request.json").write_text(json.dumps(request), encoding="utf-8")
    result = json.loads((directory / "tts_result.json").read_text())
    result["watermark_detected"] = watermark
    (directory / "tts_result.json").write_text(json.dumps(result), encoding="utf-8")
    return directory, args


def test_qwen_reviewed_audio_requires_null_watermark(env, tmp_path):
    _, args = _qwen_reviewed(env, tmp_path, None)

    assert pilot.main(args) == 0

    run = base._report(env["out"], "fixed")["runs"][0]
    assert run["watermark_detected"] is None


@pytest.mark.parametrize(
    "filename, field, value, message",
    [
        ("tts_result.json", "watermark_detected", True, "precisa ser null na engine Qwen"),
        ("tts_request.json", "engine", "chatterbox-multilingual", "request.engine"),
        ("tts_request.json", "sampler", {"seed": 1}, "request.sampler"),
    ],
    ids=["watermark-alegada", "engine-trocada", "sampler-diferente"],
)
def test_qwen_reviewed_audio_rejects_other_engine_metadata(
    env, tmp_path, capsys, filename, field, value, message
):
    directory, args = _qwen_reviewed(env, tmp_path, None)
    data = json.loads((directory / filename).read_text())
    data[field] = value
    (directory / filename).write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        pilot.main(args)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err
    assert not env["out"].exists()
