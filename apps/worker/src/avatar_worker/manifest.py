"""Manifesto de modelos, verificador da política e download verificado dos pesos."""

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import urllib.request
from collections.abc import Collection
from pathlib import Path, PurePosixPath
from typing import Any

# CC0-1.0: gravações humanas em domínio público usadas como referência de voz.
# CC-BY-4.0 permite uso comercial com atribuição: o componente precisa registrar o texto dela.
ATTRIBUTION_LICENSES = frozenset({"cc-by-4.0"})
ALLOWED_LICENSES = (
    frozenset(
        name.casefold() for name in ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0")
    )
    | ATTRIBUTION_LICENSES
)
FORBIDDEN_TERMS = ("bria-rmbg", "insightface")
# derived: arquivos gerados localmente a partir de outros componentes; o pull não os baixa.
KINDS = ("model", "code", "wheel", "derived")

_COMPONENT_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")
_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_EXACT_VERSION = re.compile(r"\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+[0-9A-Za-z.]+)?")

CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60


class PullError(Exception):
    """Falha no download verificado; a mensagem nomeia o arquivo."""


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


def _check_license_evidence(label: str, evidence: Any) -> list[str]:
    if not isinstance(evidence, list) or not evidence:
        return [f"{label}: license_evidence precisa ser uma lista não vazia de URLs https"]
    violations: list[str] = []
    for index, url in enumerate(evidence):
        violations += _check_https(f"{label}: license_evidence #{index}", url)
    return violations


def _derived_origin(
    label: str, derived_from: Any, components: dict[str, Any]
) -> tuple[list[str], set[str]]:
    """Confere a origem de um derived e devolve os arquivos que a proveniência pode citar.

    Cada origem é um componente não derivado do manifesto; um arquivo de origem é citado
    como <id>/<path>, o mesmo caminho relativo a /models usado pelo pull.
    """
    if not isinstance(derived_from, list) or not derived_from:
        violation = f"{label}: derived_from precisa listar componentes não derivados do manifesto"
        return [violation], set()
    violations: list[str] = []
    files: set[str] = set()
    for source in derived_from:
        origin = components.get(source) if isinstance(source, str) else None
        if origin is None or origin.get("kind") == "derived":
            violations.append(
                f"{label}: derived_from {source!r} não é componente não derivado do manifesto"
            )
            continue
        entries = origin.get("files")
        if isinstance(entries, list):
            files.update(
                f"{source}/{entry['path']}"
                for entry in entries
                if isinstance(entry, dict) and isinstance(entry.get("path"), str)
            )
    return violations, files


def _check_local_file(
    label: str, file_label: str, entry: dict[str, Any], sources: set[str]
) -> list[str]:
    """Arquivo derived: gerado localmente, sem url de download e com proveniência própria."""
    violations: list[str] = []
    path = entry.get("path")
    relative = PurePosixPath(path) if isinstance(path, str) else PurePosixPath()
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        violations.append(f"{file_label}: caminho fora de {label}/")
    if entry.get("url") is not None:
        violations.append(f"{file_label}: derivado local não tem url de download")
    provenance = entry.get("provenance")
    if not isinstance(provenance, dict):
        return [*violations, f"{file_label} sem provenance"]
    # Origem citada por arquivo: source para um derivado de gravação (referência de voz
    # convertida), model e preset para um derivado gerado por modelo (Kokoro).
    keys = ("source",) if "source" in provenance else ("model", "preset")
    for key in keys:
        reference = provenance.get(key)
        if not (isinstance(reference, str) and reference in sources):
            violations.append(
                f"{file_label}: provenance.{key} {reference!r} não é arquivo de derived_from"
            )
    text = provenance.get("text")
    if not (isinstance(text, str) and text.strip()):
        violations.append(f"{file_label} sem provenance.text")
    parameters = provenance.get("parameters")
    if not (isinstance(parameters, dict) and parameters):
        violations.append(f"{file_label} sem provenance.parameters")
    return violations


def _check_file(label: str, index: int, entry: Any, sources: set[str] | None) -> list[str]:
    """Confere um arquivo; com sources, é arquivo derived que cita essas origens."""
    if not isinstance(entry, dict):
        return [f"{label}: arquivo #{index} não é um objeto"]
    file_label = f"{label}: arquivo {entry.get('path') or f'#{index}'}"
    if sources is None:
        violations = _check_https(file_label, entry.get("url"))
    else:
        violations = _check_local_file(label, file_label, entry, sources)
    sha256 = entry.get("sha256")
    if not (isinstance(sha256, str) and _SHA256.fullmatch(sha256)):
        violations.append(f"{file_label} sem sha256 de 64 hexadecimais")
    size = entry.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        violations.append(f"{file_label} sem size")
    return violations


def _check_component(index: int, component: Any, components: dict[str, Any]) -> list[str]:
    if not isinstance(component, dict):
        return [f"componente #{index}: não é um objeto"]
    label = component.get("id") or f"componente #{index}"
    kind = component.get("kind")
    revision = component.get("revision")
    files = component.get("files")
    violations: list[str] = []

    if not isinstance(component.get("id"), str) or not component["id"]:
        violations.append(f"{label}: sem id")
    elif not _COMPONENT_ID.fullmatch(component["id"]):
        violations.append(f"{label}: id fora do formato {_COMPONENT_ID.pattern}")
    if kind not in KINDS:
        violations.append(f"{label}: kind {kind!r} fora de {', '.join(KINDS)}")
    sources = None
    if kind == "derived":
        origin_violations, sources = _derived_origin(
            label, component.get("derived_from"), components
        )
        violations += origin_violations
    else:
        violations += _check_https(label, component.get("url"))
    if component.get("commercial_use") is not True:
        violations.append(f"{label}: commercial_use diferente de true")
    if not _is_allowed_license(component.get("code_license")):
        violations.append(
            f"{label}: code_license {component.get('code_license')!r} não é permitida"
        )
    if kind in ("model", "derived") and not _is_allowed_license(component.get("weights_license")):
        violations.append(
            f"{label}: weights_license {component.get('weights_license')!r} não é permitida"
        )
    violations += _check_license_evidence(label, component.get("license_evidence"))
    licenses = (component.get("code_license"), component.get("weights_license"))
    attribution = component.get("attribution")
    if any(
        isinstance(name, str) and name.casefold() in ATTRIBUTION_LICENSES for name in licenses
    ) and not (isinstance(attribution, str) and attribution.strip()):
        violations.append(f"{label}: licença com atribuição exige o campo attribution")
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
    if kind in ("model", "wheel", "derived") and not files:
        violations.append(f"{label}: componente {kind} sem arquivo")
    for file_index, entry in enumerate(files):
        violations += _check_file(label, file_index, entry, sources)

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

    by_id = {
        component["id"]: component
        for component in components
        if isinstance(component, dict) and isinstance(component.get("id"), str)
    }
    seen: set[str] = set()
    for index, component in enumerate(components):
        component_id = component.get("id") if isinstance(component, dict) else None
        if isinstance(component_id, str):
            if component_id in seen:
                violations.append(f"{component_id}: id duplicado")
            seen.add(component_id)
        violations += _check_component(index, component, by_id)
    return violations


def _summary(component: dict[str, Any]) -> str:
    files = component.get("files") or []
    if component["kind"] == "derived":
        origin = f"origem {', '.join(component['derived_from'])}"
    else:
        origin = f"revisão {component['revision']}"
    return (
        f"{component['id']} ({component['kind']}): código {component['code_license']}, "
        f"pesos {component.get('weights_license') or '-'}, {origin}, {len(files)} arquivo(s)"
    )


def _load_checked(path: str | Path) -> dict[str, Any] | None:
    """Lê o manifesto e aplica a política; imprime o motivo e devolve None se recusado."""
    try:
        manifest = load_manifest(path)
    except (OSError, ValueError) as exc:
        print(f"Erro: não foi possível ler {path}: {exc}", file=sys.stderr)
        return None
    violations = check_policy(manifest)
    if violations:
        print(f"Manifesto recusado com {len(violations)} violação(ões):", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return None
    return manifest


def _verify(args: argparse.Namespace) -> int:
    manifest = _load_checked(args.policy)
    if manifest is None:
        return 1
    for component in manifest["components"]:
        print(_summary(component))
    print(f"Manifesto aceito: {len(manifest['components'])} componente(s).")
    return 0


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _target(dest: Path, label: str, component_id: str, relative: str) -> Path:
    if not _COMPONENT_ID.fullmatch(component_id):
        raise PullError(f"{label}: id fora do formato {_COMPONENT_ID.pattern}")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        raise PullError(f"{label}: caminho fora de {component_id}/")
    target = dest / component_id / path
    if not target.resolve().is_relative_to(dest.resolve()):
        raise PullError(f"{label}: caminho fora de {dest}")
    return target


def _download(url: str, part: Path, size: int) -> str:
    """Grava url em part conferindo o tamanho e devolve o SHA-256 calculado em streaming."""
    digest = hashlib.sha256()
    written = 0
    with (
        urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response,
        open(part, "wb") as out,
    ):
        while chunk := response.read(CHUNK_SIZE):
            written += len(chunk)
            if written > size:
                raise PullError(f"passou do size {size}")
            digest.update(chunk)
            out.write(chunk)
    if written != size:
        raise PullError(f"{written} bytes em vez do size {size}")
    return digest.hexdigest()


def pull(
    manifest: dict[str, Any], dest: Path, components: Collection[str] | None = None
) -> tuple[int, int]:
    """Baixa os arquivos dos componentes model em dest/<id>/<path>; devolve (baixados, pulados).

    Com components, baixa só os ids nomeados e recusa id ausente do manifesto antes de baixar.
    Cada arquivo passa por <arquivo>.part e só é renomeado com SHA-256 e size do manifesto.
    Arquivo já presente com hash correto não é baixado de novo.
    """
    if components is not None:
        unknown = sorted(set(components) - {c["id"] for c in manifest["components"]})
        if unknown:
            raise PullError(f"componente fora do manifesto: {', '.join(unknown)}")
    downloaded = skipped = 0
    for component in manifest["components"]:
        if component["kind"] != "model":
            continue
        if components is not None and component["id"] not in components:
            continue
        for entry in component["files"]:
            label = f"{component['id']}/{entry['path']}"
            target = _target(dest, label, component["id"], entry["path"])
            size = entry["size"]
            expected = entry["sha256"].lower()
            if (
                target.is_file()
                and target.stat().st_size == size
                and _sha256_of(target) == expected
            ):
                print(f"já conferido: {label}")
                skipped += 1
                continue

            print(f"baixando: {label} ({size} bytes)", flush=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(f"{target.name}.part")
            try:
                sha256 = _download(entry["url"], part, size)
                if sha256 != expected:
                    raise PullError(f"sha256 {sha256} diferente do manifesto {expected}")
                os.replace(part, target)
            except PullError as exc:
                raise PullError(f"{label}: {exc}") from exc
            except (OSError, http.client.HTTPException) as exc:
                raise PullError(f"{label}: falha no download: {exc}") from exc
            finally:
                part.unlink(missing_ok=True)
            downloaded += 1
    return downloaded, skipped


def _pull(args: argparse.Namespace) -> int:
    manifest = _load_checked(args.policy)
    if manifest is None:
        return 1
    try:
        downloaded, skipped = pull(manifest, args.dest, args.components)
    except PullError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(f"Pesos conferidos: {downloaded} baixado(s), {skipped} já presente(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avatar_worker.manifest")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="confere o manifesto contra a política")
    verify.add_argument("--policy", required=True, help="arquivo MODEL_MANIFEST.json")
    verify.set_defaults(handler=_verify)
    pull_parser = commands.add_parser("pull", help="baixa os pesos conferindo cada SHA-256")
    pull_parser.add_argument("--policy", required=True, help="arquivo MODEL_MANIFEST.json")
    pull_parser.add_argument("--dest", required=True, type=Path, help="diretório dos pesos")
    pull_parser.add_argument(
        "--component",
        action="append",
        dest="components",
        metavar="ID",
        help="baixa só este componente; repetível",
    )
    pull_parser.set_defaults(handler=_pull)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
