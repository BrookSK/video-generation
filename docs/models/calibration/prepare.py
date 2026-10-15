"""Prepara entradas de calibração; não carrega modelos nem executa inferência."""

import argparse
import copy
import hashlib
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
MATERIALS = (
    "avatar-feminino.png",
    "avatar-masculino.png",
    "cenario-escritorio.png",
    "cenario-estudio.png",
    "cenario-sala.png",
    "cenario-loja.png",
)
SPEECHES = (
    "demo-feminina.txt",
    "demo-masculina.txt",
    "c1-aprox30s.txt",
    "stress-original-numerico.txt",
    "stress-original-extenso.txt",
)
FORMATS = ("9:16", "16:9")
VOICES = {"feminina": "feminino", "masculina": "masculino"}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sample(voice: str, aspect: str, speech: str, scene: str = "escritorio") -> dict:
    tag = aspect.replace(":", "x")
    corpus = "demo" if speech.startswith("demo-") else Path(speech).stem
    return {
        "id": f"{corpus}-{voice}-{scene}-{tag}",
        "image": f"materiais/avatar-{VOICES[voice]}.png",
        "background": f"materiais/cenario-{scene}.png",
        "text_file": speech,
        "voice": voice,
        "format": aspect,
    }


def prepare(materials: Path, out: Path, worker_image: str | None = None) -> None:
    if out.exists():
        raise ValueError(f"saída já existe; escolha um diretório novo: {out}")
    missing = [name for name in MATERIALS if not (materials / name).is_file()]
    if missing:
        raise ValueError(f"materiais ausentes em {materials}: {', '.join(missing)}")

    recipe = json.loads((HERE.parent / "RECIPE-v1.json").read_text(encoding="utf-8"))
    if recipe.get("status") != "draft" or recipe.get("pilot") is not None:
        raise ValueError("a receita base precisa estar draft, com pilot null")
    if worker_image is not None:
        match = re.fullmatch(r"([a-z0-9][a-z0-9._:/-]*)@sha256:([0-9a-f]{64})", worker_image)
        if match is None:
            raise ValueError("--worker-image precisa ser ref@sha256 com 64 hexadecimais minúsculos")
        recipe["worker_image"] = {"ref": match[1], "digest": f"sha256:{match[2]}"}
    variants = json.loads((HERE / "variants.json").read_text(encoding="utf-8"))
    texts = {name: (HERE / name).read_bytes().decode("utf-8") for name in SPEECHES}
    for name, text in texts.items():
        if not text.strip() or len(text) > recipe["limits"]["max_script_chars"]:
            raise ValueError(f"fala vazia ou acima do limite da receita: {name}")

    out.mkdir(parents=True)
    (out / "materiais").mkdir()
    for name in MATERIALS:
        shutil.copyfile(materials / name, out / "materiais" / name)
    for name in SPEECHES:
        shutil.copyfile(HERE / name, out / name)
    shutil.copyfile(HERE.parent / "MODEL_MANIFEST.json", out / "MODEL_MANIFEST.json")
    if worker_image is None:
        shutil.copyfile(HERE.parent / "RECIPE-v1.json", out / "RECIPE-baseline.json")
    else:
        write_json(out / "RECIPE-baseline.json", recipe)

    prompt_recipe = copy.deepcopy(recipe)
    prompt_recipe["avatar"]["prompt"] = variants["prompt_positive"]
    write_json(out / "RECIPE-prompt.json", prompt_recipe)
    composition_recipe = copy.deepcopy(recipe)
    composition_recipe["calibration"]["composition"].update(variants["composition_candidate"])
    write_json(out / "RECIPE-composition.json", composition_recipe)

    demo_samples, c1_samples = [], []
    for voice in VOICES:
        for aspect in FORMATS:
            tag = aspect.replace(":", "x")
            demo = sample(voice, aspect, f"demo-{voice}.txt")
            c1 = sample(voice, aspect, "c1-aprox30s.txt")
            write_json(out / f"queue-demo-{voice}-{tag}.json", {"samples": [demo]})
            write_json(out / f"queue-c1-{voice}-{tag}.json", {"samples": [c1]})
            demo_samples.append(demo)
            c1_samples.append(c1)
        for corpus, speech in (
            ("demo", f"demo-{voice}.txt"),
            ("c1", "c1-aprox30s.txt"),
            ("stress-numerico", "stress-original-numerico.txt"),
            ("stress-extenso", "stress-original-extenso.txt"),
        ):
            name = f"{corpus}-{voice}"
            if corpus.startswith("stress-"):
                write_json(
                    out / f"queue-{name}-9x16.json",
                    {"samples": [sample(voice, "9:16", speech)]},
                )
            write_json(
                out / f"tts-{name}.json",
                {
                    "text": texts[speech],
                    "language": recipe["tts"]["language"],
                    "models_dir": "/models",
                    "out_wav": f"/pilot/out/{name}.wav",
                    "voice": recipe["tts"]["voices"][voice],
                },
            )
    write_json(out / "queue-demo-four-samples.json", {"samples": demo_samples})
    write_json(out / "queue-c1-four-samples.json", {"samples": c1_samples})
    write_json(
        out / "queue-demo-feminina-9x16-sala.json",
        {"samples": [sample("feminina", "9:16", "demo-feminina.txt", "sala")]},
    )

    hashes = []
    for path in sorted(out.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes.append(f"{digest}  {path.relative_to(out).as_posix()}")
    (out / "SHA256SUMS").write_text("\n".join(hashes) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="diretório novo; nunca sobrescrito")
    parser.add_argument(
        "--worker-image", help="candidato opcional ref@sha256 aplicado às três receitas"
    )
    args = parser.parse_args()
    try:
        prepare(args.materials.resolve(), args.out.resolve(), args.worker_image)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"preparo recusado: {exc}\n")
    print(f"Entradas preparadas em {args.out.resolve()}; nenhuma inferência executada.")


if __name__ == "__main__":
    main()
