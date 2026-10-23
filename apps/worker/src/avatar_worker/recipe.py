"""Receita de render: carga, validação contra o manifesto e exigências de congelamento."""

import argparse
import json
import math
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from avatar_worker.manifest import load_manifest

FORMATS = ("9:16", "16:9")
CANVAS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
FPS = 25
VOICES = ("feminina", "masculina")
STATUSES = ("draft", "frozen")
# Cada voz usa uma referência sintética própria do manifesto, nunca a voz padrão (DEC-004).
VOICE_KINDS = ("reference",)
CHATTERBOX_ENGINE = "chatterbox-multilingual"
QWEN_ENGINE = "qwen3-tts-base"
TTS_ENGINES = (CHATTERBOX_ENGINE, QWEN_ENGINE)
# Componentes sem os quais o runtime do Qwen não carrega: código e pesos.
QWEN_COMPONENTS = ("qwen-tts", "qwen3-tts-12hz-1.7b-base")
# Sampler do talker do Qwen; o sub-talker repete temperatura, top-k e top-p.
SAMPLER_FIELDS = (
    "seed",
    "temperature",
    "top_p",
    "top_k",
    "repetition_penalty",
    "repetition_window",
    "max_new_tokens",
)
AVATAR_SIZES = ("infinitetalk-480", "infinitetalk-720")
# Mesmas faixas de _COMPOSITION_RANGES em avatar_api.assets (geometria de canvas.compose_canvas).
COMPOSITION_RANGES = {"scale": (0.3, 1.2), "x": (0.0, 1.0), "y": (0.5, 1.2)}
X264_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)
APPROVED_VERDICT = "aprovado"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_BITRATE = re.compile(r"[1-9]\d*k")


class RecipeError(Exception):
    """Receita recusada; problems lista cada regra violada em português."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class WorkerImage:
    ref: str
    digest: str | None


@dataclass(frozen=True)
class Cutout:
    model: str
    components: tuple[str, ...]


@dataclass(frozen=True)
class Voice:
    kind: str
    path: str | None
    sha256: str | None
    # Só no Qwen: texto falado na referência, igual a provenance.text do manifesto.
    transcript: str | None = None


@dataclass(frozen=True)
class Tts:
    engine: str
    language: str
    sample_rate: int
    components: tuple[str, ...]
    voices: Mapping[str, Voice]
    # Só no Qwen: os campos de SAMPLER_FIELDS.
    sampler: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Avatar:
    engine: str
    components: tuple[str, ...]
    wheels: tuple[str, ...]
    profile: str
    size: str
    sample_steps: int
    mode: str
    max_frame_num: int
    motion_frame: int
    quant: str | None
    num_persistent_param_in_dit: int | None
    # dict simples: segue em JSON para o estágio de avatar.
    lora: dict[str, Any] | None
    sample_text_guide_scale: float
    sample_audio_guide_scale: float
    prompt: str
    negative_prompt: str | None
    buckets: Mapping[str, tuple[int, int]]


@dataclass(frozen=True)
class Output:
    fps: int
    video_codec: str
    pix_fmt: str
    crf: int
    preset: str
    audio_codec: str
    audio_sample_rate: int
    audio_bitrate: str
    faststart: bool


@dataclass(frozen=True)
class Limits:
    max_audio_seconds: int
    max_script_chars: int
    chars_per_second: float


@dataclass(frozen=True)
class Calibration:
    # Enquadramento {scale, x, y} por formato para amostras do piloto sem composição própria.
    composition: Mapping[str, Mapping[str, float]]


@dataclass(frozen=True)
class Recipe:
    schema_version: int
    name: str
    status: str
    manifest: str
    worker_image: WorkerImage
    cutout: Cutout
    tts: Tts
    avatar: Avatar
    canvas: Mapping[str, tuple[int, int]]
    calibration: Calibration
    output: Output
    limits: Limits
    pilot: Mapping[str, Any] | None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


class _Checker:
    """Acumula os problemas enquanto lê cada campo da receita."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, problem: str) -> None:
        self.problems.append(problem)

    def section(self, parent: dict[str, Any], key: str, label: str) -> dict[str, Any]:
        value = parent.get(key)
        if isinstance(value, dict):
            return value
        self.add(f"{label} precisa ser um objeto")
        return {}

    def text(
        self,
        parent: dict[str, Any],
        key: str,
        label: str,
        choices: tuple[str, ...] | None = None,
    ) -> None:
        value = parent.get(key)
        if not isinstance(value, str) or not value:
            self.add(f"{label} precisa ser um texto não vazio")
        elif choices and value not in choices:
            self.add(f"{label} {value!r} fora de {', '.join(choices)}")

    def equals(self, parent: dict[str, Any], key: str, label: str, expected: Any) -> None:
        value = parent.get(key)
        if value != expected or type(value) is not type(expected):
            self.add(f"{label} precisa ser {expected!r} (recebido {value!r})")

    def integer(self, parent: dict[str, Any], key: str, label: str, minimum: int = 1) -> None:
        value = parent.get(key)
        if not _is_int(value) or value < minimum:
            self.add(f"{label} precisa ser inteiro >= {minimum} (recebido {value!r})")

    def positive(self, parent: dict[str, Any], key: str, label: str, zero: bool = False) -> None:
        value = parent.get(key)
        if not _is_number(value) or value < 0 or (value == 0 and not zero):
            kind = "número >= 0" if zero else "número positivo"
            self.add(f"{label} precisa ser {kind} (recebido {value!r})")

    def finite_positive(self, parent: dict[str, Any], key: str, label: str) -> None:
        value = parent.get(key)
        if not (_is_number(value) and math.isfinite(value) and value > 0):
            self.add(f"{label} precisa ser número finito e positivo (recebido {value!r})")

    def ids(
        self,
        parent: dict[str, Any],
        key: str,
        label: str,
        kinds: dict[str, Any],
        allowed: tuple[str, ...],
    ) -> None:
        value = parent.get(key)
        if not isinstance(value, list) or not value:
            self.add(f"{label} precisa ser uma lista não vazia de ids do manifesto")
            return
        for component_id in value:
            self.component(component_id, label, kinds, allowed)

    def component(
        self, component_id: Any, label: str, kinds: dict[str, Any], allowed: tuple[str, ...]
    ) -> None:
        if not isinstance(component_id, str) or component_id not in kinds:
            self.add(f"{label}: {component_id!r} não existe no manifesto")
        elif kinds[component_id] not in allowed:
            self.add(
                f"{label}: {component_id} tem kind {kinds[component_id]!r} no manifesto, "
                f"esperado {' ou '.join(allowed)}"
            )


def _manifest_components(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    components = manifest.get("components")
    if not isinstance(components, list):
        return {}
    return {
        component["id"]: component
        for component in components
        if isinstance(component, dict) and isinstance(component.get("id"), str)
    }


def _files(component: dict[str, Any]) -> dict[str, Any]:
    """Arquivos de um componente do manifesto: path -> sha256."""
    files = component.get("files")
    return {
        entry["path"]: entry.get("sha256")
        for entry in (files if isinstance(files, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }


def _check_voices(
    check: _Checker,
    voices: dict[str, Any],
    derived: dict[str, Any],
    transcripts: dict[str, Any],
    engine: Any,
) -> None:
    """Cada voz aponta para um arquivo derived do manifesto, e nenhuma repete a outra.

    No Qwen a voz traz a transcrição da referência, igual à do manifesto; no Chatterbox, não.
    """
    for name in VOICES:
        if name not in voices:
            check.add(f"tts.voices sem a voz {name}")
    references = []
    for name, voice in voices.items():
        label = f"tts.voices.{name}"
        if not isinstance(voice, dict):
            check.add(f"{label} precisa ser um objeto")
            continue
        check.text(voice, "kind", f"{label}.kind", VOICE_KINDS)
        if voice.get("kind") != "reference":
            continue
        path, sha256 = voice.get("path"), voice.get("sha256")
        relative = PurePosixPath(path) if isinstance(path, str) else PurePosixPath()
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            check.add(f"{label}.path precisa ser caminho relativo a /models (recebido {path!r})")
        elif not (isinstance(sha256, str) and _SHA256.fullmatch(sha256)):
            check.add(f"{label}.sha256 precisa ter 64 hexadecimais minúsculos")
        else:
            references.append((path, sha256))
            if derived.get(path) != sha256:
                check.add(f"{label}: {path} com sha256 {sha256} não é arquivo derived do manifesto")
        transcript = voice.get("transcript")
        if engine == QWEN_ENGINE:
            if not (isinstance(transcript, str) and transcript.strip()):
                check.add(f"{label}.transcript precisa ser a transcrição da referência")
            elif isinstance(path, str) and transcript != transcripts.get(path):
                check.add(f"{label}.transcript diferente de provenance.text de {path} no manifesto")
        elif "transcript" in voice:
            check.add(f"{label}.transcript só vale na engine {QWEN_ENGINE}")
    paths = {path for path, _ in references}
    hashes = {sha256 for _, sha256 in references}
    if len(paths) < len(references) or len(hashes) < len(references):
        check.add("tts.voices precisam de referências distintas, com caminho e sha256 próprios")


def _check_sampler(check: _Checker, tts: dict[str, Any]) -> None:
    """Sampler do Qwen completo, sem campo extra e com valores que o generate aceita."""
    sampler = check.section(tts, "sampler", "tts.sampler")
    if not sampler:
        return
    for key in sorted(set(sampler) - set(SAMPLER_FIELDS)):
        check.add(f"tts.sampler.{key} não é campo do sampler")
    check.integer(sampler, "seed", "tts.sampler.seed", 0)
    check.finite_positive(sampler, "temperature", "tts.sampler.temperature")
    top_p = sampler.get("top_p")
    if not (_is_number(top_p) and 0 < top_p <= 1):
        check.add(f"tts.sampler.top_p precisa estar em (0, 1] (recebido {top_p!r})")
    check.integer(sampler, "top_k", "tts.sampler.top_k")
    penalty = sampler.get("repetition_penalty")
    if not (_is_number(penalty) and math.isfinite(penalty) and penalty >= 1):
        check.add(f"tts.sampler.repetition_penalty precisa ser número >= 1 (recebido {penalty!r})")
    check.integer(sampler, "repetition_window", "tts.sampler.repetition_window")
    check.integer(sampler, "max_new_tokens", "tts.sampler.max_new_tokens")


def _check_lora(
    check: _Checker, avatar: dict[str, Any], components: dict[str, dict[str, Any]]
) -> None:
    """LoRA declarada: componente model do manifesto, arquivo e sha256 dele, escala finita."""
    if "lora" not in avatar:
        check.add("avatar.lora ausente: declare a LoRA ou null para perfil sem LoRA")
        return
    lora = avatar["lora"]
    if lora is None:
        return
    if not isinstance(lora, dict):
        check.add("avatar.lora precisa ser um objeto ou null")
        return
    component_id = lora.get("component")
    component = components.get(component_id) if isinstance(component_id, str) else None
    if component is None or component.get("kind") != "model":
        check.add(f"avatar.lora.component {component_id!r} não é componente model do manifesto")
    else:
        files = _files(component)
        name, sha256 = lora.get("file"), lora.get("sha256")
        if not isinstance(name, str) or name not in files:
            check.add(f"avatar.lora.file {name!r} não é arquivo de {component_id} no manifesto")
        elif not isinstance(sha256, str) or sha256 != files[name]:
            check.add(f"avatar.lora.sha256 {sha256!r} diferente do manifesto em {component_id}")
    check.finite_positive(lora, "scale", "avatar.lora.scale")


def _check_calibration(check: _Checker, raw: dict[str, Any]) -> None:
    """Enquadramento padrão das amostras de calibração, nas faixas aceitas pelos cenários."""
    calibration = raw.get("calibration")
    composition = calibration.get("composition") if isinstance(calibration, dict) else None
    if not isinstance(composition, dict):
        check.add("calibration.composition precisa ser um objeto por formato")
        return
    if set(composition) != set(FORMATS):
        check.add(
            f"calibration.composition precisa ter exatamente os formatos {', '.join(FORMATS)}"
        )
    for aspect in FORMATS:
        if aspect not in composition:
            continue
        framing = composition[aspect]
        label = f"calibration.composition.{aspect}"
        if not isinstance(framing, dict) or set(framing) != set(COMPOSITION_RANGES):
            check.add(f"{label} precisa ter exatamente {', '.join(COMPOSITION_RANGES)}")
            continue
        for key, (low, high) in COMPOSITION_RANGES.items():
            value = framing[key]
            if not (_is_number(value) and math.isfinite(value) and low <= value <= high):
                check.add(f"{label}.{key} {value!r} fora da faixa de {low:g} a {high:g}")


def _check_buckets(check: _Checker, avatar: dict[str, Any]) -> None:
    buckets = check.section(avatar, "buckets", "avatar.buckets")
    if set(buckets) != set(FORMATS):
        check.add(f"avatar.buckets precisa ter exatamente os formatos {', '.join(FORMATS)}")
    for aspect in FORMATS:
        if aspect not in buckets:
            continue
        size = buckets[aspect]
        if not (isinstance(size, list) and len(size) == 2 and all(_is_int(v) for v in size)):
            check.add(f"avatar.buckets.{aspect} precisa ser [largura, altura] inteiros")
            continue
        width, height = size
        if width <= 0 or height <= 0:
            check.add(f"avatar.buckets.{aspect} {size} precisa ter lados positivos")
        elif aspect == "9:16" and height <= width:
            check.add(f"avatar.buckets.9:16 {size} não é retrato (altura > largura)")
        elif aspect == "16:9" and width <= height:
            check.add(f"avatar.buckets.16:9 {size} não é paisagem (largura > altura)")


def _check_frozen(check: _Checker, raw: dict[str, Any]) -> None:
    digest = _dict(raw.get("worker_image")).get("digest")
    if not (isinstance(digest, str) and _IMAGE_DIGEST.fullmatch(digest)):
        check.add(f"congelada: worker_image.digest precisa ser sha256:<64 hex> ({digest!r})")

    pilot = raw.get("pilot")
    if not isinstance(pilot, dict):
        check.add("congelada: pilot precisa trazer as medições do piloto")
        return
    formats = check.section(pilot, "formats", "congelada: pilot.formats")
    for aspect in FORMATS:
        _check_measurement(check, aspect, formats.get(aspect))

    max_audio_seconds = _dict(raw.get("limits")).get("max_audio_seconds")
    approved = pilot.get("approved_max_audio_seconds")
    if not _is_number(approved) or approved != max_audio_seconds:
        check.add(
            f"congelada: pilot.approved_max_audio_seconds {approved!r} diferente de "
            f"limits.max_audio_seconds {max_audio_seconds!r}"
        )
    if _dict(pilot.get("evaluation")).get("verdict") != APPROVED_VERDICT:
        check.add(f"congelada: pilot.evaluation.verdict precisa ser {APPROVED_VERDICT!r}")


def _check_measurement(check: _Checker, aspect: str, measurement: Any) -> None:
    label = f"congelada: pilot.formats.{aspect}"
    if not isinstance(measurement, dict):
        check.add(f"{label} sem medições")
        return
    check.positive(measurement, "audio_seconds", f"{label}.audio_seconds")
    stages = measurement.get("stages")
    if not isinstance(stages, dict) or not stages:
        check.add(f"{label}.stages precisa listar os estágios medidos")
    else:
        for stage in ("tts", "render", "finalize"):
            if stage not in stages:
                check.add(f"{label}.stages.{stage} sem medições")
        for stage, values in stages.items():
            values = _dict(values)
            check.positive(values, "vram_peak_mb", f"{label}.stages.{stage}.vram_peak_mb", True)
            check.positive(values, "seconds", f"{label}.stages.{stage}.seconds")
    ratio = check.section(
        measurement, "seconds_per_video_second", f"{label}.seconds_per_video_second"
    )
    for load in ("cold", "warm"):
        check.positive(ratio, load, f"{label}.seconds_per_video_second.{load}")


def check_recipe(
    raw: dict[str, Any], manifest: dict[str, Any], require_frozen: bool = False
) -> list[str]:
    """Devolve os problemas da receita; lista vazia significa receita válida."""
    check = _Checker()
    components = _manifest_components(manifest)
    kinds = {component_id: component.get("kind") for component_id, component in components.items()}
    weights_or_code = ("model", "code")

    check.equals(raw, "schema_version", "schema_version", 1)
    check.text(raw, "name", "name")
    check.text(raw, "status", "status", STATUSES)
    check.text(raw, "manifest", "manifest")

    worker_image = check.section(raw, "worker_image", "worker_image")
    check.text(worker_image, "ref", "worker_image.ref")
    digest = worker_image.get("digest")
    if digest is not None and not (isinstance(digest, str) and _IMAGE_DIGEST.fullmatch(digest)):
        check.add(f"worker_image.digest precisa ser sha256:<64 hex> ou null ({digest!r})")

    cutout = check.section(raw, "cutout", "cutout")
    check.text(cutout, "model", "cutout.model")
    if isinstance(cutout.get("model"), str):
        check.component(cutout["model"], "cutout.model", kinds, ("model",))
    check.ids(cutout, "components", "cutout.components", kinds, weights_or_code)

    tts = check.section(raw, "tts", "tts")
    engine = tts.get("engine")
    check.text(tts, "engine", "tts.engine", TTS_ENGINES)
    check.equals(tts, "language", "tts.language", "pt")
    check.equals(tts, "sample_rate", "tts.sample_rate", 24000)
    check.ids(tts, "components", "tts.components", kinds, weights_or_code)
    if engine == QWEN_ENGINE:
        listed = tts.get("components") if isinstance(tts.get("components"), list) else []
        for component_id in QWEN_COMPONENTS:
            if component_id not in listed:
                check.add(f"tts.components sem {component_id}, exigido pela engine {QWEN_ENGINE}")
        _check_sampler(check, tts)
    elif "sampler" in tts:
        check.add(f"tts.sampler só vale na engine {QWEN_ENGINE}")
    voices = check.section(tts, "voices", "tts.voices")
    derived_files = [
        (f"{component_id}/{entry['path']}", entry)
        for component_id, component in components.items()
        if component.get("kind") == "derived"
        for entry in (component.get("files") if isinstance(component.get("files"), list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    ]
    derived = {path: entry.get("sha256") for path, entry in derived_files}
    transcripts = {
        path: _dict(entry.get("provenance")).get("text") for path, entry in derived_files
    }
    _check_voices(check, voices, derived, transcripts, engine)

    avatar = check.section(raw, "avatar", "avatar")
    check.text(avatar, "engine", "avatar.engine")
    check.ids(avatar, "components", "avatar.components", kinds, weights_or_code)
    check.ids(avatar, "wheels", "avatar.wheels", kinds, ("wheel",))
    check.text(avatar, "profile", "avatar.profile")
    check.text(avatar, "size", "avatar.size", AVATAR_SIZES)
    check.integer(avatar, "sample_steps", "avatar.sample_steps")
    check.equals(avatar, "mode", "avatar.mode", "streaming")
    check.integer(avatar, "max_frame_num", "avatar.max_frame_num")
    check.integer(avatar, "motion_frame", "avatar.motion_frame")
    quant = avatar.get("quant")
    if quant is not None:
        check.add(
            f"avatar.quant {quant!r} não roda na imagem do worker: a quantização compila a "
            "extensão CUDA do optimum-quanto na primeira inferência e a imagem não tem nvcc; "
            "use null (bf16)"
        )
    if avatar.get("num_persistent_param_in_dit") is not None:
        check.integer(
            avatar, "num_persistent_param_in_dit", "avatar.num_persistent_param_in_dit", 0
        )
    _check_lora(check, avatar, components)
    check.finite_positive(avatar, "sample_text_guide_scale", "avatar.sample_text_guide_scale")
    check.finite_positive(avatar, "sample_audio_guide_scale", "avatar.sample_audio_guide_scale")
    check.text(avatar, "prompt", "avatar.prompt")
    negative = avatar.get("negative_prompt")
    if negative is not None and (not isinstance(negative, str) or negative.strip()):
        check.add(
            "avatar.negative_prompt precisa ser null: o generate_infinitetalk.py fixado (50aa0a94) "
            "não expõe prompt negativo"
        )
    _check_buckets(check, avatar)

    canvas = raw.get("canvas")
    expected_canvas = {aspect: list(size) for aspect, size in CANVAS.items()}
    if canvas != expected_canvas:
        check.add(f"canvas precisa ser exatamente {expected_canvas} (recebido {canvas!r})")
    _check_calibration(check, raw)

    output = check.section(raw, "output", "output")
    check.equals(output, "fps", "output.fps", FPS)
    check.equals(output, "video_codec", "output.video_codec", "libx264")
    check.equals(output, "pix_fmt", "output.pix_fmt", "yuv420p")
    check.integer(output, "crf", "output.crf", 0)
    if _is_int(output.get("crf")) and output["crf"] > 51:
        check.add(f"output.crf {output['crf']} acima de 51")
    check.text(output, "preset", "output.preset", X264_PRESETS)
    check.equals(output, "audio_codec", "output.audio_codec", "aac")
    check.equals(output, "audio_sample_rate", "output.audio_sample_rate", 48000)
    bitrate = output.get("audio_bitrate")
    if not (isinstance(bitrate, str) and _BITRATE.fullmatch(bitrate)):
        check.add(f"output.audio_bitrate precisa ser como '192k' (recebido {bitrate!r})")
    check.equals(output, "faststart", "output.faststart", True)

    limits = check.section(raw, "limits", "limits")
    check.integer(limits, "max_audio_seconds", "limits.max_audio_seconds")
    check.integer(limits, "max_script_chars", "limits.max_script_chars")
    check.positive(limits, "chars_per_second", "limits.chars_per_second")
    seconds = limits.get("max_audio_seconds")
    chars = limits.get("max_script_chars")
    rate = limits.get("chars_per_second")
    if _is_int(seconds) and _is_int(chars) and _is_number(rate) and chars > seconds * rate:
        check.add(
            f"limits.max_script_chars {chars} acima de max_audio_seconds * chars_per_second "
            f"({seconds} * {rate} = {seconds * rate:g})"
        )
    frames = avatar.get("max_frame_num")
    if _is_int(seconds) and _is_int(frames) and frames != seconds * FPS:
        check.add(
            f"avatar.max_frame_num {frames} incoerente com limits.max_audio_seconds {seconds} "
            f"a {FPS} fps (esperado {seconds * FPS})"
        )

    if "pilot" not in raw:
        check.add("pilot ausente (null no rascunho)")
    if require_frozen and raw.get("status") != "frozen":
        check.add("congelada: status precisa ser frozen")
    if require_frozen or raw.get("status") == "frozen":
        _check_frozen(check, raw)
    return check.problems


def _build(raw: dict[str, Any]) -> Recipe:
    tts, avatar, output, limits = raw["tts"], raw["avatar"], raw["output"], raw["limits"]
    voices = {
        name: Voice(
            kind=voice["kind"],
            path=voice.get("path"),
            sha256=voice.get("sha256"),
            transcript=voice.get("transcript"),
        )
        for name, voice in tts["voices"].items()
    }
    return Recipe(
        schema_version=raw["schema_version"],
        name=raw["name"],
        status=raw["status"],
        manifest=raw["manifest"],
        worker_image=WorkerImage(
            ref=raw["worker_image"]["ref"], digest=raw["worker_image"].get("digest")
        ),
        cutout=Cutout(model=raw["cutout"]["model"], components=tuple(raw["cutout"]["components"])),
        tts=Tts(
            engine=tts["engine"],
            language=tts["language"],
            sample_rate=tts["sample_rate"],
            components=tuple(tts["components"]),
            voices=MappingProxyType(voices),
            sampler=_freeze(tts["sampler"]) if "sampler" in tts else None,
        ),
        avatar=Avatar(
            engine=avatar["engine"],
            components=tuple(avatar["components"]),
            wheels=tuple(avatar["wheels"]),
            profile=avatar["profile"],
            size=avatar["size"],
            sample_steps=avatar["sample_steps"],
            mode=avatar["mode"],
            max_frame_num=avatar["max_frame_num"],
            motion_frame=avatar["motion_frame"],
            quant=avatar.get("quant"),
            num_persistent_param_in_dit=avatar.get("num_persistent_param_in_dit"),
            lora=dict(avatar["lora"]) if avatar["lora"] is not None else None,
            sample_text_guide_scale=float(avatar["sample_text_guide_scale"]),
            sample_audio_guide_scale=float(avatar["sample_audio_guide_scale"]),
            prompt=avatar["prompt"],
            negative_prompt=avatar.get("negative_prompt"),
            buckets=MappingProxyType(
                {aspect: tuple(size) for aspect, size in avatar["buckets"].items()}
            ),
        ),
        canvas=MappingProxyType({aspect: tuple(size) for aspect, size in raw["canvas"].items()}),
        calibration=Calibration(composition=_freeze(raw["calibration"]["composition"])),
        output=Output(**{field: output[field] for field in Output.__dataclass_fields__}),
        limits=Limits(
            max_audio_seconds=limits["max_audio_seconds"],
            max_script_chars=limits["max_script_chars"],
            chars_per_second=float(limits["chars_per_second"]),
        ),
        pilot=_freeze(raw["pilot"]),
    )


def recipe_from_mapping(
    raw: dict[str, Any], manifest: dict[str, Any], require_frozen: bool = False
) -> Recipe:
    """Valida o snapshot do job pelo mesmo schema usado pelo loader de arquivo."""
    if not isinstance(raw, dict):
        raise RecipeError(["a receita precisa ser um objeto JSON"])
    problems = check_recipe(raw, manifest, require_frozen)
    if problems:
        raise RecipeError(problems)
    return _build(raw)


def load_recipe(
    recipe_path: str | Path, manifest_path: str | Path, require_frozen: bool = False
) -> Recipe:
    """Carrega a receita validada contra o manifesto; lança RecipeError com os problemas."""
    try:
        with open(recipe_path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        raise RecipeError([f"não foi possível ler a receita {recipe_path}: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise RecipeError(["a receita precisa ser um objeto JSON"])
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError) as exc:
        raise RecipeError([f"não foi possível ler o manifesto {manifest_path}: {exc}"]) from exc

    return recipe_from_mapping(raw, manifest, require_frozen)


def _summary(recipe: Recipe) -> str:
    buckets = ", ".join(f"{aspect} {w}x{h}" for aspect, (w, h) in recipe.avatar.buckets.items())
    return (
        f"Receita {recipe.name} ({recipe.status}) válida: perfil {recipe.avatar.profile}, "
        f"buckets {buckets}, limite {recipe.limits.max_audio_seconds} s e "
        f"{recipe.limits.max_script_chars} caracteres."
    )


def _validate(args: argparse.Namespace) -> int:
    try:
        recipe = load_recipe(args.recipe, args.manifest, require_frozen=args.frozen)
    except RecipeError as exc:
        print(f"Receita recusada com {len(exc.problems)} problema(s):", file=sys.stderr)
        for problem in exc.problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(_summary(recipe))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avatar_worker.recipe")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="valida a receita contra o manifesto")
    validate.add_argument("recipe", help="arquivo RECIPE-vN.json")
    validate.add_argument("--manifest", required=True, help="arquivo MODEL_MANIFEST.json")
    validate.add_argument(
        "--frozen", action="store_true", help="exige as medições e a avaliação do congelamento"
    )
    validate.set_defaults(handler=_validate)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
