"""Aplica somente a retirada do analisador do commit Chatterbox 3f35dfc8.

Executado no build pelo Python do runtime TTS. A wheel 0.1.7 e os três
arquivos de origem precisam corresponder à base 59bc590 antes de qualquer
alteração. O patch preserva orçamento, seleção de pesos, top_p e áudio final.
"""

import hashlib
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

PATCH_SHA256 = "be202b1dd49c65a18a3198693991d0097f66569904419273ccb3a9b7ea512b2e"
BASE_FILES = {
    "models/t3/t3.py": "6d8be2af8fa203e755d5316d817b73ca8e2a385204b8e4efe92c6446595c71b1",
    "models/t3/inference/t3_hf_backend.py": (
        "a87ae044d9777589ac531360bb3f9096adfe724cf84b92ca6f4306f405de61dd"
    ),
    "models/t3/inference/alignment_stream_analyzer.py": (
        "d8430efa92aedb8e59b782c1d299fe7238570eecea9d293c0981a5ee2e82c8c7"
    ),
}


class PatchError(Exception):
    """A distribuição instalada não corresponde ao artefato de origem fixado."""


def require_sha256(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise PatchError(f"sha256 de {path} diverge: esperado {expected}, obtido {actual}")


def main() -> int:
    try:
        installed = distribution("chatterbox-tts")
        if installed.version != "0.1.7":
            raise PatchError(f"esperado chatterbox-tts 0.1.7, obtido {installed.version}")
        package = Path(installed.locate_file("chatterbox"))
        patch = Path(__file__).with_name("chatterbox-v3-policy.patch")
        require_sha256(patch, PATCH_SHA256)
        for relative, expected in BASE_FILES.items():
            require_sha256(package / relative, expected)
        subprocess.run(
            ["git", "apply", "-p2", str(patch.resolve())],
            cwd=package.parent,
            check=True,
        )
    except (OSError, PackageNotFoundError, PatchError, subprocess.CalledProcessError) as exc:
        print(f"patch_chatterbox: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
