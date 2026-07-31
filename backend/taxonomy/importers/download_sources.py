"""Descarga y verifica las fuentes versionadas del catálogo taxonómico."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path


TAXONOMY_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = TAXONOMY_DIR / "sources.json"
DEFAULT_DESTINATION = TAXONOMY_DIR.parents[1] / ".cache" / "taxonomy_sources"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_sources(
    manifest_path: Path = DEFAULT_MANIFEST,
    destination: Path = DEFAULT_DESTINATION,
    force: bool = False,
) -> dict[str, Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, Path] = {}

    for key, source in manifest.items():
        if source.get("bundled_path"):
            bundled = TAXONOMY_DIR / source["bundled_path"]
            if not bundled.exists():
                raise FileNotFoundError(
                    f"Falta la fuente incluida {key}: {bundled}"
                )
            actual_hash = _sha256(bundled)
            if actual_hash != source["sha256"]:
                raise ValueError(
                    f"Checksum inválido para {key}: {actual_hash}; "
                    f"se esperaba {source['sha256']}"
                )
            resolved[key] = bundled
            continue

        target = destination / source["filename"]
        expected_hash = source["sha256"]
        if target.exists() and not force and _sha256(target) == expected_hash:
            resolved[key] = target
            continue

        temporary = target.with_suffix(f"{target.suffix}.part")
        request = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "Teacher-Ideal-Taxonomy-Builder/3.0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)

        actual_hash = _sha256(temporary)
        if actual_hash != expected_hash:
            temporary.unlink(missing_ok=True)
            raise ValueError(
                f"Checksum inválido para {key}: {actual_hash}; "
                f"se esperaba {expected_hash}"
            )
        temporary.replace(target)
        resolved[key] = target

    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sources = download_sources(args.manifest, args.destination, args.force)
    for key, path in sources.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
