"""Estágio tts_engine: request.json vira WAV mono 24 kHz e result.json.

Uso: python tts_stage.py <request.json> <result.json>

Roda com o Python do runtime isolado. O topo só importa a biblioteca padrão; torch,
chatterbox e perth entram dentro das funções.
"""

import hashlib
import json
import os
import sys
import tempfile
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SAMPLE_RATE = 24000
VOICE_KINDS = ("default", "reference")
OFFLINE_ENV = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")

# O from_local da 0.1.7 lê nomes fixos num único diretório. O checkpoint pt-BR usa outros
# nomes e o resto vem do repositório base, por isso cada nome esperado aponta para
# /models/<componente>/<arquivo> do manifesto.
CHECKPOINT_FILES = {
    "ve.pt": ("chatterbox-base", "ve.pt"),
    "conds.pt": ("chatterbox-base", "conds.pt"),
    "t3_mtl23ls_v2.safetensors": ("chatterbox-multilingual-pt-br", "t3_pt_br.safetensors"),
    "s3gen.pt": ("chatterbox-multilingual-pt-br", "s3gen_v3.pt"),
    "grapheme_mtl_merged_expanded_v1.json": (
        "chatterbox-multilingual-pt-br",
        "grapheme_mtl_merged_expanded_v1.json",
    ),
}


class StageError(Exception):
    """Pedido inválido ou insumo recusado; o estágio sai com código 1."""


@dataclass(frozen=True)
class Synthesis:
    pcm16: bytes
    sample_rate: int
    peak_vram_mb: float


Synthesizer = Callable[[str, str, Path | None, Path], Synthesis]
WatermarkDetector = Callable[[Path], bool]


def read_request(path: Path) -> dict[str, Any]:
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StageError(f"request.json ilegível: {exc}") from exc
    if not isinstance(request, dict):
        raise StageError("request.json precisa ser um objeto")
    for key in ("text", "language", "models_dir", "out_wav"):
        value = request.get(key)
        if not isinstance(value, str) or not value.strip():
            raise StageError(f"request.{key} precisa ser texto não vazio")
    voice = request.get("voice")
    if not isinstance(voice, dict) or voice.get("kind") not in VOICE_KINDS:
        raise StageError(f"request.voice.kind precisa ser um de {', '.join(VOICE_KINDS)}")
    return request


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_voice(voice: dict[str, Any], models_dir: Path) -> Path | None:
    """Devolve a referência de voz conferida pelo sha256, ou None para a voz padrão."""
    if voice["kind"] == "default":
        return None
    path, expected = voice.get("path"), voice.get("sha256")
    parts = PurePosixPath(path).parts if isinstance(path, str) else ()
    if not path or PurePosixPath(path).is_absolute() or ".." in parts:
        raise StageError(f"voice.path precisa ser caminho relativo a models_dir: {path!r}")
    if not isinstance(expected, str) or len(expected) != 64:
        raise StageError("voice.sha256 precisa ter 64 hexadecimais")
    reference = models_dir / path
    if not reference.is_file():
        raise StageError(f"referência de voz ausente: {reference}")
    actual = sha256_file(reference)
    if actual != expected.lower():
        raise StageError(
            f"sha256 da referência {path} diverge: esperado {expected}, obtido {actual}"
        )
    return reference


def write_wav(path: Path, synthesis: Synthesis) -> float:
    if synthesis.sample_rate != SAMPLE_RATE:
        raise StageError(
            f"sintetizador devolveu {synthesis.sample_rate} Hz, esperado {SAMPLE_RATE}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(synthesis.pcm16)
    return len(synthesis.pcm16) / 2 / SAMPLE_RATE


def chatterbox_synthesize(
    text: str, language: str, voice: Path | None, models_dir: Path
) -> Synthesis:
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    with tempfile.TemporaryDirectory(prefix="chatterbox-ckpt-") as ckpt_dir:
        for name, (component, filename) in CHECKPOINT_FILES.items():
            source = models_dir / component / filename
            if not source.is_file():
                raise StageError(f"checkpoint ausente: {source}")
            (Path(ckpt_dir) / name).symlink_to(source.resolve())
        model = ChatterboxMultilingualTTS.from_local(ckpt_dir, device)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    prompt = str(voice) if voice else None
    wav = model.generate(text, language_id=language, audio_prompt_path=prompt)
    peak = torch.cuda.max_memory_allocated() / 2**20 if device == "cuda" else 0.0
    pcm16 = (wav.squeeze(0).clamp(-1.0, 1.0) * 32767).to(torch.int16).cpu().numpy().tobytes()
    return Synthesis(pcm16=pcm16, sample_rate=model.sr, peak_vram_mb=round(peak, 1))


def perth_detect(wav_path: Path) -> bool:
    import librosa
    import perth

    audio, sample_rate = librosa.load(str(wav_path), sr=None)
    return perth.PerthImplicitWatermarker().get_watermark(audio, sample_rate=sample_rate) >= 0.5


def run(
    request_path: Path,
    result_path: Path,
    synthesize: Synthesizer = chatterbox_synthesize,
    detect_watermark: WatermarkDetector = perth_detect,
) -> dict[str, Any]:
    started = time.monotonic()
    for name in OFFLINE_ENV:
        os.environ[name] = "1"
    request = read_request(request_path)
    models_dir = Path(request["models_dir"])
    voice = resolve_voice(request["voice"], models_dir)
    synthesis = synthesize(request["text"], request["language"], voice, models_dir)
    out_wav = Path(request["out_wav"])
    duration = write_wav(out_wav, synthesis)
    result = {
        "audio_path": str(out_wav),
        "duration_s": round(duration, 3),
        "sample_rate": synthesis.sample_rate,
        "peak_vram_mb": synthesis.peak_vram_mb,
        "watermark_detected": bool(detect_watermark(out_wav)),
        "elapsed_s": round(time.monotonic() - started, 3),
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(
    argv: list[str] | None = None,
    synthesize: Synthesizer = chatterbox_synthesize,
    detect_watermark: WatermarkDetector = perth_detect,
) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("uso: tts_stage.py <request.json> <result.json>", file=sys.stderr)
        return 2
    try:
        run(Path(args[0]), Path(args[1]), synthesize, detect_watermark)
    except StageError as exc:
        print(f"tts_stage: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
