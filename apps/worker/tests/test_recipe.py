import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from avatar_worker.recipe import RecipeError, check_recipe, load_recipe, main, recipe_from_mapping

MODELS_DIR = Path(__file__).resolve().parents[3] / "docs" / "models"
RECIPE_PATH = MODELS_DIR / "RECIPE-v1.json"
MANIFEST_PATH = MODELS_DIR / "MODEL_MANIFEST.json"
DRAFT = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
FEMININA = DRAFT["tts"]["voices"]["feminina"]

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
            _set("tts.voices.feminina", {"kind": "default"}),
            "tts.voices.feminina.kind 'default' fora de reference",
        ),
        (
            _drop("tts.voices.feminina.sha256"),
            "tts.voices.feminina.sha256 precisa ter 64 hexadecimais",
        ),
        (
            _set("tts.voices.masculina.sha256", "0" * 64),
            "tts.voices.masculina: kokoro-voice-references/pm_alex.wav com sha256 "
            + "0" * 64
            + " não é arquivo derived do manifesto",
        ),
        (
            _set("tts.voices.masculina", {**FEMININA, "path": "kokoro-voice-references/copia.wav"}),
            "tts.voices precisam de referências distintas",
        ),
        (_drop("avatar.lora"), "avatar.lora ausente"),
        (
            _set("avatar.lora.component", "kokoro-voice-references"),
            "avatar.lora.component 'kokoro-voice-references' não é componente model do manifesto",
        ),
        (
            _set(
                "avatar.lora.file",
                "Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors",
            ),
            "avatar.lora.file 'Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors' "
            "não é arquivo de lightx2v-lora no manifesto",
        ),
        (
            _set("avatar.lora.sha256", "0" * 64),
            "avatar.lora.sha256 '" + "0" * 64 + "' diferente do manifesto em lightx2v-lora",
        ),
        (_set("avatar.lora.scale", 0), "avatar.lora.scale precisa ser número finito e positivo"),
        (
            _set("avatar.sample_text_guide_scale", float("inf")),
            "avatar.sample_text_guide_scale precisa ser número finito e positivo",
        ),
        (
            _set("avatar.sample_audio_guide_scale", -2.0),
            "avatar.sample_audio_guide_scale precisa ser número finito e positivo",
        ),
        (_set("avatar.sample_steps", 0), "avatar.sample_steps precisa ser inteiro >= 1"),
        (
            _set("avatar.quant", "fp8"),
            "avatar.quant 'fp8' não roda na imagem do worker: a quantização compila a extensão "
            "CUDA do optimum-quanto na primeira inferência e a imagem não tem nvcc",
        ),
        (
            _set("avatar.negative_prompt", "hands, gestures"),
            "avatar.negative_prompt precisa ser null: o generate_infinitetalk.py fixado (50aa0a94)",
        ),
        (
            _set("calibration.composition.16:9.y", 0.4),
            "calibration.composition.16:9.y 0.4 fora da faixa de 0.5 a 1.2",
        ),
        (
            _drop("calibration.composition.9:16"),
            "calibration.composition precisa ter exatamente os formatos 9:16, 16:9",
        ),
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
    recipe = _recipe(_frozen)

    assert check_recipe(recipe, MANIFEST) == []
    loaded = load_recipe(_write(tmp_path, recipe), MANIFEST_PATH, require_frozen=True)
    assert loaded.pilot["formats"]["9:16"]["stages"]["render"]["vram_peak_mb"] == 21800
    assert loaded.tts.voices["feminina"].sha256 == FEMININA["sha256"]
    assert loaded.avatar.lora == DRAFT["avatar"]["lora"]
    assert json.loads(json.dumps(loaded.avatar.lora)) == DRAFT["avatar"]["lora"]
    assert (loaded.avatar.sample_text_guide_scale, loaded.avatar.sample_audio_guide_scale) == (1, 2)
    assert loaded.avatar.negative_prompt is None
    assert loaded.calibration.composition == DRAFT["calibration"]["composition"]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_set("worker_image.digest", None), "congelada: worker_image.digest"),
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


def test_empty_buckets_are_refused_before_loading(tmp_path):
    path = _write(tmp_path, _recipe(_set("avatar.buckets", {})))

    with pytest.raises(RecipeError):
        load_recipe(path, MANIFEST_PATH)
    assert main(["validate", str(path), "--manifest", str(MANIFEST_PATH)]) == 1


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
@pytest.mark.parametrize("stage", ["tts", "render", "finalize"])
def test_frozen_recipe_requires_each_inference_and_export_stage(tmp_path, aspect, stage):
    raw = _recipe(_frozen, _drop(f"pilot.formats.{aspect}.stages.{stage}"))
    path = _write(tmp_path, raw)

    with pytest.raises(RecipeError):
        load_recipe(path, MANIFEST_PATH, require_frozen=True)
    assert main(["validate", str(path), "--manifest", str(MANIFEST_PATH), "--frozen"]) == 1


def test_complete_metadata_does_not_authorize_draft_for_production(tmp_path):
    raw = _recipe(_frozen, _set("status", "draft"))
    path = _write(tmp_path, raw)

    assert load_recipe(path, MANIFEST_PATH).status == "draft"
    with pytest.raises(RecipeError):
        recipe_from_mapping(raw, MANIFEST, require_frozen=True)
    with pytest.raises(RecipeError):
        load_recipe(path, MANIFEST_PATH, require_frozen=True)
    assert main(["validate", str(path), "--manifest", str(MANIFEST_PATH), "--frozen"]) == 1


def test_unreadable_files_are_reported(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    assert main(["validate", str(broken), "--manifest", str(MANIFEST_PATH)]) == 1
    assert "não foi possível ler a receita" in capsys.readouterr().err
    assert main(["validate", str(RECIPE_PATH), "--manifest", str(broken)]) == 1
    assert "não foi possível ler o manifesto" in capsys.readouterr().err


# Receita Qwen sobre o manifesto real, com uma segunda referência derived sintética para a voz
# feminina; a masculina é a Faber do manifesto.
FABER = "qwen-voice-references/faber.wav"
FABER_ENTRY = next(
    entry
    for component in MANIFEST["components"]
    if component["id"] == "qwen-voice-references"
    for entry in component["files"]
    if entry["path"] == "faber.wav"
)
FABER_TEXT = FABER_ENTRY["provenance"]["text"]
SAMPLER = {
    "seed": 20261015,
    "temperature": 0.9,
    "top_p": 1.0,
    "top_k": 50,
    "repetition_penalty": 1.5,
    "repetition_window": 64,
    "max_new_tokens": 512,
}


def _qwen_manifest():
    manifest = copy.deepcopy(MANIFEST)
    references = next(c for c in manifest["components"] if c["id"] == "qwen-voice-references")
    second = copy.deepcopy(references["files"][0])
    second.update(path="feminina-teste.wav", sha256="c" * 64)
    second["provenance"]["text"] = "Transcrição sintética da referência feminina."
    references["files"].append(second)
    return manifest


QWEN_MANIFEST = _qwen_manifest()


def _qwen(recipe):
    recipe["tts"] = {
        "engine": "qwen3-tts-base",
        "language": "pt",
        "sample_rate": 24000,
        "components": ["qwen-tts", "qwen3-tts-12hz-1.7b-base", "ohf-voice-pt-br"],
        "sampler": copy.deepcopy(SAMPLER),
        "voices": {
            "feminina": {
                "kind": "reference",
                "path": "qwen-voice-references/feminina-teste.wav",
                "sha256": "c" * 64,
                "transcript": "Transcrição sintética da referência feminina.",
            },
            "masculina": {
                "kind": "reference",
                "path": FABER,
                "sha256": FABER_ENTRY["sha256"],
                "transcript": FABER_TEXT,
            },
        },
    }


def test_qwen_recipe_is_accepted_and_carries_sampler_and_transcript():
    recipe = recipe_from_mapping(_recipe(_qwen), QWEN_MANIFEST)

    assert recipe.tts.engine == "qwen3-tts-base"
    assert dict(recipe.tts.sampler) == SAMPLER
    assert recipe.tts.voices["masculina"].transcript == FABER_TEXT
    assert recipe_from_mapping(_recipe(), MANIFEST).tts.sampler is None


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_set("tts.engine", "kokoro"), "tts.engine 'kokoro' fora de chatterbox-multilingual"),
        (_drop("tts.sampler.repetition_window"), "tts.sampler.repetition_window precisa ser"),
        (_drop("tts.sampler"), "tts.sampler precisa ser um objeto"),
        (_set("tts.sampler.top_p", 0), "tts.sampler.top_p precisa estar em (0, 1]"),
        (_set("tts.sampler.repetition_penalty", 0.9), "repetition_penalty precisa ser número >= 1"),
        (_set("tts.sampler.min_p", 0.1), "tts.sampler.min_p não é campo do sampler"),
        (
            _set("tts.voices.masculina.transcript", FABER_TEXT + " "),
            f"tts.voices.masculina.transcript diferente de provenance.text de {FABER}",
        ),
        (
            _drop("tts.voices.feminina.transcript"),
            "tts.voices.feminina.transcript precisa ser a transcrição da referência",
        ),
        (
            _set("tts.components", ["qwen-tts", "ohf-voice-pt-br"]),
            "tts.components sem qwen3-tts-12hz-1.7b-base",
        ),
    ],
    ids=[
        "engine-desconhecida",
        "campo-ausente",
        "sem-sampler",
        "top-p-zero",
        "penalty-abaixo-de-1",
        "campo-extra",
        "transcricao-divergente",
        "sem-transcricao",
        "sem-pesos",
    ],
)
def test_incoherent_qwen_recipe_is_refused(mutate, expected):
    problems = check_recipe(_recipe(_qwen, mutate), QWEN_MANIFEST)

    assert any(expected in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_set("tts.sampler", copy.deepcopy(SAMPLER)), "tts.sampler só vale na engine"),
        (
            _set("tts.voices.feminina.transcript", "texto"),
            "tts.voices.feminina.transcript só vale na engine",
        ),
    ],
    ids=["sampler", "transcricao"],
)
def test_chatterbox_recipe_refuses_qwen_only_fields(mutate, expected):
    problems = check_recipe(_recipe(mutate), MANIFEST)

    assert any(expected in problem for problem in problems), problems


def test_qwen_recipe_with_real_marina_and_faber_references_is_valid():
    marina = next(
        entry
        for component in MANIFEST["components"]
        if component["id"] == "fleurs-voice-references"
        for entry in component["files"]
        if entry["path"] == "marina.wav"
    )

    def real_voices(recipe):
        _qwen(recipe)
        recipe["tts"]["components"].append("fleurs-pt-br")
        recipe["tts"]["voices"]["feminina"] = {
            "kind": "reference",
            "path": "fleurs-voice-references/marina.wav",
            "sha256": marina["sha256"],
            "transcript": marina["provenance"]["text"],
        }

    recipe = recipe_from_mapping(_recipe(real_voices), MANIFEST)

    assert recipe.tts.voices["feminina"].transcript == marina["provenance"]["text"]
