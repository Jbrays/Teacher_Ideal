"""Acceso cacheado al catálogo compartido por extracción y resolución."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional

from .models import Taxonomy


DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parent / "taxonomy.json"


@lru_cache(maxsize=4)
def _load_taxonomy(path: str) -> Taxonomy:
    return Taxonomy.from_file(path)


def get_taxonomy(path: Optional[str | Path] = None) -> Taxonomy:
    resolved = Path(path or DEFAULT_TAXONOMY_PATH).resolve()
    return _load_taxonomy(str(resolved))


@lru_cache(maxsize=4)
def _load_canonical_lookup(path: str) -> Mapping[str, str]:
    return MappingProxyType(_load_taxonomy(path).canonical_label_lookup())


def get_canonical_label_lookup(
    path: Optional[str | Path] = None,
) -> Mapping[str, str]:
    resolved = Path(path or DEFAULT_TAXONOMY_PATH).resolve()
    return _load_canonical_lookup(str(resolved))
