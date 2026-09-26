"""Manifesto de modelos e verificador da política de licenças, revisões e hashes."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ALLOWED_LICENSES = frozenset(
    name.casefold() for name in ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause")
)
FORBIDDEN_TERMS = ("bria-rmbg", "insightface")
KINDS = ("model", "code", "wheel")

_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_EXACT_VERSION = re.compile(r"\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+[0-9A-Za-z.]+)?")


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Lê o manifesto JSON; erros de leitura e de sintaxe sobem como OSError e ValueError."""
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError("o manifesto precisa ser um objeto JSON")
    return manifest


def _is_allowed_license(value: Any) -> bool:
    return isinstance(value, str) and value.casefold() in ALLOWED_LICENSES


def _forbidden_term(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.casefold()
    return next((term for term in FORBIDDEN_TERMS if term in lowered), None)


def _check_https(label: str, url: Any) -> list[str]:
    if isinstance(url, str) and url.startswith("https://"):
        return []
    return [f"{label}: url sem https ({url!r})"]


def _check_file(label: str, index: int, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{label}: arquivo #{index} não é um objeto"]
    file_label = f"{label}: arquivo {entry.get('path') or f'#{index}'}"
    violations = _check_https(file_label, entry.get("url"))
    sha256 = entry.get("sha256")
    if not (isinstance(sha256, str) and _SHA256.fullmatch(sha256)):
        violations.append(f"{file_label} sem sha256 de 64 hexadecimais")
    size = entry.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        violations.append(f"{file_label} sem size")
    return violations


def _check_component(index: int, component: Any) -> list[str]:
    if not isinstance(component, dict):
        return [f"componente #{index}: não é um objeto"]
    label = component.get("id") or f"componente #{index}"
    kind = component.get("kind")
    revision = component.get("revision")
    files = component.get("files")
    violations: list[str] = []

    if not isinstance(component.get("id"), str) or not component["id"]:
        violations.append(f"{label}: sem id")
    if kind not in KINDS:
        violations.append(f"{label}: kind {kind!r} fora de {', '.join(KINDS)}")
    violations += _check_https(label, component.get("url"))
    if component.get("commercial_use") is not True:
        violations.append(f"{label}: commercial_use diferente de true")
    if not _is_allowed_license(component.get("code_license")):
        violations.append(
            f"{label}: code_license {component.get('code_license')!r} não é permitida"
        )
    if kind == "model" and not _is_allowed_license(component.get("weights_license")):
        violations.append(
            f"{label}: weights_license {component.get('weights_license')!r} não é permitida"
        )
    if kind in ("model", "code") and not (
        isinstance(revision, str) and _COMMIT.fullmatch(revision)
    ):
        violations.append(f"{label}: revision {revision!r} não é commit de 40 hexadecimais")
    if kind == "wheel" and not (isinstance(revision, str) and _EXACT_VERSION.fullmatch(revision)):
        violations.append(f"{label}: wheel sem versão exata (revision {revision!r})")

    if files is None:
        files = []
    if not isinstance(files, list):
        violations.append(f"{label}: files precisa ser uma lista")
        files = []
    if kind in ("model", "wheel") and not files:
        violations.append(f"{label}: componente {kind} sem arquivo")
    for file_index, entry in enumerate(files):
        violations += _check_file(label, file_index, entry)

    named_values = [component.get("id"), component.get("url")]
    named_values += [entry.get("path") for entry in files if isinstance(entry, dict)]
    for value in named_values:
        term = _forbidden_term(value)
        if term:
            violations.append(f"{label}: {term} é proibido ({value})")
    return violations


def check_policy(manifest: dict[str, Any]) -> list[str]:
    """Devolve as violações da política; lista vazia significa manifesto aceito."""
    violations: list[str] = []
    if manifest.get("schema_version") != 1:
        violations.append(f"schema_version {manifest.get('schema_version')!r} diferente de 1")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        return [*violations, "components precisa ser uma lista não vazia"]

    seen: set[str] = set()
    for index, component in enumerate(components):
        component_id = component.get("id") if isinstance(component, dict) else None
        if isinstance(component_id, str):
            if component_id in seen:
                violations.append(f"{component_id}: id duplicado")
            seen.add(component_id)
        violations += _check_component(index, component)
    return violations


def _summary(component: dict[str, Any]) -> str:
    files = component.get("files") or []
    return (
        f"{component['id']} ({component['kind']}): código {component['code_license']}, "
        f"pesos {component.get('weights_license') or '-'}, "
        f"revisão {component['revision']}, {len(files)} arquivo(s)"
    )


def _verify(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.policy)
    except (OSError, ValueError) as exc:
        print(f"Erro: não foi possível ler {args.policy}: {exc}", file=sys.stderr)
        return 1
    violations = check_policy(manifest)
    if violations:
        print(f"Manifesto recusado com {len(violations)} violação(ões):", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    for component in manifest["components"]:
        print(_summary(component))
    print(f"Manifesto aceito: {len(manifest['components'])} componente(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avatar_worker.manifest")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="confere o manifesto contra a política")
    verify.add_argument("--policy", required=True, help="arquivo MODEL_MANIFEST.json")
    verify.set_defaults(handler=_verify)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
