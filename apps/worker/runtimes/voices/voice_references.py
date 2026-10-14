"""Ferramenta offline: gera em CPU as referências de voz pt-BR com o Kokoro-82M.

Uso: python voice_references.py --manifest <MODEL_MANIFEST.json> --models <diretório dos pesos>

Roda com o Python do runtime isolado runtimes/voices. O topo só importa a biblioteca padrão:
as fontes kokoro-82m em <models>/kokoro-82m/ são conferidas por tamanho e SHA-256 contra o
manifesto antes de importar torch. A geração força o Hugging Face offline, recusa qualquer
conexão de socket, fixa semente e threads e grava um WAV PCM16 mono 24 kHz por preset em
<models>/kokoro-voice-references/. As vozes são presets sintéticos do Kokoro: nenhuma pessoa
real é gravada ou clonada. O componente derived, com hashes e proveniência, sai no stdout para
registro no manifesto.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import sys
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CODE_ID = "kokoro-code"
SOURCE_ID = "kokoro-82m"
DERIVED_ID = "kokoro-voice-references"
REPO_ID = "hexgrad/Kokoro-82M"
CONFIG_FILE = "config.json"
MODEL_FILE = "kokoro-v1_0.pth"
PRESETS = ("pf_dora", "pm_alex")
SAMPLE_RATE = 24000
SEED = 20261014
THREADS = 1
OFFLINE_ENV = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
# Mesmo texto pt-BR nas duas vozes, sem nomes, números ou siglas.
TEXT = (
    "Olá! Esta é uma voz sintética de referência, criada para apresentar os vídeos com "
    "clareza e naturalidade. Falo português do Brasil, com ritmo tranquilo, boa articulação "
    "e entonação amigável."
)
PARAMETERS = {
    "lang_code": "p",
    "speed": 1.0,
    "sample_rate": SAMPLE_RATE,
    "seed": SEED,
    "threads": THREADS,
    "device": "cpu",
}


class VoiceError(Exception):
    """Fonte divergente ou saída recusada; a ferramenta sai com código 1."""


@dataclass(frozen=True)
class Synthesis:
    pcm16: bytes
    sample_rate: int


# (models_dir, texto, presets, revisão do código no manifesto) -> áudio de cada preset
Synthesizer = Callable[[Path, str, tuple[str, ...], str], dict[str, Synthesis]]


def read_sources(manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Devolve os componentes kokoro-code e kokoro-82m do manifesto."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VoiceError(f"manifesto ilegível: {exc}") from exc
    components = manifest.get("components") if isinstance(manifest, dict) else None
    by_id = {c.get("id"): c for c in components or [] if isinstance(c, dict)}
    missing = [component_id for component_id in (CODE_ID, SOURCE_ID) if component_id not in by_id]
    if missing:
        raise VoiceError(f"manifesto sem {', '.join(missing)}")
    return by_id[CODE_ID], by_id[SOURCE_ID]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sources(models_dir: Path, source: dict[str, Any]) -> dict[str, str]:
    """Confere tamanho e SHA-256 de cada arquivo de kokoro-82m; devolve <id>/<path> -> sha256."""
    hashes: dict[str, str] = {}
    for entry in source.get("files") or []:
        label = f"{SOURCE_ID}/{entry['path']}"
        path = models_dir / SOURCE_ID / entry["path"]
        if not path.is_file():
            raise VoiceError(f"fonte ausente: {path}")
        size = path.stat().st_size
        if size != entry["size"]:
            raise VoiceError(f"{label}: {size} bytes em vez do size {entry['size']} do manifesto")
        actual = sha256_file(path)
        if actual != entry["sha256"].lower():
            raise VoiceError(f"{label}: sha256 {actual} diferente do manifesto {entry['sha256']}")
        hashes[label] = actual
    needed = [CONFIG_FILE, MODEL_FILE, *(f"voices/{preset}.pt" for preset in PRESETS)]
    missing = [name for name in needed if f"{SOURCE_ID}/{name}" not in hashes]
    if missing:
        raise VoiceError(f"{SOURCE_ID} sem {', '.join(missing)} no manifesto")
    return hashes


@contextmanager
def offline() -> Iterator[None]:
    """Hugging Face offline e qualquer conexão de socket recusada durante a geração."""

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise OSError("rede bloqueada durante a geração das referências de voz")

    targets = [
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
        (socket, "create_connection"),
        (socket, "getaddrinfo"),
    ]
    saved = [(owner, name, getattr(owner, name)) for owner, name in targets]
    saved_env = {name: os.environ.get(name) for name in OFFLINE_ENV}
    os.environ.update(dict.fromkeys(OFFLINE_ENV, "1"))
    for owner, name in targets:
        setattr(owner, name, refuse)
    try:
        yield
    finally:
        for owner, name, original in saved:
            setattr(owner, name, original)
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def kokoro_synthesize(
    models_dir: Path, text: str, presets: tuple[str, ...], code_revision: str
) -> dict[str, Synthesis]:
    """Gera cada preset com KModel e KPipeline carregados só de arquivos locais, em CPU."""
    try:
        installed = importlib.metadata.distribution("kokoro").read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError as exc:
        raise VoiceError("kokoro não está instalado neste runtime") from exc
    commit = json.loads(installed or "{}").get("vcs_info", {}).get("commit_id")
    if commit != code_revision:
        raise VoiceError(f"kokoro instalado no commit {commit!r}; o manifesto fixa {code_revision}")

    import torch
    from kokoro import KModel, KPipeline

    torch.set_num_threads(THREADS)
    source = models_dir / SOURCE_ID
    model = KModel(
        repo_id=REPO_ID, config=str(source / CONFIG_FILE), model=str(source / MODEL_FILE)
    )
    pipeline = KPipeline(lang_code=PARAMETERS["lang_code"], repo_id=REPO_ID, model=model.eval())
    outputs = {}
    for preset in presets:
        # Semente renovada por preset: cada WAV não depende da ordem de geração.
        torch.manual_seed(SEED)
        voice = str(source / "voices" / f"{preset}.pt")
        chunks = [result.audio for result in pipeline(text, voice=voice, speed=PARAMETERS["speed"])]
        audio = torch.cat(chunks).clamp(-1.0, 1.0)
        pcm16 = (audio * 32767).to(torch.int16).numpy().tobytes()
        outputs[preset] = Synthesis(pcm16=pcm16, sample_rate=SAMPLE_RATE)
    return outputs


def write_wav(path: Path, synthesis: Synthesis) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.part")
    with wave.open(str(part), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(synthesis.pcm16)
    os.replace(part, path)


def run(
    manifest_path: Path, models_dir: Path, synthesize: Synthesizer = kokoro_synthesize
) -> dict[str, Any]:
    """Gera os WAVs e devolve o componente derived que os registra no manifesto."""
    code, source = read_sources(manifest_path)
    source_hashes = verify_sources(models_dir, source)
    with offline():
        outputs = synthesize(models_dir, TEXT, PRESETS, code["revision"])
    for preset in PRESETS:
        synthesis = outputs[preset]
        if synthesis.sample_rate != SAMPLE_RATE or not synthesis.pcm16:
            raise VoiceError(f"{preset}: áudio vazio ou fora de {SAMPLE_RATE} Hz")
    if len({outputs[preset].pcm16 for preset in PRESETS}) != len(PRESETS):
        raise VoiceError(f"as vozes {', '.join(PRESETS)} geraram áudios iguais")

    parameters = {**PARAMETERS, "platform": f"{sys.platform}-{platform.machine()}"}
    revisions = {CODE_ID: code["revision"], SOURCE_ID: source["revision"]}
    files = []
    for preset in PRESETS:
        path = models_dir / DERIVED_ID / f"{preset}.wav"
        write_wav(path, outputs[preset])
        used = [f"{SOURCE_ID}/{name}" for name in (CONFIG_FILE, MODEL_FILE, f"voices/{preset}.pt")]
        files.append(
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
                "provenance": {
                    "model": f"{SOURCE_ID}/{MODEL_FILE}",
                    "preset": f"{SOURCE_ID}/voices/{preset}.pt",
                    "text": TEXT,
                    "parameters": parameters,
                    "revisions": revisions,
                    "sources": {label: source_hashes[label] for label in used},
                },
            }
        )
    return {
        "id": DERIVED_ID,
        "kind": "derived",
        "code_license": code["code_license"],
        "weights_license": source["weights_license"],
        "commercial_use": code["commercial_use"] is True and source["commercial_use"] is True,
        "license_evidence": list(
            dict.fromkeys([*code["license_evidence"], *source["license_evidence"]])
        ),
        "derived_from": [CODE_ID, SOURCE_ID],
        "files": files,
    }


def main(argv: list[str] | None = None, synthesize: Synthesizer = kokoro_synthesize) -> int:
    parser = argparse.ArgumentParser(
        prog="voice_references.py",
        description="Gera offline as referências de voz pt-BR do Kokoro e imprime o derived.",
    )
    parser.add_argument("--manifest", type=Path, required=True, help="MODEL_MANIFEST.json")
    parser.add_argument(
        "--models", type=Path, required=True, help="diretório dos pesos, com kokoro-82m/"
    )
    args = parser.parse_args(argv)
    try:
        component = run(args.manifest, args.models, synthesize)
    except VoiceError as exc:
        print(f"voice_references: {exc}", file=sys.stderr)
        return 1
    print(f"referências gravadas em {args.models / DERIVED_ID}", file=sys.stderr)
    print(json.dumps(component, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
