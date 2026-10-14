"""Patch do checkout fixado do InfiniteTalk, aplicado no build da imagem do worker.

Uso: python patch_infinitetalk.py <diretório do InfiniteTalk>

transformers 4.55 recusa config.output_attentions com SDPA, e o Wav2Vec2Model do
InfiniteTalk liga essa flag no forward. O custom_init de generate_infinitetalk.py passa a
carregar só esse encoder com atenção eager; o Wav2Vec2FeatureExtractor, carregado com os
mesmos argumentos, fica intacto. A âncora precisa aparecer exatamente uma vez: ausente ou
repetida, o código não é o do commit fixado e o arquivo não é alterado.

Só usa a biblioteca padrão.
"""

import sys
from pathlib import Path

TARGET = "generate_infinitetalk.py"
ANCHOR = b"Wav2Vec2Model.from_pretrained(wav2vec, local_files_only=True)"
PATCHED = (
    b'Wav2Vec2Model.from_pretrained(wav2vec, local_files_only=True, attn_implementation="eager")'
)


class PatchError(Exception):
    """Âncora ausente ou repetida; o script sai com código 1."""


def patch(source: bytes) -> bytes:
    found = source.count(ANCHOR)
    if found != 1:
        raise PatchError(
            f"esperada 1 ocorrência de {ANCHOR.decode()} em {TARGET}, encontradas {found}"
        )
    return source.replace(ANCHOR, PATCHED)


def main() -> int:
    args = sys.argv[1:]
    if len(args) != 1:
        print("uso: patch_infinitetalk.py <diretório do InfiniteTalk>", file=sys.stderr)
        return 2
    path = Path(args[0]) / TARGET
    try:
        path.write_bytes(patch(path.read_bytes()))
    except (OSError, PatchError) as exc:
        print(f"patch_infinitetalk: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
