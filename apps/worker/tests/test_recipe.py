import copy
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from avatar_worker.recipe import RecipeError, check_recipe, load_recipe, main

MODELS_DIR = Path(__file__).resolve().parents[3] / "docs" / "models"
RECIPE_PATH = MODELS_DIR / "RECIPE-v1.json"
MANIFEST_PATH = MODELS_DIR / "MODEL_MANIFEST.json"
DRAFT = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

MEASUREMENT = {
    "audio_seconds": 30.2,
    "stages": {
        "tts": {"seconds": 12.5, "vram_peak_mb": 6100},
        "render": {"seconds": 610.0, "vram_peak_mb": 21800},
        "finalize": {"seconds": 4.1, "vram_peak_mb": 0},
    },
    "seconds_per_video_second": {"cold": 24.1, "warm": 20.6},
}


def _frozen(recipe):
    recipe["status"] = "frozen"
    recipe["worker_image"]["digest"] = "sha256:" + "b" * 64
    recipe["pilot"] = {
        "formats": {"9:16": copy.deepcopy(MEASUREMENT), "16:9": copy.deepcopy(MEASUREMENT)},
        "approved_max_audio_seconds": 40,
        "evaluation": {"evaluator": "human:felipe", "date": "2026-10-01", "verdict": "aprovado"},
    }


def _recipe(*mutations):
    recipe = copy.deepcopy(DRAFT)
    for mutate in mutations:
        mutate(recipe)
    return recipe


def _write(tmp_path, recipe):
    path = tmp_path / "RECIPE.json"
    path.write_text(json.dumps(recipe), encoding="utf-8")
    return path


def _set(dotted, value):
    *parents, key = dotted.split(".")

    def mutate(recipe):
        target = recipe
        for parent in parents:
            target = target[parent]
        target[key] = value

    return mutate


def _drop(dotted):
    *parents, key = dotted.split(".")

    def mutate(recipe):
        target = recipe
        for parent in parents:
            target = target[parent]
        del target[key]

    return mutate


def test_repository_draft_loads_as_frozen_dataclasses():
    recipe = load_recipe(RECIPE_PATH, MANIFEST_PATH)

    assert recipe.status == "draft"
    assert recipe.avatar.profile == "480p-fp8"
    assert recipe.avatar.size == "infinitetalk-480"
    assert recipe.avatar.quant == "fp8"
    assert recipe.avatar.num_persistent_param_in_dit == 0
    assert recipe.avatar.mode == "streaming"
    assert recipe.avatar.max_frame_num == 1000
    assert recipe.avatar.buckets["9:16"] == (448, 832)
    assert recipe.avatar.buckets["16:9"] == (896, 448)
    assert recipe.canvas == {"9:16": (1080, 1920), "16:9": (1920, 1080)}
    assert recipe.output.fps == 25
    assert recipe.limits.max_audio_seconds == 40
    assert recipe.limits.max_script_chars == 600
    assert recipe.limits.chars_per_second == 15
    assert {voice.kind for voice in recipe.tts.voices.values()} == {"default"}
    assert recipe.pilot is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        recipe.status = "frozen"
    with pytest.raises(TypeError):
        recipe.avatar.buckets["9:16"] = (1, 2)


def test_validate_cli_accepts_draft_and_refuses_it_with_frozen(capsys):
    args = ["validate", str(RECIPE_PATH), "--manifest", str(MANIFEST_PATH)]

    assert main(args) == 0
    assert "Receita RECIPE-v1 (draft) válida" in capsys.readouterr().out

    assert main([*args, "--frozen"]) == 1
    err = capsys.readouterr().err
    assert "Receita recusada" in err
    assert "congelada: worker_image.digest" in err
    assert "congelada: pilot precisa trazer as medições do piloto" in err


def test_module_entry_point_exit_codes():
    command = [sys.executable, "-m", "avatar_worker.recipe", "validate", str(RECIPE_PATH)]
    command += ["--manifest", str(MANIFEST_PATH)]

    ok = subprocess.run(command, capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stderr
    refused = subprocess.run([*command, "--frozen"], capture_output=True, text=True, check=False)
    assert refused.returncode == 1


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            _set("avatar.components", ["infinitetalk-code", "longcat-avatar"]),
            "avatar.components: 'longcat-avatar' não existe no manifesto",
        ),
        (
            _set("tts.components", ["chatterbox-tts", "chatterbox-v9"]),
            "tts.components: 'chatterbox-v9' não existe no manifesto",
        ),
        (
            _set("avatar.wheels", ["flash-attn-wheel", "infinitetalk-weights"]),
            "avatar.wheels: infinitetalk-weights tem kind 'model' no manifesto, esperado wheel",
        ),
        (
            _set("cutout.components", ["xformers-wheel"]),
            "cutout.components: xformers-wheel tem kind 'wheel'",
        ),
        (_set("cutout.model", "bria-rmbg"), "cutout.model: 'bria-rmbg' não existe no manifesto"),
        (_set("avatar.buckets.9:16", [832, 448]), "avatar.buckets.9:16 [832, 448] não é retrato"),
        (
            _set("avatar.buckets.16:9", [448, 896]),
            "avatar.buckets.16:9 [448, 896] não é paisagem",
        ),
        (_drop("avatar.buckets.16:9"), "avatar.buckets precisa ter exatamente os formatos"),
        (_drop("tts.voices.masculina"), "tts.voices sem a voz masculina"),
        (_drop("tts.voices.feminina"), "tts.voices sem a voz feminina"),
        (
            _set("tts.voices.feminina", {"kind": "reference", "path": "/srv/voz.wav"}),
            "tts.voices.feminina.path precisa ser caminho relativo a /models",
        ),
        (
            _set("tts.voices.feminina", {"kind": "reference", "path": "../voz.wav"}),
            "tts.voices.feminina.path precisa ser caminho relativo a /models",
        ),
        (_set("tts.voices.masculina", {"kind": "clone"}), "tts.voices.masculina.kind 'clone'"),
        (
            _set("limits.max_script_chars", 601),
            "limits.max_script_chars 601 acima de max_audio_seconds * chars_per_second (40 * 15",
        ),
        (
            _set("limits.chars_per_second", 12),
            "limits.max_script_chars 600 acima de max_audio_seconds * chars_per_second (40 * 12",
        ),
        (
            _set("avatar.max_frame_num", 1500),
            "avatar.max_frame_num 1500 incoerente com limits.max_audio_seconds 40",
        ),
        (_set("output.fps", 30), "output.fps precisa ser 25"),
        (_set("canvas.9:16", [1080, 1080]), "canvas precisa ser exatamente"),
        (_set("canvas.1:1", [1080, 1080]), "canvas precisa ser exatamente"),
        (_set("avatar.mode", "clip"), "avatar.mode precisa ser 'streaming'"),
        (_set("status", "approved"), "status 'approved' fora de draft, frozen"),
        (_set("worker_image.digest", "latest"), "worker_image.digest precisa ser sha256:"),
    ],
)
def test_incoherent_recipe_is_refused(tmp_path, capsys, mutate, expected):
    path = _write(tmp_path, _recipe(mutate))

    with pytest.raises(RecipeError) as refused:
        load_recipe(path, MANIFEST_PATH)
    assert any(expected in problem for problem in refused.value.problems), refused.value.problems

    assert main(["validate", str(path), "--manifest", str(MANIFEST_PATH)]) == 1
    assert expected in capsys.readouterr().err


def test_complete_frozen_recipe_is_accepted(tmp_path):
    reference = {"kind": "reference", "path": "voices/feminina.wav", "sha256": "c" * 64}
    recipe = _recipe(_frozen, _set("tts.voices.feminina", reference))

    assert check_recipe(recipe, MANIFEST) == []
    loaded = load_recipe(_write(tmp_path, recipe), MANIFEST_PATH, require_frozen=True)
    assert loaded.pilot["formats"]["9:16"]["stages"]["render"]["vram_peak_mb"] == 21800
    assert loaded.tts.voices["feminina"].sha256 == "c" * 64


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_set("worker_image.digest", None), "congelada: worker_image.digest"),
        (
            _set("tts.voices.feminina", {"kind": "reference", "path": "voices/f.wav"}),
            "congelada: tts.voices.feminina de referência sem sha256",
        ),
        (_set("pilot", None), "congelada: pilot precisa trazer as medições do piloto"),
        (_drop("pilot.formats.16:9"), "congelada: pilot.formats.16:9 sem medições"),
        (
            _drop("pilot.formats.9:16.stages.render.vram_peak_mb"),
            "congelada: pilot.formats.9:16.stages.render.vram_peak_mb",
        ),
        (
            _drop("pilot.formats.9:16.stages.tts.seconds"),
            "congelada: pilot.formats.9:16.stages.tts.seconds",
        ),
        (_set("pilot.formats.16:9.stages", {}), "congelada: pilot.formats.16:9.stages precisa"),
        (_drop("pilot.formats.9:16.audio_seconds"), "congelada: pilot.formats.9:16.audio_seconds"),
        (
            _drop("pilot.formats.16:9.seconds_per_video_second.warm"),
            "congelada: pilot.formats.16:9.seconds_per_video_second.warm",
        ),
        (
            _drop("pilot.formats.16:9.seconds_per_video_second.cold"),
            "congelada: pilot.formats.16:9.seconds_per_video_second.cold",
        ),
        (
            _set("pilot.approved_max_audio_seconds", 60),
            "congelada: pilot.approved_max_audio_seconds 60 diferente de "
            "limits.max_audio_seconds 40",
        ),
        (
            _set("pilot.evaluation.verdict", "reprovado"),
            "congelada: pilot.evaluation.verdict precisa ser 'aprovado'",
        ),
        (_drop("pilot.evaluation"), "congelada: pilot.evaluation.verdict precisa ser"),
    ],
)
def test_frozen_recipe_without_measurements_is_refused(mutate, expected):
    problems = check_recipe(_recipe(_frozen, mutate), MANIFEST)

    assert any(expected in problem for problem in problems), problems


def test_frozen_flag_applies_frozen_rules_to_draft():
    draft = _recipe()

    assert check_recipe(draft, MANIFEST) == []
    assert "congelada: pilot precisa trazer as medições do piloto" in check_recipe(
        draft, MANIFEST, require_frozen=True
    )


def test_unreadable_files_are_reported(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    assert main(["validate", str(broken), "--manifest", str(MANIFEST_PATH)]) == 1
    assert "não foi possível ler a receita" in capsys.readouterr().err
    assert main(["validate", str(RECIPE_PATH), "--manifest", str(broken)]) == 1
    assert "não foi possível ler o manifesto" in capsys.readouterr().err
